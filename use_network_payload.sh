#!/usr/bin/env bash
set -euo pipefail

# Send a message through the distributed proxy chain described in the decrypted
# network access payload. Reads ~/.AUTH/Network_Access_Payload.json by default.
#
# Examples:
#   ./use_network_payload.sh "Hello world"
#   echo "payload" | ./use_network_payload.sh
#   PAYLOAD_JSON=/path/to/custom.json ./use_network_payload.sh -f message.bin

PAYLOAD_FILE="${PAYLOAD_JSON:-$HOME/.AUTH/Network_Access_Payload.json}"
TOR_SOCKS_HOST="${TOR_SOCKS_HOST:-127.0.0.1}"
TOR_SOCKS_PORT="${TOR_SOCKS_PORT:-9050}"
INPUT_MODE="arg"
INPUT_PATH=""
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

usage() {
    echo "Usage: $0 [-f file] [message]" >&2
    exit 1
}

while getopts ":f:h" opt; do
    case "$opt" in
        f)
            INPUT_MODE="file"
            INPUT_PATH="$OPTARG"
            ;;
        h)
            usage
            ;;
        \?)
            usage
            ;;
    esac
done
shift $((OPTIND - 1))

TMP_INPUT=""
cleanup_tmp() {
    if [[ -n "${TMP_INPUT}" && -f "${TMP_INPUT}" ]]; then
        rm -f "${TMP_INPUT}"
    fi
}
trap cleanup_tmp EXIT

if [[ "${INPUT_MODE}" == "file" ]]; then
    if [[ -z "${INPUT_PATH}" || ! -r "${INPUT_PATH}" ]]; then
        echo "Error: cannot read input file '${INPUT_PATH}'" >&2
        exit 1
    fi
    MESSAGE_FILE="${INPUT_PATH}"
else
    if [[ $# -gt 0 ]]; then
        TMP_INPUT="$(mktemp "${TMPDIR:-/tmp}/ghostcomm-msg.XXXXXX")"
        printf "%s" "$1" > "${TMP_INPUT}"
        MESSAGE_FILE="${TMP_INPUT}"
    elif [[ -t 0 ]]; then
        TMP_INPUT="$(mktemp "${TMPDIR:-/tmp}/ghostcomm-msg.XXXXXX")"
        echo -n "Enter message: " >&2
        if ! IFS= read -r LINE; then
            echo "Error: no input data supplied." >&2
            exit 1
        fi
        printf "%s" "$LINE" > "${TMP_INPUT}"
        MESSAGE_FILE="${TMP_INPUT}"
    else
        TMP_INPUT="$(mktemp "${TMPDIR:-/tmp}/ghostcomm-msg.XXXXXX")"
        cat > "${TMP_INPUT}"
        MESSAGE_FILE="${TMP_INPUT}"
    fi
fi

if [[ ! -s "${MESSAGE_FILE}" ]]; then
    echo "Error: no input data supplied." >&2
    exit 1
fi

if [[ ! -r "${PAYLOAD_FILE}" ]]; then
    echo "Error: payload file '${PAYLOAD_FILE}' not found or unreadable." >&2
    exit 1
fi

python3 - "$PAYLOAD_FILE" "$TOR_SOCKS_HOST" "$TOR_SOCKS_PORT" "$SCRIPT_DIR" <<'PY'
import json
import os
import socket
import sys
from pathlib import Path

import pgpy
import socks

repo_root = Path(sys.argv[4])
src_path = repo_root / "src"
sys.path.append(str(repo_root))
sys.path.append(str(src_path))

from src.crypto.utils import encrypt_pgp

payload_path = Path(sys.argv[1])
tor_host = sys.argv[2]
tor_port = int(sys.argv[3])
message = sys.stdin.buffer.read()

if not message:
    raise SystemExit("Error: no message data received.")

payload = json.loads(payload_path.read_text(encoding="utf-8"))
proxy_chain_config = payload["proxy_chain_config"]
node_order = proxy_chain_config["node_order"]
node_configs = proxy_chain_config["node_configs"]

if not node_order:
    raise SystemExit("Error: proxy chain config has no nodes.")

current_data_hex = message.hex()
next_hop_onion = None
next_hop_pubkey = None

for node_id in reversed(node_order):
    node_info = node_configs[node_id]
    node_pubkey_pem = node_info["pgp_pubkey"]
    node_pubkey, _ = pgpy.PGPKey.from_blob(node_pubkey_pem)

    payload_for_node = {
        "original_data": current_data_hex,
        "next_hop_onion": next_hop_onion,
        "next_hop_pubkey": next_hop_pubkey,
        "final_destination": None,
    }
    encrypted_blob = encrypt_pgp(json.dumps(payload_for_node).encode("utf-8"), node_pubkey)
    current_data_hex = encrypted_blob.hex()

    next_hop_onion = node_info["onion_address"]
    next_hop_pubkey = node_pubkey_pem

first_node_id = node_order[0]
first_node_onion = node_configs[first_node_id]["onion_address"]

sock = socks.socksocket()
try:
    sock.set_proxy(socks.SOCKS5, tor_host, tor_port, rdns=True)
    sock.settimeout(60)
    sock.connect((first_node_onion, 80))
    request = json.dumps({"encrypted_data": current_data_hex}).encode("utf-8")
    sock.sendall(request)

    response_chunks = []
    while True:
        chunk = sock.recv(4096)
        if not chunk:
            break
        response_chunks.append(chunk)
    response = b"".join(response_chunks)
finally:
    sock.close()

try:
    response_json = json.loads(response.decode("utf-8"))
except json.JSONDecodeError as exc:
    print("Error: failed to decode response from chain:", exc, file=sys.stderr)
    sys.exit(1)

status = response_json.get("status")
if status == "final_processed":
    processed_bytes = bytes.fromhex(response_json["data"])
    sys.stdout.buffer.write(processed_bytes)
else:
    print("Unexpected response from chain:", response_json, file=sys.stderr)
    sys.exit(1)
PY < "${MESSAGE_FILE}"
