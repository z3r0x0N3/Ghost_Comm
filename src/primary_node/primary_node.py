# src/primary_node/primary_node.py
import sys
import os
import json
import random
import threading
import time
import pgpy
from typing import Dict, Tuple

# ensure top-level package import works when running main.py from project root
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '../..')))

from stem.control import Controller
from src.crypto.utils import generate_aes_key, encrypt_aes, encrypt_pgp
from src.network.server import Server
from src.network.proxy_chain import ProxyChain


class PrimaryNode:
    """Primary node that creates 6 fresh ephemeral .onion services each lock-cycle."""

    def __init__(
        self,
        host: str = "127.0.0.1",
        port: int = 8000,
        tor_control_port: int = 9051,
        tor_control_password: str = None,
    ):
        self.host = host
        self.port = port
        self.node_keywords = [f"keyword_{i}" for i in range(8)]
        self.hashing_algorithms = ["sha256", "sha512", "sha3_256"]

        # initial proxy chain configuration (will be replaced on first lock cycle)
        self.proxy_chain_config = self.generate_proxy_chain_config()
        self.proxy_chain = ProxyChain(self.proxy_chain_config["node_configs"], self.proxy_chain_config["node_order"])

        # server that receives client requests (assumes Server accepts host, port, handler)
        self.server = Server(self.host, self.port, self.handle_client_request)

        # threading / runtime control
        self.lock_cycle_thread = None
        self.running = False

        # Tor controller and ephemeral hidden services bookkeeping
        self.tor_control_port = tor_control_port
        self.tor_control_password = tor_control_password
        self.tor_controller: Controller | None = None
        # self.hidden_services maps service_id -> onion_addr (string)
        self.hidden_services: Dict[str, str] = {}
        self.distributed_nodes: Dict[str, Node] = {}

        # attempt to connect to Tor controller at init
        self._connect_to_tor_controller()

    # -------------------------- Tor helper methods --------------------------
    def _connect_to_tor_controller(self) -> None:
        """Connect to local Tor control port (9051 by default)."""
        try:
            self.tor_controller = Controller.from_port(port=self.tor_control_port)
            if self.tor_control_password:
                self.tor_controller.authenticate(password=self.tor_control_password)
            else:
                self.tor_controller.authenticate()  # cookie or no-auth fallback
            print("PrimaryNode: Connected to Tor controller.")
        except Exception as e:
            print(f"PrimaryNode: Warning: Could not connect to Tor controller on port {self.tor_control_port}: {e}. Tor functionality will be unavailable.")
            self.tor_controller = None

    def _create_ephemeral_service(self, local_port: int, await_publication: bool = True, publish_timeout: float = 20.0) -> Tuple[str, str] | None:
        """
        Create single ephemeral hidden service mapping Tor port 80 -> local_port.
        Returns (onion_addr, service_id) on success, or None on failure.
        """
        if not self.tor_controller:
            return None

        try:
            # create ephemeral hidden service (v3) — ask stem to wait for publication optionally
            service = self.tor_controller.create_ephemeral_hidden_service(
                {80: local_port},
                key_type="ED25519-V3",
                await_publication=await_publication
            )

            service_id = service.service_id
            onion_addr = f"{service_id}.onion"

            # if await_publication was False, verify published manually
            if not await_publication:
                deadline = time.time() + publish_timeout
                published = False
                while time.time() < deadline:
                    try:
                        info = (self.tor_controller.get_info("onions/current") or "")
                        if service_id in info:
                            published = True
                            break
                    except Exception:
                        pass
                    time.sleep(0.3)
                if not published:
                    # try cleaning up and report failure
                    try:
                        self.tor_controller.remove_ephemeral_hidden_service(service_id)
                    except Exception:
                        pass
                    print(f"PrimaryNode: Error: ephemeral onion {onion_addr} did not publish within {publish_timeout}s")
                    return None

            # record
            self.hidden_services[service_id] = onion_addr
            print(f"PrimaryNode: Created ephemeral hidden service: {onion_addr} -> local port {local_port}")
            return onion_addr, service_id

        except Exception as e:
            print(f"PrimaryNode: Error creating ephemeral hidden service (local_port={local_port}): {e}")
            return None

    def _remove_ephemeral_service(self, service_id: str) -> None:
        """Remove ephemeral hidden service by service_id (best-effort)."""
        if not self.tor_controller:
            return
        try:
            # stem provides remove_ephemeral_hidden_service in modern versions
            # if not present, fallback to remove_hidden_service (older name)
            try:
                self.tor_controller.remove_ephemeral_hidden_service(service_id)
            except AttributeError:
                # older stem naming
                self.tor_controller.remove_hidden_service(service_id)
            print(f"PrimaryNode: Removed ephemeral hidden service: {service_id}.onion")
        except Exception as e:
            print(f"PrimaryNode: Warning: could not remove ephemeral hidden service {service_id}: {e}")
        finally:
            self.hidden_services.pop(service_id, None)

    # -------------------------- Lock-cycle onion creation --------------------------
    def create_lock_cycle_onions(self, count: int = 6, local_port: int | None = None, publish_timeout: float = 20.0) -> Dict[str, Tuple[str, str]]:
        """
        Create `count` ephemeral .onion services for distributed nodes and update self.proxy_chain_config.

        Returns mapping { node_id: (onion_address, service_id) } for successfully created onions.
        On failure (Tor not connected) returns {}.
        """
        if local_port is None:
            local_port = self.port # This will be the PrimaryNode's port for its own onion service

        if not self.tor_controller:
            print("PrimaryNode: Tor controller not connected — cannot create onions.")
            return {}

        # 1) Stop and remove previous distributed nodes and their services
        if self.distributed_nodes:
            for node_id, node_instance in list(self.distributed_nodes.items()):
                try:
                    node_instance.stop_server()
                except Exception as e:
                    print(f"PrimaryNode: Warning stopping old distributed node {node_id}: {e}")
            self.distributed_nodes = {}

        # 2) Create new distributed Node instances and their ephemeral services
        created_node_info: Dict[str, Dict[str, str]] = {}
        node_ids = [f"node_{i}" for i in range(count)]
        random.shuffle(node_ids)

        for node_id in node_ids:
            # Create a new Node instance
            # We pass port=0 so the OS assigns a free port for the Node's server
            node_instance = Node(
                node_id=node_id,
                keyword=random.choice(self.node_keywords),
                hashing_algorithm=random.choice(self.hashing_algorithms),
                port=0, # Let OS assign a free port
                tor_control_port=self.tor_control_port,
                tor_control_password=self.tor_control_password
            )
            self.distributed_nodes[node_id] = node_instance

            # Start the Node's server and its hidden service
            node_instance.start_server()
            time.sleep(0.5) # Give the node's server and onion service a moment to start

            if node_instance.onion_address and node_instance.pgp_pubkey:
                created_node_info[node_id] = {
                    "onion_address": node_instance.onion_address,
                    "pgp_pubkey": str(node_instance.pgp_pubkey) # Convert PGPKey object to string for serialization
                }
            else:
                print(f"PrimaryNode: Failed to create ephemeral onion or get pubkey for distributed node {node_id}; continuing")
                # Clean up the failed node
                node_instance.stop_server()
                self.distributed_nodes.pop(node_id)

        # 3) Build node_configs for proxy chain based on created distributed nodes
        node_configs: Dict[str, Dict[str, str]] = {}
        for node_id, info in created_node_info.items():
            node_configs[node_id] = {
                "onion_address": info["onion_address"],
                "pgp_pubkey": info["pgp_pubkey"],
                "keyword": self.distributed_nodes[node_id].keyword, # Get keyword from the actual node instance
                "hashing_algorithm": self.distributed_nodes[node_id].hashing_algorithm # Get hashing_algorithm from the actual node instance
            }

        # If some failed and we need to preserve chain length, add placeholders (though ideally we want all nodes to start)
        if len(created_node_info) < count:
            print(f"PrimaryNode: Warning: Only {len(created_node_info)} out of {count} distributed nodes started successfully.")

        # final node order: shuffle to avoid predictable ordering
        final_node_order = list(node_configs.keys())
        random.shuffle(final_node_order)

        # update proxy_chain_config
        self.proxy_chain_config = {
            "node_order": final_node_order,
            "node_configs": node_configs
        }

        # The primary_node_url will now be the onion address of the PrimaryNode itself, if it has one.
        # This is for the client to initially connect to the PrimaryNode to get the payload.
        if self.onion_address:
            self.proxy_chain_config["primary_node_url"] = self.onion_address
        else:
            self.proxy_chain_config["primary_node_url"] = f"{self.host}:{self.port}" # Fallback to direct address

        # Rebuild proxy chain (this will now be a logical chain of the distributed nodes' info)
        # The ProxyChain class itself will need to be updated to reflect this change.
        # For now, we'll keep it as is, but it will be refactored later.
        self.proxy_chain = ProxyChain(self.proxy_chain_config["node_configs"], self.proxy_chain_config["node_order"])
        print(f"PrimaryNode: create_lock_cycle_onions: created {len(created_node_info)} distributed nodes, primary_node_url={self.proxy_chain_config['primary_node_url']}")
        return created_node_info

    # -------------------------- Other existing logic --------------------------
    def generate_proxy_chain_config(self) -> dict:
        """Generates a default proxy chain config used before onions exist."""
        # This method will now generate a config for the PrimaryNode's own onion service
        # and a placeholder for distributed nodes.
        config = {
            "node_order": [],
            "node_configs": {},
            "primary_node_url": f"{self.host}:{self.port}" # Default to direct address
        }
        print(f"PrimaryNode: Generated default proxy chain config: {config}")
        return config

    def get_lock_cycle_payload(self, client_pub_key_pem: bytes) -> bytes:
        """Generates and encrypts the lock-cycle payload (AES + wrap AES key with client PGP)."""
        client_pub_key, _ = pgpy.PGPKey.from_blob(client_pub_key_pem)

        payload = {
            "proxy_chain_config": self.proxy_chain_config,
            "primary_node_url": self.proxy_chain_config.get("primary_node_url", f"{self.host}:{self.port}")
        }
        payload_bytes = json.dumps(payload).encode("utf-8")

        # AES encryption for payload
        aes_key = generate_aes_key()
        encrypted_payload_aes = encrypt_aes(payload_bytes, aes_key)

        # wrap AES key with client PGP
        encrypted_aes_key_pgp = encrypt_pgp(aes_key, client_pub_key)

        return json.dumps({
            "encrypted_payload": encrypted_payload_aes.hex(),
            "encrypted_aes_key": encrypted_aes_key_pgp.hex()
        }).encode("utf-8")

    def refresh_lock_cycle(self):
        """Refresh lock-cycle: create 6 new distributed nodes and their onion services."""
        print("PrimaryNode: Refreshing lock-cycle...")

        # Create 6 fresh distributed nodes and their onion services
        self.create_lock_cycle_onions(count=6, publish_timeout=20.0)

        # after creation, self.proxy_chain_config and self.distributed_nodes are already updated
        print("PrimaryNode: Lock-cycle refreshed.")

    def _lock_cycle_worker(self):
        """Background worker that refreshes the lock-cycle periodically."""
        # First, create the initial set of distributed nodes
        self.create_lock_cycle_onions(count=6, publish_timeout=20.0)

        while self.running:
            # production: time.sleep(60)
            time.sleep(60)
            try:
                self.refresh_lock_cycle()
            except Exception as e:
                print(f"PrimaryNode: Lock-cycle worker encountered an error: {e}")

    def handle_client_request(self, data: bytes) -> bytes:
        """Handle incoming client requests from Server."""
        request = json.loads(data.decode("utf-8"))
        if request.get("type") == "get_payload":
            client_pub_key_pem = request["pub_key"].encode("utf-8")
            response = self.get_lock_cycle_payload(client_pub_key_pem)
            print(f"PrimaryNode: Sending payload to client.")
            return response
        elif request.get("type") == "process_data":
            # This branch is now deprecated as clients will directly interact with distributed nodes.
            # However, for backward compatibility or direct processing by PrimaryNode, we can keep it.
            print("PrimaryNode: Received 'process_data' request. This should now go to distributed nodes.")
            # For now, we'll just return an error or a placeholder response.
            return json.dumps({"status": "error", "message": "Please use distributed nodes for data processing."}).encode("utf-8")
        return b"PrimaryNode: Error: Unknown request type"

    def start_server(self):
        """Start server and lock-cycle worker."""
        self.running = True
        # Start PrimaryNode's own server
        threading.Thread(target=self.server.start, daemon=True).start()
        # Create PrimaryNode's own onion service
        if self.tor_controller:
            onion_addr, service_id = self._create_ephemeral_service(self.port)
            self.onion_address = onion_addr # Store PrimaryNode's own onion address

        self.lock_cycle_thread = threading.Thread(target=self._lock_cycle_worker, daemon=True)
        self.lock_cycle_thread.start()
        print(f"PrimaryNode server started on {self.host}:{self.port}")

    def stop_server(self):
        """Stop server and cleanup ephemeral services."""
        self.running = False
        # Stop all distributed nodes
        if self.distributed_nodes:
            for node_id, node_instance in list(self.distributed_nodes.items()):
                try:
                    node_instance.stop_server()
                except Exception as e:
                    print(f"PrimaryNode: Warning stopping distributed node {node_id} at shutdown: {e}")
            self.distributed_nodes = {}

        # Remove PrimaryNode's own ephemeral service
        if self.tor_controller and self.hidden_services:
            for sid in list(self.hidden_services.keys()):
                try:
                    self._remove_ephemeral_service(sid)
                except Exception as e:
                    print(f"PrimaryNode: Warning removing own hidden service {sid} at shutdown: {e}")
            self.hidden_services = {}
            try:
                self.tor_controller.close()
            except Exception:
                pass
        # stop server
        try:
            self.server.stop()
        except Exception:
            pass
        print("PrimaryNode server stopped.")

