"""
sync_openclaw_artifacts.py — LIB-01.1 Scanner

Indexes Factory-managed and OpenClaw-native artifacts into factory.db.

Security invariants:
  - Symlinks are ALWAYS skipped (prevents path-traversal / infinite loops).
  - OpenClaw native artifacts are prefixed with 'openclaw::' and marked is_readonly=1.
  - Factory artifacts use source='agentic_factory', is_readonly=0.
  - All paths resolved via os.path.realpath() before storage.
  - Read-only guard: any call to upsert an artifact with is_readonly=1 (by name)
    that isn't coming from this scanner is blocked by the guard in librarian_ctl.py.

Usage:
    python3 openclaw_skills/librarian/sync_openclaw_artifacts.py workspace/factory.db [--dry-run]
"""

import os
import sys
import json
import sqlite3
import logging
import argparse
from typing import List, Tuple

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO, format="%(levelname)s  %(message)s")

# ── Path resolution ───────────────────────────────────────────────────────────

_HERE = os.path.dirname(os.path.abspath(__file__))
_SKILLS_ROOT = os.path.dirname(_HERE)  # openclaw_skills/
_PROJECT_ROOT = os.path.dirname(_SKILLS_ROOT)  # agentic_factory/


def _resolve_native_openclaw_paths() -> List[str]:
    """
    Dynamically resolve paths for OpenClaw native skill/agent workspaces.

    Priority:
      1. OPENCLAW_HOME env var  → {OPENCLAW_HOME}/workspace/skills/, agents/
      2. ~/.openclaw/openclaw.json config  → read gateway.stateDir or workspace path
      3. Hardcoded fallback: ~/.openclaw/workspace/skills/, ~/.openclaw/workspace/agents/
         AND ~/.openclaw/agents/ (common layout in v2026+)

    Symlinks are NOT followed — caller must use os.path.islink() guard.
    """
    candidates: List[str] = []

    # 1. OPENCLAW_HOME env var
    oc_home = os.environ.get("OPENCLAW_HOME", "")
    if oc_home:
        candidates += [
            os.path.join(oc_home, "workspace", "skills"),
            os.path.join(oc_home, "workspace", "agents"),
        ]

    # 2. Parse ~/.openclaw/openclaw.json for state dir
    config_path = os.path.expanduser("~/.openclaw/openclaw.json")
    if os.path.isfile(config_path) and not os.path.islink(config_path):
        try:
            with open(config_path, "r", encoding="utf-8") as f:
                config = json.load(f)
            # openclaw.json may contain gateway.stateDir or a top-level stateDir
            state_dir = (
                config.get("gateway", {}).get("stateDir")
                or config.get("stateDir")
                or ""
            )
            if state_dir:
                candidates += [
                    os.path.join(state_dir, "skills"),
                    os.path.join(state_dir, "agents"),
                ]
        except (json.JSONDecodeError, OSError) as e:
            logger.warning("Could not parse openclaw.json: %s", e)

    # 3. Hardcoded fallback paths (v2026 layout)
    oc_base = os.path.expanduser("~/.openclaw")
    candidates += [
        os.path.join(oc_base, "workspace", "skills"),
        os.path.join(oc_base, "workspace", "agents"),
        os.path.join(oc_base, "agents"),      # v2026 layout
        os.path.join(oc_base, "extensions"),  # v2026: plugins/skills live here
    ]

    # Deduplicate while preserving order
    seen = set()
    unique: List[str] = []
    for p in candidates:
        rp = os.path.realpath(p)
        if rp not in seen:
            seen.add(rp)
            unique.append(p)

    return unique


def _scan_directory(
    root: str,
    name_prefix: str = "",
    source: str = "agentic_factory",
    is_readonly: int = 0,
    extensions: Tuple[str, ...] = (".md", ".py", ".json", ".yaml", ".yml"),
) -> List[dict]:
    """
    Walk a directory tree and collect artifact metadata.

    Security:
      - Symlinks are ALWAYS skipped (both files and directories).
      - Only files matching `extensions` are included.

    Returns a list of dicts suitable for DB insertion.
    """
    results: List[dict] = []

    if not os.path.isdir(root) or os.path.islink(root):
        logger.debug("_scan_directory: skipping non-directory or symlink: %s", root)
        return results

    for dirpath, dirnames, filenames in os.walk(root):
        # Skip symlinked subdirectories in-place (prevents recursion into loops)
        dirnames[:] = [
            d for d in dirnames
            if not os.path.islink(os.path.join(dirpath, d))
        ]

        for fname in filenames:
            full_path = os.path.join(dirpath, fname)

            # Skip symlinked files
            if os.path.islink(full_path):
                logger.debug("Skipping symlink: %s", full_path)
                continue

            _, ext = os.path.splitext(fname)
            if ext.lower() not in extensions:
                continue

            stem = os.path.splitext(fname)[0]
            artifact_name = f"{name_prefix}{stem}" if name_prefix else stem
            real_path = os.path.realpath(full_path)

            results.append({
                "name": artifact_name,
                "artifact_type": ext.lstrip("."),
                "path": real_path,
                "description": f"Discovered from {os.path.relpath(full_path, root)}",
                "source": source,
                "is_readonly": is_readonly,
            })

    return results


