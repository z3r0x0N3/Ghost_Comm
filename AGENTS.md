# Repository Guidelines

## Project Structure & Module Organization
Core application modules live under `src/`, with packages for `client`, `node`, `primary_node`, `network`, and `crypto`. The packaged entrypoint in `ghost_comm/` mirrors the top-level scripts and exposes `scripts/start_primary.py` for packaging or sandboxed execution. Runtime artifacts such as generated onion data and payloads land in `NODES/`, `.primary_onion`, and `.primary.log`; keep these out of version control. Shell helpers (`start_ghost_comm.sh`, `start_primary_node.sh`, `create_torsite.sh`) sit in the repository root alongside configuration assets (`GUI-index.html`, `GUI-style.css`, `payload.json`).

## Build, Test, and Development Commands
- `python3 -m venv .venv && source .venv/bin/activate`: provision a local virtual environment.
- `pip install -r requirements.txt`: install runtime dependencies (cryptography, pgpy, stem, pysocks).
- `./start_ghost_comm.sh`: bootstrap the venv (if needed), verify Tor connectivity, and launch the primary node entrypoint while streaming logs.
- `python -m ghost_comm.scripts.start_primary --tor-control-port 9051`: manual start for custom Tor endpoints.
- `python main.py`: run the end-to-end demo that exercises the primary node, client, and distributed node chain.

## Coding Style & Naming Conventions
Target Python 3.10+ syntax, four-space indentation, and PEP 8 defaults. Favor descriptive snake_case for modules, files, and functions; reserve UpperCamelCase for classes such as node controllers. Keep network- or crypto-facing helpers pure and reusable, and document tricky flows with brief comments adjacent to the code.

## Testing Guidelines
Add automated coverage under a new `tests/` package using `pytest`; name files `test_<module>.py` and mirror the structure of `src/`. Treat `python main.py` as the smoke test that should still pass after any change. When introducing network mutations, create isolated unit tests that mock Tor interactions and assert payload transformations. Aim to exercise new encryption layers and failure paths before opening a pull request.

## Commit & Pull Request Guidelines
Recent history shows automated `Auto backup: <timestamp>` commits. For human-authored changes, prefer concise, imperative summaries (≤72 characters) and expand motivation or validation in the body. Squash work-in-progress commits locally. Pull requests should link issues, summarize behavioral impact, note test coverage, and attach relevant logs or screenshots (e.g., onion address output) when behavior changes.

## Security & Configuration Tips
Never commit secrets, onion hostnames, or generated PGP material from `.tor/`, `NODES/`, or payload exports. Use `.gitignore` updates if new artifacts appear. Review shell scripts before running them with elevated privileges, especially `create_torsite.sh`, which modifies system Tor and Nginx configuration. Rotate Tor control credentials and payload keys whenever you share demo builds outside trusted environments.
