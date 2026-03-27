"""
obsidian_vault_bootstrap.py — Idempotent Johnny.Decimal folder initialisation.

Creates the mandatory vault folder structure before the Obsidian Local REST API
is available (i.e., before Obsidian is running). This is the ONLY direct
filesystem operation in the Obsidian integration — all subsequent note I/O
goes through obsidian_bridge.py.

Johnny.Decimal taxonomy (per the Navigator's vault architecture):
  00 - INBOX        → Raw captures, mobile dumps, OpenClaw agent output
  10 - PROJECTS     → Active work with defined deadlines
  20 - AREAS        → Ongoing domains (Health, Finance, Research)
  30 - RESOURCES    → Evergreen reference material
  40 - ARCHIVE      → Completed / deprecated (excluded from AI index)
  90 - TEMPLATES    → Note templates
  99 - META         → Dashboards, AI logs, system notes
"""

import os
import sys
import logging
import argparse

logger = logging.getLogger(__name__)

JOHNNY_DECIMAL_FOLDERS = [
    "00 - INBOX",
    "00 - INBOX/openclaw",   # OpenClaw agent output sub-folder
    "10 - PROJECTS",
    "20 - AREAS",
    "30 - RESOURCES",
    "40 - ARCHIVE",
    "90 - TEMPLATES",
    "99 - META",
]


def setup_vault_structure(vault_path: str) -> None:
    """Create the Johnny.Decimal folder structure inside the given vault root.

    Idempotent — safe to run multiple times (uses exist_ok=True).
    Does NOT require Obsidian to be running.

    Args:
        vault_path: Absolute path to the vault root directory.

    Raises:
        FileNotFoundError: If vault_path does not exist.
        ValueError:        If vault_path is not absolute or is empty.
    """
    if not vault_path or not os.path.isabs(vault_path):
        raise ValueError(
            f"vault_path must be an absolute path. Got: {vault_path!r}. "
            "Set OBSIDIAN_VAULT_PATH to the full path of your vault directory."
        )

    if not os.path.exists(vault_path):
        raise FileNotFoundError(
            f"Vault directory does not exist: {vault_path!r}. "
            "Create the vault directory first, or open Obsidian to create a new vault."
        )

    created = []
    existing = []
    for folder in JOHNNY_DECIMAL_FOLDERS:
        full_path = os.path.join(vault_path, folder)
        if os.path.exists(full_path):
            logger.debug("Vault folder already exists (skipping): %s", full_path)
            existing.append(folder)
        else:
            os.makedirs(full_path, exist_ok=True)
            logger.info("Created vault folder: %s", full_path)
            created.append(folder)

    if created:
        print(f"[VAULT] Created {len(created)} folder(s): {', '.join(created)}")
    if existing:
        print(f"[VAULT] Already existed ({len(existing)} folder(s)) — no changes needed.")
    print(f"[VAULT] Johnny.Decimal structure ready at: {vault_path}")


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    parser = argparse.ArgumentParser(
        description="Bootstrap the Johnny.Decimal folder structure in an Obsidian vault."
    )
    parser.add_argument(
        "vault_path",
        nargs="?",
        default=os.environ.get("OBSIDIAN_VAULT_PATH", ""),
        help="Absolute path to vault root (defaults to OBSIDIAN_VAULT_PATH env var)",
    )
    args = parser.parse_args()

    if not args.vault_path:
        print(
            "ERROR: vault_path argument is required, or set OBSIDIAN_VAULT_PATH env var.",
            file=sys.stderr,
        )
        sys.exit(1)

    try:
        setup_vault_structure(args.vault_path)
    except (FileNotFoundError, ValueError) as e:
        print(f"ERROR: {e}", file=sys.stderr)
        sys.exit(1)