def _upsert_artifacts(conn: sqlite3.Connection, artifacts: List[dict], dry_run: bool) -> Tuple[int, int]:
    """
    Insert or update artifacts in the DB.

    Returns (inserted_count, updated_count).
    """
    inserted = 0
    updated = 0

    for art in artifacts:
        existing = conn.execute(
            "SELECT id, is_readonly FROM artifacts WHERE name = ?",
            (art["name"],),
        ).fetchone()

        if existing:
            existing_id, existing_readonly = existing
            # Safety: never overwrite a readonly record with a non-readonly one
            if existing_readonly == 1 and art["is_readonly"] == 0:
                logger.warning(
                    "Skipping overwrite of readonly artifact '%s' with non-readonly data.",
                    art["name"],
                )
                continue

            if not dry_run:
                conn.execute(
                    """
                    UPDATE artifacts
                    SET artifact_type=?, path=?, description=?, source=?,
                        is_readonly=?, updated_at=CURRENT_TIMESTAMP
                    WHERE name=?
                    """,
                    (
                        art["artifact_type"], art["path"], art["description"],
                        art["source"], art["is_readonly"], art["name"],
                    ),
                )
            else:
                logger.info("[DRY-RUN] Would UPDATE artifact: %s", art["name"])
            updated += 1
        else:
            if not dry_run:
                conn.execute(
                    """
                    INSERT INTO artifacts (name, artifact_type, path, description, source, is_readonly)
                    VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (
                        art["name"], art["artifact_type"], art["path"],
                        art["description"], art["source"], art["is_readonly"],
                    ),
                )
            else:
                logger.info("[DRY-RUN] Would INSERT artifact: %s", art["name"])
            inserted += 1

    return inserted, updated


def sync_artifacts(db_path: str, dry_run: bool = False) -> dict:
    """
    Main sync entry point.

    1. Scans Factory-managed artifacts (openclaw_skills/)
    2. Scans OpenClaw native artifacts (skills/agents directories)
    3. Upserts all to factory.db artifacts table
    4. Returns a summary dict.

    Returns:
        {
          "factory_inserted": int, "factory_updated": int,
          "native_inserted": int,  "native_updated": int,
          "native_paths_scanned": list[str],
        }
    """
    if not os.path.exists(db_path):
        raise FileNotFoundError(f"Database not found: {db_path}")

    # ── Factory-managed artifacts (from openclaw_skills/) ────────────────────
    factory_artifacts: List[dict] = []
    skills_dir = os.path.join(_PROJECT_ROOT, "openclaw_skills")
    if os.path.isdir(skills_dir) and not os.path.islink(skills_dir):
        factory_artifacts = _scan_directory(
            root=skills_dir,
            name_prefix="",
            source="agentic_factory",
            is_readonly=0,
        )
        logger.info("Factory scan: %d artifacts found in %s", len(factory_artifacts), skills_dir)

    # ── OpenClaw native artifacts ─────────────────────────────────────────────
    native_paths = _resolve_native_openclaw_paths()
    native_artifacts: List[dict] = []
    scanned_native: List[str] = []

    for native_dir in native_paths:
        if os.path.isdir(native_dir) and not os.path.islink(native_dir):
            scanned_native.append(native_dir)
            found = _scan_directory(
                root=native_dir,
                name_prefix="openclaw::",
                source="openclaw_native",
                is_readonly=1,
            )
            native_artifacts.extend(found)
            logger.info("Native scan: %d artifacts in %s", len(found), native_dir)
        else:
            logger.debug("Native path not found or is symlink: %s", native_dir)

    # ── Upsert to DB ─────────────────────────────────────────────────────────
    with sqlite3.connect(db_path) as conn:
        factory_ins, factory_upd = _upsert_artifacts(conn, factory_artifacts, dry_run)
        native_ins, native_upd = _upsert_artifacts(conn, native_artifacts, dry_run)
        if not dry_run:
            conn.commit()

    summary = {
        "factory_inserted": factory_ins,
        "factory_updated": factory_upd,
        "native_inserted": native_ins,
        "native_updated": native_upd,
        "native_paths_scanned": scanned_native,
    }

    logger.info(
        "Sync complete — Factory: +%d upd=%d | Native: +%d upd=%d | Native dirs scanned: %d",
        factory_ins, factory_upd, native_ins, native_upd, len(scanned_native),
    )
    return summary


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="LIB-01.1: Sync factory + OpenClaw native artifacts into factory.db."
    )
    parser.add_argument("db_path", help="Path to factory.db")
    parser.add_argument(
        "--dry-run", action="store_true",
        help="Print what would be done without writing to the database."
    )
    args = parser.parse_args()

    try:
        summary = sync_artifacts(args.db_path, dry_run=args.dry_run)
        mode = "[DRY-RUN] " if args.dry_run else ""
        print(
            f"{mode}Sync complete.\n"
            f"  Factory artifacts  — inserted: {summary['factory_inserted']}, "
            f"updated: {summary['factory_updated']}\n"
            f"  Native artifacts   — inserted: {summary['native_inserted']}, "
            f"updated: {summary['native_updated']}\n"
            f"  Native paths scanned: {summary['native_paths_scanned']}"
        )
        sys.exit(0)
    except FileNotFoundError as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        import traceback
        traceback.print_exc()
        print(f"Sync failed: {e}", file=sys.stderr)
        sys.exit(1)
