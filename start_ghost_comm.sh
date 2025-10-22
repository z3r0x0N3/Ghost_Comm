#!/usr/bin/env bash
# Bootstrap and launch the Ghost-Comm primary node.

set -euo pipefail

PROJECT_ROOT="${PROJECT_ROOT:-$HOME/projects/OMEGA/Ghost-Comm}"
VENV_DIR="${VENV_DIR:-$PROJECT_ROOT/.venv}"
PYTHON_BIN="${PYTHON_BIN:-python3}"

info() {
    printf '[info] %s\n' "$*"
}

die() {
    printf '[error] %s\n' "$*" >&2
    exit 1
}

command -v "$PYTHON_BIN" >/dev/null 2>&1 || die "python3 is required but was not found in PATH"

[ -d "$PROJECT_ROOT" ] || die "Ghost-Comm project not found at $PROJECT_ROOT"

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

info "Starting Ghost-Comm primary node (Ctrl+C to stop)"
exec python -m ghost_comm.scripts.start_primary "$@"

