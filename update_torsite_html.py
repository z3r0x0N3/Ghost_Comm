#!/usr/bin/env python3
"""
Utility to update the HTML served by a locally hosted Tor hidden service.

This script assumes the hidden services were created with `create_torsite.sh`,
which lays out directories under `NODES/torsite` like:

  tor_data_node1/
    hostname
    hs_ed25519_secret_key
    ...
  html_node1/
    index.html

Given an .onion address and an input HTML file, the script locates the matching
`tor_data_node*` directory and overwrites the sibling `html_node*` directory's
`index.html` file with the provided contents.
"""

from __future__ import annotations

import argparse
import os
from pathlib import Path
import shutil
import sys
from typing import Optional, Tuple


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Replace the HTML content for a local Tor hidden service created by "
            "create_torsite.sh."
        )
    )
    parser.add_argument(
        "onion_address",
        help="Target onion address (with or without the .onion suffix).",
    )
    parser.add_argument(
        "html_source",
        help="Path to the HTML file whose contents should be served.",
    )
    parser.add_argument(
        "--torsite-root",
        default=Path(__file__).resolve().parent / "NODES" / "torsite",
        type=Path,
        help=(
            "Root directory containing tor_data_* and html_* directories. "
            "Defaults to projects/Ghost_Comm/NODES/torsite."
        ),
    )
    parser.add_argument(
        "--output-name",
        default="index.html",
        help="Filename to create inside the html_* directory (default: index.html).",
    )
    parser.add_argument(
        "--backup",
        action="store_true",
        help="If set, keep a timestamped backup of the previous HTML file.",
    )
    return parser.parse_args()


def normalise_onion_address(onion: str) -> str:
    onion = onion.strip().lower()
    return onion if onion.endswith(".onion") else f"{onion}.onion"


def find_hidden_service_dirs(root: Path, onion_address: str) -> Optional[Tuple[Path, Path]]:
    if not root.is_dir():
        raise FileNotFoundError(f"Torsite root not found: {root}")

    for tor_dir in sorted(root.glob("tor_data_*")):
        hostname_path = tor_dir / "hostname"
        if not hostname_path.is_file():
            continue

        try:
            hostname = hostname_path.read_text(encoding="utf-8").strip().lower()
        except OSError as exc:
            raise RuntimeError(f"Failed to read hostname from {hostname_path}: {exc}") from exc

        if hostname == onion_address:
            # Try to align with create_torsite's naming (html_nodeX)
            suffix = tor_dir.name.replace("tor_data_", "", 1)
            html_dir = root / f"html_{suffix}"
            if not html_dir.is_dir():
                raise FileNotFoundError(
                    f"Matched {onion_address} but HTML directory missing: {html_dir}"
                )
            return tor_dir, html_dir

    return None


def backup_existing(html_path: Path) -> None:
    if not html_path.exists():
        return

    timestamp = html_path.stat().st_mtime_ns
    backup_path = html_path.with_suffix(html_path.suffix + f".bak.{timestamp}")
    shutil.copy2(html_path, backup_path)
    print(f"[+] Backed up existing file to {backup_path}")


def update_hidden_service_html(
    onion_address: str,
    html_source: Path,
    torsite_root: Path,
    output_name: str = "index.html",
    backup: bool = False,
) -> Path:
    if not html_source.is_file():
        raise FileNotFoundError(f"HTML source file not found: {html_source}")

    onion_address = normalise_onion_address(onion_address)
    torsite_root = torsite_root.expanduser().resolve()

    try:
        match = find_hidden_service_dirs(torsite_root, onion_address)
    except (FileNotFoundError, RuntimeError) as exc:
        raise RuntimeError(str(exc)) from exc

    if match is None:
        raise ValueError(f"Could not locate hidden service for {onion_address} under {torsite_root}")

    _, html_dir = match
    destination = html_dir / output_name

    if backup:
        backup_existing(destination)

    try:
        shutil.copyfile(html_source, destination)
    except OSError as exc:
        raise RuntimeError(f"Failed to copy {html_source} to {destination}: {exc}") from exc

    os.chmod(destination, 0o644)
    return destination


def main() -> int:
    args = parse_args()

    html_source = Path(args.html_source).expanduser().resolve()
    torsite_root = args.torsite_root

    try:
        destination = update_hidden_service_html(
            onion_address=args.onion_address,
            html_source=html_source,
            torsite_root=torsite_root,
            output_name=args.output_name,
            backup=args.backup,
        )
    except Exception as exc:
        print(f"[!] {exc}", file=sys.stderr)
        return 1

    print(f"[+] Updated {destination} with contents from {html_source}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
