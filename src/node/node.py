
import sys
import os
import json
import threading
import time
from typing import Dict, Tuple
import pgpy

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '../../')))

from stem.control import Controller
from src.crypto.utils import hash_data, generate_aes_key, encrypt_aes, decrypt_aes, generate_pgp_key, encrypt_pgp, decrypt_pgp
from src.network.server import Server


class Node:
    """Represents a node in the proxy chain, now capable of running as a network service."""

    def __init__(
        self,
        node_id: str,
        keyword: str,
        hashing_algorithm: str,
        host: str = "127.0.0.1",
        port: int = 0,  # 0 means OS will assign a free port
        tor_control_port: int = 9051,
        tor_control_password: str = None,
        pgp_key_passphrase: str = None,
    ):
        """Initializes a Node."""
        self.node_id = node_id
        self.keyword = keyword
        self.hashing_algorithm = hashing_algorithm
        self.host = host
        self.port = port
        self.tor_control_port = tor_control_port
        self.tor_control_password = tor_control_password
        self.pgp_key_passphrase = pgp_key_passphrase

        self.tor_controller: Controller | None = None
        self.hidden_service_id: str | None = None
        self.onion_address: str | None = None

        self.server: Server | None = None
        self.running = False

        self.pgp_key, self.pgp_pubkey = self._generate_or_load_pgp_key()

        # Attempt to connect to Tor controller at init
        self._connect_to_tor_controller()

        # Create ephemeral hidden service if Tor is connected
        if self.tor_controller:
            self._create_ephemeral_service(self.port)

    def _generate_or_load_pgp_key(self) -> Tuple[pgpy.PGPKey, pgpy.PGPKey]:
        """Generates a new PGP key pair for the node."""
        # In a real scenario, keys might be loaded from disk or a secure store.
        # For now, we generate a new one each time.
        name = f"Node {self.node_id}"
        email = f"{self.node_id}@ghostcomm.onion"
        key, pubkey = generate_pgp_key(name, email)
        # Sign the key with itself (self-signature)
        key.sign(key.uid_and_signatures[0])
        return key, pubkey

    # -------------------------- Tor helper methods --------------------------
    def _connect_to_tor_controller(self) -> None:
        """Connect to local Tor control port (9051 by default)."""
        try:
            self.tor_controller = Controller.from_port(port=self.tor_control_port)
            if self.tor_control_password:
                self.tor_controller.authenticate(password=self.tor_control_password)
            else:
                self.tor_controller.authenticate()  # cookie or no-auth fallback
            print(f"Node {self.node_id}: Connected to Tor controller.")
        except Exception as e:
            print(f"Node {self.node_id}: Warning: Could not connect to Tor controller on port {self.tor_control_port}: {e}. Tor functionality will be unavailable.")
            self.tor_controller = None

    def _create_ephemeral_service(self, local_port: int, await_publication: bool = True, publish_timeout: float = 20.0) -> None: 
        """
        Create single ephemeral hidden service mapping Tor port 80 -> local_port.
        Sets self.onion_address and self.hidden_service_id on success.
        """
        if not self.tor_controller:
            return

        try:
            service = self.tor_controller.create_ephemeral_hidden_service(
                {80: local_port},
                key_type="NEW",
                key_content="ED25519-V3",
                await_publication=await_publication
            )
            self.hidden_service_id = service.service_id
            self.onion_address = f"{self.hidden_service_id}.onion"
            print(f"Node {self.node_id}: Created ephemeral hidden service: {self.onion_address} -> local port {local_port}")

        except Exception as e:
            print(f"Node {self.node_id}: Error creating ephemeral hidden service (local_port={local_port}): {e}")
            self.hidden_service_id = None
            self.onion_address = None

    def _remove_ephemeral_service(self) -> None: 
        """Remove ephemeral hidden service (best-effort)."""
        if not self.tor_controller or not self.hidden_service_id:
            return
        try:
            try:
                self.tor_controller.remove_ephemeral_hidden_service(self.hidden_service_id)
            except AttributeError:
                self.tor_controller.remove_hidden_service(self.hidden_service_id)
            print(f"Node {self.node_id}: Removed ephemeral hidden service: {self.hidden_service_id}.onion")
        except Exception as e:
            print(f"Node {self.node_id}: Warning: could not remove ephemeral hidden service {self.hidden_service_id}: {e}")
        finally:
            self.hidden_service_id = None
            self.onion_address = None

    # -------------------------- Server methods --------------------------
    def start_server(self) -> None:
        """Starts the node's server to listen for incoming connections."""
        if not self.server:
            self.server = Server(self.host, self.port, self.handle_incoming_data)
        self.running = True
        threading.Thread(target=self.server.start, daemon=True).start()
        # Update the actual port if 0 was passed initially
        if self.port == 0:
            self.port = self.server.port
        print(f"Node {self.node_id}: Server started on {self.host}:{self.port}")

    def stop_server(self) -> None:
        """Stops the node's server and cleans up Tor services."""
        self.running = False
        if self.server:
            self.server.stop()
        self._remove_ephemeral_service()
        if self.tor_controller:
            try:
                self.tor_controller.close()
            except Exception:
                pass
        print(f"Node {self.node_id}: Server stopped.")

    def handle_incoming_data(self, data: bytes) -> bytes:
        """Handles incoming encrypted data, decrypts, processes, and re-encrypts for the next hop."""
        try:
            request_payload = json.loads(data.decode("utf-8"))
            encrypted_data_for_this_node_hex = request_payload["encrypted_data"]
            next_hop_onion = request_payload.get("next_hop_onion")
            next_hop_pubkey_pem = request_payload.get("next_hop_pubkey")
            final_destination = request_payload.get("final_destination")

            # 1. Decrypt data for this node using its PGP private key
            encrypted_data_for_this_node = bytes.fromhex(encrypted_data_for_this_node_hex)
            decrypted_data_json = decrypt_pgp(encrypted_data_for_this_node, self.pgp_key)
            decrypted_data_payload = json.loads(decrypted_data_json.decode("utf-8"))

            original_data = bytes.fromhex(decrypted_data_payload["original_data"])
            # The actual processing logic for this node
            processed_data = self.process_data(original_data)

            response_to_client = {"processed_data": processed_data.hex()}

            if next_hop_onion and next_hop_pubkey_pem:
                # 2. Re-encrypt for the next hop
                next_hop_pubkey, _ = pgpy.PGPKey.from_blob(next_hop_pubkey_pem.encode("utf-8"))
                
                # The data to be encrypted for the next hop includes the processed data
                # and potentially the remaining chain information.
                # For now, we'll just pass the processed data.
                data_for_next_hop_payload = {
                    "original_data": processed_data.hex(),
                    "next_hop_onion": next_hop_onion, # Pass along for the next node to use
                    "next_hop_pubkey": next_hop_pubkey_pem, # Pass along for the next node to use
                    "final_destination": final_destination # Pass along for the next node to use
                }
                encrypted_data_for_next_hop = encrypt_pgp(json.dumps(data_for_next_hop_payload).encode("utf-8"), next_hop_pubkey)

                # In a real scenario, this would involve making a network request to next_hop_onion
                # For now, we'll return the re-encrypted data as if it were forwarded.
                print(f"Node {self.node_id}: Re-encrypted for next hop {next_hop_onion}.")
                return json.dumps({
                    "status": "forwarded",
                    "encrypted_data": encrypted_data_for_next_hop.hex(),
                    "next_hop_onion": next_hop_onion,
                    "final_destination": final_destination
                }).encode("utf-8")
            elif final_destination:
                # 3. This is the last node, send to final destination
                print(f"Node {self.node_id}: Last node. Sending final processed data to {final_destination}.")
                # In a real scenario, this would involve making a network request to final_destination
                # For now, we'll return the final processed data.
                return json.dumps({"status": "final_processed", "data": processed_data.hex()}).encode("utf-8")
            else:
                print(f"Node {self.node_id}: Processed data, but no next hop or final destination specified.")
                return json.dumps({"status": "processed", "data": processed_data.hex()}).encode("utf-8")

        except Exception as e:
            print(f"Node {self.node_id}: Error handling incoming data: {e}")
            return json.dumps({"status": "error", "message": str(e)}).encode("utf-8")

    def process_data(self, data: bytes) -> bytes:
        """Processes incoming data (placeholder for actual processing logic)."""
        # This method will be updated to reflect the new distributed processing.
        # For now, it's a placeholder.
        print(f"Node {self.node_id}: Local data processing (placeholder).")
        return hash_data(data, self.hashing_algorithm)

    def set_new_config(self, keyword: str, hashing_algorithm: str):
        """Sets a new keyword and hashing algorithm."""
        self.keyword = keyword
        self.hashing_algorithm = hashing_algorithm


    def process_data(self, data: bytes) -> bytes:
        """Processes incoming data."""
        # The description is a bit ambiguous here. It says "single separate cryptographically hashed (512) digital shift cipher".
        # I will interpret this as: the data is first encrypted with the shift cipher, and then the result is hashed.
        encrypted_data = digital_shift_cipher(data, self.get_keyword_as_int())
        hashed_data = hash_data(encrypted_data, self.hashing_algorithm)
        return hashed_data

    def get_keyword_as_int(self) -> int:
        """Converts the keyword string to an integer for the shift cipher."""
        # Simple conversion for now, this can be made more complex.
        return sum(ord(c) for c in self.keyword)

    def set_new_config(self, keyword: str, hashing_algorithm: str):
        """Sets a new keyword and hashing algorithm."""
        self.keyword = keyword
        self.hashing_algorithm = hashing_algorithm
