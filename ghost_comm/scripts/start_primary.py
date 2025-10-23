import argparse
import signal
import sys
import time

from ghost_comm import PrimaryNode


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Start the Ghost-Comm primary node.")
    parser.add_argument("--host", default="127.0.0.1", help="Bind address for the primary node server.")
    parser.add_argument("--port", type=int, default=8000, help="Bind port for the primary node server.")
    parser.add_argument("--tor-control-port", type=int, default=9051, help="Tor control port to use.")
    parser.add_argument("--tor-control-password", default=None, help="Tor control port password if configured.")
    parser.add_argument(
        "--onion-wait-time",
        type=int,
        default=60,
        help="Seconds to wait for the onion service to be published before continuing.",
    )
    parser.add_argument("--tor-socks-host", default="127.0.0.1", help="Host for the Tor SOCKS proxy (for onion HTTP checks).")
    parser.add_argument("--tor-socks-port", type=int, default=9050, help="Port for the Tor SOCKS proxy (for onion HTTP checks).")
    parser.add_argument(
        "--payload-pubkey-path",
        default="~/.AUTH/Z3R0-public-key.asc",
        help="Path to the PGP public key used when retrieving the payload after each lock cycle.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()

    primary = PrimaryNode(
        host=args.host,
        port=args.port,
        tor_control_port=args.tor_control_port,
        tor_control_password=args.tor_control_password,
        tor_socks_host=args.tor_socks_host,
        tor_socks_port=args.tor_socks_port,
        payload_pubkey_path=args.payload_pubkey_path,
    )
    primary.start_server()

    def _shutdown(signum, frame):
        print(f"\nReceived signal {signum}; shutting down primary node...")
        primary.stop_server()
        sys.exit(0)

    signal.signal(signal.SIGINT, _shutdown)
    signal.signal(signal.SIGTERM, _shutdown)

    # Wait for the onion service to appear (when Tor is available)
    deadline = time.time() + max(0, args.onion_wait_time)
    while not primary.onion_address and time.time() < deadline:
        time.sleep(1)

    if primary.onion_address:
        print(f"Primary node onion service: {primary.onion_address}")
    else:
        print("Primary node running without an onion service (Tor unavailable?).")

    print("Ghost-Comm primary node is operational. Press Ctrl+C to stop.")

    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        _shutdown(signal.SIGINT, None)


if __name__ == "__main__":
    main()
