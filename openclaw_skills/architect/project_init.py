"""
project_init.py — factory-init CLI (PR-06)
==========================================
Initializes a new OpenClaw Project Silo in a target directory.

Workflow:
  1. Pre-flight guard: abort if .factory_anchor or project.db already exist
     (unless --force is passed).
  2. Resolve absolute path via os.path.realpath() — required for uniqueness.
  3. Create directory structure: docs/, memory/, workspace/.
  4. Write .factory_anchor sentinel file.
  5. Initialize project.db using the shared initialize_project_schema() helper.
  6. Register the project in the Global Hub projects table (factory.db).

Security:
  - All paths pass through os.path.realpath() before use.
  - parent_project_id is validated against the Global Registry before insert.
  - No shell=True anywhere.
"""

from __future__ import annotations

import argparse
import logging
import os
import sqlite3
import sys
import uuid
from pathlib import Path

# ---------------------------------------------------------------------------
# Bootstrap import path
# ---------------------------------------------------------------------------
_REPO_ROOT = Path(__file__).resolve().parent.parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from openclaw_skills.config import (  # noqa: E402
    FACTORY_ANCHOR,
    GLOBAL_DB_PATH,
    find_project_root,
)
from openclaw_skills.librarian.db_utils import initialize_project_schema  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(levelname)s  %(message)s")
log = logging.getLogger("factory_init")

# ---------------------------------------------------------------------------
# Pre-flight guard
# ---------------------------------------------------------------------------

class ProjectAlreadyInitialized(RuntimeError):
    """Raised when the target directory already contains a project."""


def _preflight_check(target: Path, force: bool) -> None:
    """Abort if anchor or project.db already exist, unless --force given."""
    anchor = target / FACTORY_ANCHOR
    project_db = target / "workspace" / "project.db"

    collisions = []
    if anchor.exists():
        collisions.append(str(anchor))
    if project_db.exists():
        collisions.append(str(project_db))

    if collisions and not force:
        raise ProjectAlreadyInitialized(
            f"Project already initialized in '{target}'. "
            f"Conflicting files: {collisions}. "
            "Use --force to overwrite (destructive)."
        )
    if collisions and force:
        log.warning("--force active: overwriting existing project files in '%s'.", target)


# ---------------------------------------------------------------------------
# Directory provisioning
# ---------------------------------------------------------------------------

def _provision_dirs(target: Path) -> None:
    """Create standard project directory layout."""
    for subdir in ("docs", "memory", "workspace"):
        (target / subdir).mkdir(parents=True, exist_ok=True)
    log.info("Provisioned directory layout in '%s'.", target)


# ---------------------------------------------------------------------------
# Global Registry helpers
# ---------------------------------------------------------------------------

def _validate_parent(global_db: Path, parent_id: str) -> None:
    """Raise ValueError if parent_project_id does not exist in the registry."""
    conn = sqlite3.connect(global_db)
    row = conn.execute(
        "SELECT id FROM projects WHERE id=?", (parent_id,)
    ).fetchone()
    conn.close()
    if row is None:
        raise ValueError(
            f"parent_project_id '{parent_id}' does not exist in the Global "
            f"Registry ({global_db}). Register the parent first."
        )


def _ensure_projects_table(conn: sqlite3.Connection) -> None:
    """Create the projects table in the Global Hub if it doesn't exist."""
    conn.execute("PRAGMA foreign_keys=ON;")
    conn.execute("""
        CREATE TABLE IF NOT EXISTS projects (
            id                TEXT PRIMARY KEY,
            name              TEXT NOT NULL,
            root_path         TEXT UNIQUE NOT NULL,
            parent_project_id TEXT REFERENCES projects(id) ON DELETE SET NULL,
            created_at        TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
    """)
    conn.commit()
    log.info("projects table ready in Global Hub.")


def _register_in_global_hub(
    global_db: Path,
    project_id: str,
    name: str,
    root_path: str,
    parent_project_id: str | None,
) -> None:
    """Insert the new project record into the Global Hub projects table."""
    conn = sqlite3.connect(global_db)
    conn.execute("PRAGMA journal_mode=WAL;")
    conn.execute("PRAGMA foreign_keys=ON;")
    _ensure_projects_table(conn)

    conn.execute("""
        INSERT OR REPLACE INTO projects (id, name, root_path, parent_project_id)
        VALUES (?, ?, ?, ?)
    """, (project_id, name, root_path, parent_project_id))
    conn.commit()
    conn.close()
    log.info("Registered project '%s' (%s) in Global Hub.", name, project_id)


