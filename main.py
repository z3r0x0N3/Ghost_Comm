
import sys
import os
import time
import threading

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), 'src')))

from src.client.client import Client
from src.primary_node.primary_node import PrimaryNode

def main():
    """Main function to run the simulation."""
    # Tor configuration (adjust as needed)
    tor_control_port = 9051
    tor_control_password = None  # Set if your Tor control port is password protected
    tor_socks_proxy_host = '127.0.0.1'
    tor_socks_proxy_port = 9050

    # 1. Create a PrimaryNode and start its server
    primary_node = PrimaryNode(
        tor_control_port=tor_control_port,
        tor_control_password=tor_control_password
    )
    primary_node.start_server()
    time.sleep(5) # Give the server and its distributed nodes a moment to start and publish onion services

    print("PrimaryNode server and distributed nodes started.")

    # 2. Create a Client
    client = Client(
        name="testuser",
        email="test@example.com",
        tor_socks_proxy_host=tor_socks_proxy_host,
        tor_socks_proxy_port=tor_socks_proxy_port
    )
    print("Client created.")

    # 3. Client requests the lock-cycle payload from the PrimaryNode
    #    Connect to the PrimaryNode's onion address (or direct if Tor not available)
    client.primary_node_host = primary_node.onion_address if primary_node.onion_address else primary_node.host
    client.primary_node_port = 80 if primary_node.onion_address else primary_node.port

    print(f"Client connecting to PrimaryNode at {client.primary_node_host}:{client.primary_node_port}...")
    client.connect_to_primary_node()
    decrypted_payload_initial = client.request_lock_cycle_payload()
    client.close_connection()

    # 4. Client decrypts and prints the initial payload
    print("Initial Payload decrypted successfully!")
    print("Initial Decrypted payload:", decrypted_payload_initial)

    # 5. Send test data through the distributed proxy chain
    test_data = b"Hello Ghost-Comm!"
    print(f"Client sending data through distributed proxy chain (initial): {test_data}")
    processed_data_initial = client.send_data_through_distributed_proxy_chain(
        original_data=test_data,
        proxy_chain_config=decrypted_payload_initial['proxy_chain_config']
    )
    print(f"Data processed by distributed proxy chain (initial): {processed_data_initial}")

    # 6. Wait for a lock-cycle refresh (simulated)
    print("\nWaiting for lock-cycle refresh (simulating 10 seconds for demonstration)...")
    time.sleep(10) # In real scenario, this would be 60 seconds

    # 7. Client requests updated lock-cycle payload
    client.primary_node_host = primary_node.onion_address if primary_node.onion_address else primary_node.host
    client.primary_node_port = 80 if primary_node.onion_address else primary_node.port

    print(f"Client connecting to PrimaryNode at {client.primary_node_host}:{client.primary_node_port} for updated payload...")
    client.connect_to_primary_node()
    decrypted_payload_updated = client.request_lock_cycle_payload()
    client.close_connection()

    # 8. Client decrypts and prints the updated payload
    print("Updated Payload decrypted successfully!")
    print("Updated Decrypted payload:", decrypted_payload_updated)

    # 9. Send same test data through the distributed proxy chain again
    print(f"Client sending data through distributed proxy chain (updated): {test_data}")
    processed_data_updated = client.send_data_through_distributed_proxy_chain(
        original_data=test_data,
        proxy_chain_config=decrypted_payload_updated['proxy_chain_config']
    )
    print(f"Data processed by distributed proxy chain (updated): {processed_data_updated}")

    # 10. Close client connection and stop primary node server
    primary_node.stop_server()
    print("PrimaryNode server and distributed nodes stopped.")

if __name__ == "__main__":
    main()
