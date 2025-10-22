#!/usr/bin/env bash
# Bootstrap and launch the Ghost-Comm primary node.

set -euo pipefail

PROJECT_ROOT="${PROJECT_ROOT:-$HOME/projects/OMEGA/Ghost-Comm}"
VENV_DIR="${VENV_DIR:-$PROJECT_ROOT/.venv}"
PYTHON_BIN="${PYTHON_BIN:-python3}"
TOR_CONTROL_PORT="${TOR_CONTROL_PORT:-9051}"
TOR_SOCKS_PORT="${TOR_SOCKS_PORT:-9050}"

info() {
    printf '[info] %s\n' "$*"
}

die() {
    printf '[error] %s\n' "$*" >&2
    exit 1
}

command -v "$PYTHON_BIN" >/dev/null 2>&1 || die "python3 is required but was not found in PATH"

[ -d "$PROJECT_ROOT" ] || die "Ghost-Comm project not found at $PROJECT_ROOT"

parse_cli_ports() {
    local i=0
    while [ $i -lt $# ]; do
        local arg="${!((i+1))}"
        case "${arg}" in
            --tor-control-port=*)
                TOR_CONTROL_PORT="${arg#*=}"
                ;;
            --tor-control-port)
                if [ $((i+2)) -le $# ]; then
                    TOR_CONTROL_PORT="${!((i+2))}"
                    i=$((i+1))
                fi
                ;;
            --tor-socks-port=*)
                TOR_SOCKS_PORT="${arg#*=}"
                ;;
            --tor-socks-port)
                if [ $((i+2)) -le $# ]; then
                    TOR_SOCKS_PORT="${!((i+2))}"
                    i=$((i+1))
                fi
                ;;
        esac
        i=$((i+1))
    done
}

parse_cli_ports "$@"

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

info "Starting Ghost-Comm primary node (Ctrl+C to stop)"
exec python -m ghost_comm.scripts.start_primary --tor-control-port "$TOR_CONTROL_PORT" --tor-socks-port "$TOR_SOCKS_PORT" "$@"