# ---------------------------------------------------------------------------
# Core init function (importable for tests)
# ---------------------------------------------------------------------------

def init_project(
    target_dir: str | Path,
    name: str,
    parent_project_id: str | None = None,
    global_db: Path | None = None,
    force: bool = False,
) -> dict:
    """Initialize a new Project Silo.

    Args:
        target_dir:        Directory to initialize (will be created if absent).
        name:              Human-readable project name.
        parent_project_id: Optional UUID of a parent project in the Global Hub.
        global_db:         Path to the Global Hub factory.db.
                           Defaults to config.GLOBAL_DB_PATH.
        force:             If True, overwrite existing project files.

    Returns:
        dict with keys: 'project_id', 'root_path', 'project_db', 'global_db'.

    Raises:
        ProjectAlreadyInitialized: If silo already exists and force=False.
        ValueError:               If parent_project_id doesn't exist in registry.
        FileNotFoundError:        If target_dir doesn't exist and can't be created.
    """
    global_db = global_db or GLOBAL_DB_PATH

    # Resolve and normalize target path (Path Invariant)
    target = Path(os.path.realpath(str(target_dir)))

    # Pre-flight guard
    _preflight_check(target, force)

    # Validate parent linkage before doing any filesystem work
    if parent_project_id:
        _validate_parent(global_db, parent_project_id)

    # Provision filesystem layout
    target.mkdir(parents=True, exist_ok=True)
    _provision_dirs(target)

    # Write .factory_anchor
    anchor = target / FACTORY_ANCHOR
    anchor.write_text(
        f"# OpenClaw Project Anchor\nname: {name}\n", encoding="utf-8"
    )
    log.info("Wrote .factory_anchor to '%s'.", anchor)

    # Initialize project.db with shared schema
    project_db = target / "workspace" / "project.db"
    conn = sqlite3.connect(project_db)
    initialize_project_schema(conn)
    conn.close()
    log.info("Initialized project.db at '%s'.", project_db)

    # Root path string — normalized via realpath (uniqueness invariant)
    root_path_str = str(target)

    # Register in Global Hub
    project_id = str(uuid.uuid4())
    _register_in_global_hub(global_db, project_id, name, root_path_str, parent_project_id)

    return {
        "project_id": project_id,
        "root_path":  root_path_str,
        "project_db": str(project_db),
        "global_db":  str(global_db),
    }


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="factory-init",
        description="Initialize a new OpenClaw Project Silo.",
    )
    p.add_argument("target_dir", type=str, help="Directory to initialize as a project silo.")
    p.add_argument("--name", required=True, help="Human-readable project name.")
    p.add_argument(
        "--parent", default=None, metavar="PROJECT_UUID",
        help="UUID of parent project in the Global Hub (for nested silos).",
    )
    p.add_argument(
        "--global-db", default=None, type=Path,
        help=f"Path to Global Hub factory.db (default: {GLOBAL_DB_PATH})",
    )
    p.add_argument(
        "--force", action="store_true",
        help="Overwrite existing project files (destructive).",
    )
    return p


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)

    try:
        result = init_project(
            target_dir=args.target_dir,
            name=args.name,
            parent_project_id=args.parent,
            global_db=args.global_db,
            force=args.force,
        )
    except ProjectAlreadyInitialized as e:
        log.error("ABORT: %s", e)
        return 1
    except ValueError as e:
        log.error("ABORT: %s", e)
        return 1
    except Exception as e:
        log.error("Unexpected error: %s", e)
        raise

    log.info("Project initialized successfully.")
    log.info("  Project ID : %s", result["project_id"])
    log.info("  Root path  : %s", result["root_path"])
    log.info("  project.db : %s", result["project_db"])
    log.info("  Global Hub : %s", result["global_db"])
    return 0


if __name__ == "__main__":
    sys.exit(main())
