#!/usr/bin/env bash
set -euo pipefail

# Decrypt a Ghost-Comm payload JSON containing encrypted_payload/encrypted_aes_key.
# Usage:
#   ./decrypt_primary_payload.sh payload.json
#   ./get_primary_payload.sh | ./decrypt_primary_payload.sh -

if [[ $# -eq 0 && ! -t 0 ]]; then
    PAYLOAD_SOURCE="-"
else
    PAYLOAD_SOURCE="${1:-payload.json}"
fi
GPG=${GPG:-gpg}

TMP_KEY="$(mktemp "${TMPDIR:-/tmp}/ghostcomm-key.XXXXXX")"
TMP_PAYLOAD="$(mktemp "${TMPDIR:-/tmp}/ghostcomm-payload.XXXXXX")"

cleanup() {
    rm -f "${TMP_KEY}" "${TMP_PAYLOAD}"
}
trap cleanup EXIT

if [[ "${PAYLOAD_SOURCE}" == "-" ]]; then
    python3 - <<'PY' "${TMP_KEY}" "${TMP_PAYLOAD}" || exit 1
import json, binascii, sys, pathlib

key_path = pathlib.Path(sys.argv[1])
payload_path = pathlib.Path(sys.argv[2])
raw = sys.stdin.read()
if not raw.strip():
    raise SystemExit("Error: no JSON payload received on stdin.")
try:
    payload = json.loads(raw)
except json.JSONDecodeError as exc:
    raise SystemExit(f"Error: could not parse JSON from stdin ({exc}).") from exc
try:
    encrypted_key = binascii.unhexlify(payload["encrypted_aes_key"])
    encrypted_payload = binascii.unhexlify(payload["encrypted_payload"])
except KeyError as exc:
    raise SystemExit(f"Missing key in payload JSON: {exc}") from exc

key_path.write_bytes(encrypted_key)
payload_path.write_bytes(encrypted_payload)
PY
else
    if [[ ! -r "${PAYLOAD_SOURCE}" ]]; then
        echo "Error: payload file '${PAYLOAD_SOURCE}' not found or unreadable." >&2
        exit 1
    fi
    python3 - <<'PY' "${TMP_KEY}" "${TMP_PAYLOAD}" "${PAYLOAD_SOURCE}" || exit 1
import json, binascii, sys, pathlib

key_path = pathlib.Path(sys.argv[1])
payload_path = pathlib.Path(sys.argv[2])
payload_file = pathlib.Path(sys.argv[3])
with payload_file.open("r", encoding="utf-8") as fh:
    payload = json.load(fh)
try:
    encrypted_key = binascii.unhexlify(payload["encrypted_aes_key"])
    encrypted_payload = binascii.unhexlify(payload["encrypted_payload"])
except KeyError as exc:
    raise SystemExit(f"Missing key in payload JSON: {exc}") from exc

key_path.write_bytes(encrypted_key)
payload_path.write_bytes(encrypted_payload)
PY
fi

AES_KEY="$("${GPG}" --decrypt "${TMP_KEY}")" || true
if [[ -z "${AES_KEY}" ]]; then
    echo "Error: no AES key recovered from GPG."
    exit 1
fi

export AES_KEY
python3 - "$TMP_PAYLOAD" <<'PY'
import json
import sys
import os
from pathlib import Path
from cryptography.fernet import Fernet

payload_path = Path(sys.argv[1])
key = os.environ["AES_KEY"].strip().encode()
token = payload_path.read_bytes()
plain = Fernet(key).decrypt(token)
print(json.dumps(json.loads(plain), indent=2))
PY
