#!/usr/bin/env bash
set -euo pipefail

# Launch the Ghost-Comm primary node from the project root.
cd "$(dirname "${BASH_SOURCE[0]}")"
exec python3 -m ghost_comm.scripts.start_primary --tor-control-port 9051 "$@"
