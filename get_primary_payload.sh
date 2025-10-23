#!/usr/bin/env bash
set -euo pipefail

# Fetch the encrypted payload from the primary node using the bundled PGP key.

KEY_FILE="${HOME}/.AUTH/Z3R0-public-key.asc"
ENDPOINT="${1:-${PRIMARY_NODE_ENDPOINT:-http://127.0.0.1:8000/payload}}"
TOR_SOCKS_HOST="${TOR_SOCKS_HOST:-127.0.0.1}"
TOR_SOCKS_PORT="${TOR_SOCKS_PORT:-9050}"

if [[ ! -r "${KEY_FILE}" ]]; then
    echo "Error: cannot read PGP key at ${KEY_FILE}" >&2
    exit 1
fi

JSON_PAYLOAD="$(KEY_FILE="${KEY_FILE}" python3 - <<'PY'
import json
import os
from pathlib import Path

key_file = Path(os.environ["KEY_FILE"])
key_data = key_file.read_text()
print(json.dumps({"type": "get_payload", "pub_key": key_data}))
PY
)"

curl_args=(-sS -X POST "${ENDPOINT}" -H "Content-Type: application/json" -d "${JSON_PAYLOAD}")
if [[ "${ENDPOINT}" == http://*.onion* ]] || [[ "${ENDPOINT}" == https://*.onion* ]]; then
    curl_args=(--socks5-hostname "${TOR_SOCKS_HOST}:${TOR_SOCKS_PORT}" "${curl_args[@]}")
fi

curl "${curl_args[@]}"
echo
