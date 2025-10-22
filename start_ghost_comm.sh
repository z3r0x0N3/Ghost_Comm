#!/usr/bin/env bash
# Bootstrap and launch the Ghost-Comm primary node.

set -euo pipefail

PROJECT_ROOT="${PROJECT_ROOT:-$HOME/projects/OMEGA/Ghost-Comm}"
VENV_DIR="${VENV_DIR:-$PROJECT_ROOT/.venv}"
PYTHON_BIN="${PYTHON_BIN:-python3}"
TOR_CONTROL_PORT="${TOR_CONTROL_PORT:-9051}"
TOR_SOCKS_PORT="${TOR_SOCKS_PORT:-9050}"
LOG_FILE="${LOG_FILE:-$PROJECT_ROOT/.primary.log}"
LOG_PATH="$LOG_FILE"

info() {
    printf '[info] %s\n' "$*"
}

die() {
    printf '[error] %s\n' "$*" >&2
    exit 1
}

command -v "$PYTHON_BIN" >/dev/null 2>&1 || die "python3 is required but was not found in PATH"

[ -d "$PROJECT_ROOT" ] || die "Ghost-Comm project not found at $PROJECT_ROOT"

FORWARD_ARGS=()
while [ $# -gt 0 ]; do
    case "$1" in
        --tor-control-port)
            shift
            [ $# -gt 0 ] || die "Missing value for --tor-control-port"
            TOR_CONTROL_PORT="$1"
            ;;
        --tor-control-port=*)
            TOR_CONTROL_PORT="${1#*=}"
            ;;
        --tor-socks-port)
            shift
            [ $# -gt 0 ] || die "Missing value for --tor-socks-port"
            TOR_SOCKS_PORT="$1"
            ;;
        --tor-socks-port=*)
            TOR_SOCKS_PORT="${1#*=}"
            ;;
        *)
            FORWARD_ARGS+=("$1")
            ;;
    esac
    shift || true
done
set -- "${FORWARD_ARGS[@]}"

check_tor() {
    "$PYTHON_BIN" - <<PY
import socket, sys
sock = socket.socket()
sock.settimeout(1)
try:
    sock.connect(("127.0.0.1", int("$TOR_CONTROL_PORT")))
except OSError:
    sys.exit(1)
else:
    sys.exit(0)
finally:
    sock.close()
PY
}

ensure_tor_running() {
    if check_tor; then
        return 0
    fi

    info "Tor control port $TOR_CONTROL_PORT not reachable. Attempting to start Tor service..."

    if command -v systemctl >/dev/null 2>&1; then
        sudo systemctl start tor || true
    elif command -v service >/dev/null 2>&1; then
        sudo service tor start || true
    else
        info "No service manager found to start Tor automatically."
        return 1
    fi

    sleep 2
    check_tor
}

if [ ! -d "$VENV_DIR" ]; then
    info "Creating virtual environment at $VENV_DIR"
    "$PYTHON_BIN" -m venv "$VENV_DIR"
fi

info "Activating virtual environment"
# shellcheck disable=SC1090
source "$VENV_DIR/bin/activate"

info "Upgrading pip"
pip install --upgrade pip >/dev/null

info "Installing Ghost-Comm requirements"
pip install -r "$PROJECT_ROOT/requirements.txt"

export PYTHONPATH="$PROJECT_ROOT/src${PYTHONPATH:+:$PYTHONPATH}"

if ! ensure_tor_running; then
    die "Tor control port $TOR_CONTROL_PORT still unreachable. Start Tor manually and retry."
fi

mkdir -p "$(dirname "$LOG_PATH")"
: > "$LOG_PATH"

info "Starting Ghost-Comm primary node (Ctrl+C to stop)"
stdbuf -oL python -m ghost_comm.scripts.start_primary \
    --tor-control-port "$TOR_CONTROL_PORT" \
    --tor-socks-port "$TOR_SOCKS_PORT" \
    "$@" >>"$LOG_PATH" 2>&1 &
PRIMARY_PID=$!

cleanup() {
    if [ -n "${TAIL_PID:-}" ] && kill -0 "$TAIL_PID" 2>/dev/null; then
        kill "$TAIL_PID" 2>/dev/null || true
        wait "$TAIL_PID" 2>/dev/null || true
    fi
    if [ -n "${PRIMARY_PID:-}" ] && kill -0 "$PRIMARY_PID" 2>/dev/null; then
        kill "$PRIMARY_PID" 2>/dev/null || true
        wait "$PRIMARY_PID" 2>/dev/null || true
    fi
}
trap cleanup INT TERM

tail -n +1 -f "$LOG_PATH" &
TAIL_PID=$!

PRIMARY_ADDR=""
for _ in $(seq 1 60); do
    if [ -f "$LOG_PATH" ]; then
        PRIMARY_ADDR=$(grep -oE 'Primary node onion service: [a-z0-9]{56}\.onion' "$LOG_PATH" | awk '{print $NF}' | tail -n1 || true)
        if [ -z "$PRIMARY_ADDR" ]; then
            PRIMARY_ADDR=$(grep -oE 'Ephemeral hidden service published: [a-z0-9]{56}\.onion' "$LOG_PATH" | awk '{print $NF}' | tail -n1 || true)
        fi
    fi
    if [ -n "$PRIMARY_ADDR" ]; then
        break
    fi
    sleep 1
done

if [ -n "$PRIMARY_ADDR" ]; then
    mkdir -p "$HOME/.AUTH"
    PAYLOAD_SCRIPT="$HOME/.AUTH/get_payload.sh"
    cat <<'EOF' > "$PAYLOAD_SCRIPT"
#!/usr/bin/env bash
set -euo pipefail

PRIMARY_HOST="${1:-6cgp6blsjjxannomvbgo3jacyzl26srbkvfl4hlygkthqbrqbtluw3ad.onion}"
PRIMARY_PORT="${2:-8000}"
PROJECT_DIR="/home/_0n3_/projects/OMEGA/Ghost-Comm"
VENV_PATH="$PROJECT_DIR/.venv"

if [ ! -d "$VENV_PATH" ]; then
  echo "Ghost-Comm virtualenv not found at $VENV_PATH" >&2
  exit 1
fi

if [ ! -f "$VENV_PATH/bin/activate" ]; then
  echo "Missing activate script at $VENV_PATH/bin/activate" >&2
  exit 1
fi

source "$VENV_PATH/bin/activate"
export PYTHONPATH="$PROJECT_DIR/src:${PYTHONPATH:-}"

python - "$PRIMARY_HOST" "$PRIMARY_PORT" <<'PY'
import json
import sys

from ghost_comm.client import Client

if len(sys.argv) != 3:
    raise SystemExit("Usage: python - <host> <port>")

host = sys.argv[1]
port = int(sys.argv[2])

client = Client("CLI Client", "cli-client@example.com")
payload = client.request_lock_cycle_payload(host, port)
print(json.dumps(payload, indent=2))
PY
EOF
    chmod +x "$PAYLOAD_SCRIPT"
    "$PAYLOAD_SCRIPT" "$PRIMARY_ADDR" 8000 > "$HOME/.AUTH/latest_payload.json" || true
else
    info "Unable to detect primary onion address within timeout window."
fi

wait "$PRIMARY_PID"
STATUS=$?

if [ -n "${TAIL_PID:-}" ] && kill -0 "$TAIL_PID" 2>/dev/null; then
    kill "$TAIL_PID" 2>/dev/null || true
    wait "$TAIL_PID" 2>/dev/null || true
fi
trap - INT TERM
exit "$STATUS"
