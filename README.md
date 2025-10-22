# Ghost_Comm: Secure Encrypted Communication Network over Tor

This project implements a secure, multi-hop, end-to-end encrypted communication network utilizing Tor hidden services.

## Project Architecture

The core of the `Ghost_Comm` project is a Python application designed for dynamic, ephemeral, and secure communication. It consists of three main components:

1.  **`PrimaryNode`**:
    *   Acts as a central point for clients to discover the network.
    *   Runs its own ephemeral Tor hidden service.
    *   Manages a pool of `Node` instances, each running its own ephemeral Tor hidden service.
    *   Generates and distributes a "lock-cycle payload" to clients. This payload contains the onion addresses and PGP public keys of the distributed `Node`s, along with their processing configurations. The payload is encrypted using a hybrid AES/PGP scheme, ensuring only the intended client can decrypt it.
    *   Periodically refreshes the "lock-cycle" by creating new `Node` instances and their associated ephemeral hidden services, enhancing forward secrecy.

2.  **`Node`**:
    *   Represents a hop in the distributed proxy chain.
    *   Each `Node` runs its own ephemeral Tor hidden service.
    *   Generates its own PGP key pair.
    *   Receives layered encrypted data from the previous hop (client or another `Node`).
    *   Decrypts one layer of encryption using its private key.
    *   Processes the decrypted data (e.g., applies a hash based on its configuration).
    *   Re-encrypts the processed data for the next hop using the next hop's public key.
    *   If it's the last node, it returns the final processed data.

3.  **`Client`**:
    *   Connects to the `PrimaryNode` (via Tor) to request the lock-cycle payload.
    *   Decrypts the payload to obtain the `proxy_chain_config` (containing the distributed `Node`s' onion addresses and public keys).
    *   Constructs a multi-layered encrypted message (onion routing style), where each layer is encrypted for a specific `Node` in the chain.
    *   Traverses the distributed proxy chain by sending the outermost encrypted layer to the first `Node`'s onion service via its local Tor SOCKS proxy.
    *   Receives and processes the final response from the last `Node` in the chain.

## Cryptography

The project employs robust cryptographic primitives:

*   **PGP (Pretty Good Privacy)**: Used for asymmetric encryption (key exchange) and digital signatures. Each `Client` and `Node` generates its own PGP key pair.
*   **AES (Advanced Encryption Standard) with Fernet**: Used for strong symmetric encryption of bulk data. The `PrimaryNode` uses a hybrid AES/PGP scheme to encrypt the lock-cycle payload.

## Tor Integration

*   Both `PrimaryNode` and `Node` instances utilize `stem` to programmatically create and manage **ephemeral Tor hidden services (v3)**. These services are temporary and are refreshed periodically, enhancing anonymity and forward secrecy.
*   The `Client` uses a local Tor SOCKS proxy to connect to the onion services of the `PrimaryNode` and the distributed `Node`s.

## `create_torsite.sh` Script

The `create_torsite.sh` script is a **separate utility** that sets up *persistent* Tor hidden services backed by Nginx web servers.

**Key Differences and Purpose:**

*   **Persistent vs. Ephemeral**: `create_torsite.sh` creates services that persist across Tor restarts and system reboots. The Python application creates temporary, ephemeral services that are dynamically managed and refreshed.
*   **Nginx vs. Python Server**: `create_torsite.sh` configures Nginx to serve static HTML content. The Python application's `Node`s run their own Python servers to handle dynamic, encrypted communication.
*   **System-level vs. Application-level**: `create_torsite.sh` modifies system files (`/etc/tor/torrc`, Nginx configurations) and requires `sudo`. The Python application manages its Tor services programmatically within its own process.

**`create_torsite.sh` is NOT integrated with the Python application's communication flow.** It serves as an example or a utility for setting up a *different type* of Tor hidden service (e.g., for hosting static content or for testing persistent services independently). Running it will create separate Tor hidden services that are distinct from those managed by the Python application.

## Getting Started

To run the Python application, ensure you have Tor installed and running, and its control port (default 9051) is accessible.

1.  **Install Python dependencies:**
    ```bash
    pip install -r requirements.txt
    ```
2.  **Run the main application:**
    ```bash
    python main.py
    ```

This will start the `PrimaryNode`, its distributed `Node`s, and simulate a client communication flow.
