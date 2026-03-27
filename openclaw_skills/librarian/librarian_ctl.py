"""
Librarian Control Script - Agentic Factory on OpenClaw
Handles State Management, Airlock Security, and Database Engine
"""

import os
import sys
import argparse
import sqlite3
import logging
from datetime import datetime

# Resolve workspace root from config (never hardcode paths here)
try:
    from config import WORKSPACE_ROOT
except ImportError:
    sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
    from config import WORKSPACE_ROOT

# Optional Sprint 7 dependency: ObsidianBridge
try:
    _skills_root = os.path.dirname(os.path.dirname(__file__))
    if _skills_root not in sys.path:
        sys.path.insert(0, _skills_root)
    from obsidian_bridge import ObsidianBridge, VAULT_INGEST_MAX_BYTES
except ImportError:
    ObsidianBridge = None  # type: ignore
    VAULT_INGEST_MAX_BYTES = 50000

# Safety engine for vault ingestion
try:
    _lib_dir = os.path.dirname(__file__)
    if _lib_dir not in sys.path:
        sys.path.insert(0, _lib_dir)
    from safety_engine import SafetyDistillationEngine
except ImportError:
    SafetyDistillationEngine = None  # type: ignore

logger = logging.getLogger(__name__)


def validate_path(target_path: str) -> str:
    """[DES-02] Realpath validation for Airlock protection.

    Uses os.sep suffix guard to prevent prefix-collision attacks
    (e.g. ~/.openclaw/workspace_evil would not pass).
    """
    base_dir = str(WORKSPACE_ROOT)
    target_abs = os.path.realpath(target_path)
    if not (target_abs == base_dir or target_abs.startswith(base_dir + os.sep)):
        raise PermissionError(f"Airlock Breach: {target_abs} is outside {base_dir}")
    return target_abs

def init_db(db_path: str) -> None:
    """[DES-03] Database Schema & Initialization with WAL mode."""
    valid_db_path = validate_path(db_path)
    
    with sqlite3.connect(valid_db_path) as conn:
        cursor = conn.cursor()
        
        # SQLite Durability (WAL Mode)
        cursor.execute("PRAGMA journal_mode=WAL;")
        cursor.execute("PRAGMA synchronous=NORMAL;")
        
        # Agents Table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS agents (
                agent_id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                version TEXT DEFAULT '1.0',
                persona_hash TEXT,
                state_blob JSON,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
        """)
        
        # Pipelines Table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS pipelines (
                pipeline_id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                topology_json JSON,
                status TEXT CHECK(status IN ('active', 'archived', 'deprecated'))
            );
        """)
        
        # Audit Logs Table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS audit_logs (
                log_id INTEGER PRIMARY KEY AUTOINCREMENT,
                agent_id TEXT,
                pipeline_id TEXT,
                action TEXT,
                rationale TEXT,
                timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY(agent_id) REFERENCES agents(agent_id),
                FOREIGN KEY(pipeline_id) REFERENCES pipelines(pipeline_id)
            );
        """)
        conn.commit()


def bootstrap_factory(db_path: str) -> None:
    """[DES-04] Bootstrap Seed Script to insert initial system operation data."""
    valid_db_path = validate_path(db_path)
    
    with sqlite3.connect(valid_db_path) as conn:
        cursor = conn.cursor()
        
        # Initial system registration — base columns only
        # description and tool_names are populated by migrate_db (Sprint 5)
        cursor.execute("""
            INSERT OR IGNORE INTO agents (agent_id, name, version) VALUES
            ('kimi-orch-01', 'Mega-Orchestrator (Kimi)', '1.3'),
            ('lib-keeper-01', 'The Librarian', '1.0');
        """)
        
        cursor.execute("""
            INSERT OR IGNORE INTO pipelines (pipeline_id, name, status) VALUES 
            ('factory-core', 'System Core Operations', 'active');
        """)
        
        cursor.execute("""
            INSERT OR IGNORE INTO audit_logs (agent_id, pipeline_id, action, rationale) VALUES 
            ('lib-keeper-01', 'factory-core', 'BOOTSTRAP', 'Initial system seeding in Sprint 1');
        """)
        conn.commit()


def generate_registry(db_path: str, output_md_path: str) -> None:
    """[DES-05] Atomic Write Pattern implementation for Registry Generation."""
    valid_db_path = validate_path(db_path)
    valid_out_path = validate_path(output_md_path)
    
    with sqlite3.connect(valid_db_path) as conn:
        cursor = conn.cursor()
        # Include description and tool_names (added in Sprint 5 migration)
        cursor.execute("SELECT agent_id, name, version, description, tool_names FROM agents;")
        agents = cursor.fetchall()

        cursor.execute("SELECT pipeline_id, name, status FROM pipelines;")
        pipelines = cursor.fetchall()

    # Format data with YAML frontmatter
    registry_content = "---\n"
    registry_content += "type: registry\n"
    registry_content += "generated_by: The Librarian\n"
    registry_content += f"last_updated: {datetime.now().isoformat()}\n"
    registry_content += "---\n\n"

    registry_content += "# Agentic Factory Registry\n\n"

    registry_content += "## Active Agents\n\n"
    for agent_id, name, version, description, tool_names in agents:
        registry_content += f"- **{name}** (`{agent_id}`) - v{version}\n"
        if description:
            registry_content += f"  - *{description}*\n"
        if tool_names:
            registry_content += f"  - Tools: `{tool_names}`\n"

    registry_content += "\n## System Pipelines\n\n"
    for pipeline_id, name, status in pipelines:
        registry_content += f"- **{name}** (`{pipeline_id}`) - Status: {status}\n"
        
    temp_path = valid_out_path + ".tmp"
    
    # Write to temp file first for atomic replacement
    with open(temp_path, "w", encoding="utf-8") as f:
        f.write(registry_content)
        
    os.replace(temp_path, valid_out_path)


def ingest_vault_note(
    db_path: str,
    vault_path: str,
    is_sensitive: bool = False,
) -> int:
    """Read an Obsidian vault note and archive it into the vector memory (vec_passages).

    Security invariants (SKILL.md — Obsidian Bridge Policy):
      - vault_path is always ingested with source_type='external' (IPI risk same as web-clips).
      - is_sensitive flag ALWAYS propagated to archive_log (controls Ollama vs Gemini).
      - Notes over VAULT_INGEST_MAX_BYTES are rejected before any LLM call.
      - archive_log() exceptions are caught, logged as VAULT_INGEST_FAILED, then re-raised.
      - Obsidian unavailability raises RuntimeError (explicit Navigator action).

    Args:
        db_path:      Path to factory.db for audit logging.
        vault_path:   Relative path within vault (e.g. '30 - RESOURCES/note.md').
        is_sensitive: If True, uses local Ollama distillation; if False, uses Gemini.

    Returns:
        passage_id (int) on success.

    Raises:
        RuntimeError:     If Obsidian is not reachable.
        FileNotFoundError: If the note does not exist in the vault.
        ValueError:       If note exceeds VAULT_INGEST_MAX_BYTES.
    """
    valid_db = validate_path(db_path)

    # Lazy import to keep librarian_ctl independently runnable without obsidian_bridge installed
    if ObsidianBridge is None:
        raise RuntimeError(
            "obsidian_bridge module not found. Ensure Sprint 7 is installed."
        )

    bridge = ObsidianBridge()  # raises ValueError if API key missing / non-localhost

    # Read note — raises RuntimeError if Obsidian is down, FileNotFoundError if not found
    content = bridge.read_note(vault_path)

    # IPI size gate: reject oversized notes before any LLM call
    content_bytes = len(content.encode("utf-8"))
    if content_bytes > VAULT_INGEST_MAX_BYTES:
        raise ValueError(
            f"Vault note exceeds VAULT_INGEST_MAX_BYTES ({VAULT_INGEST_MAX_BYTES} bytes). "
            f"Note size: {content_bytes} bytes. Path: {vault_path!r}. "
            "Split the note before ingesting."
        )

    # Ingest via Safety Distillation Engine
    # source_type='external' is hardcoded — vault notes always scrubbed (SKILL.md rule 10)
    # is_sensitive is ALWAYS propagated (SKILL.md rule 9)
    if SafetyDistillationEngine is None:
        raise RuntimeError("safety_engine module not found. Cannot distill vault note.")
    try:
        engine = SafetyDistillationEngine()
        passage_id = engine.archive_log(
            db_path=valid_db,
            raw_source_id=vault_path,
            raw_log=content,
            is_sensitive=is_sensitive,
            source_type="external",
        )
    except Exception as ingest_err:
        # SKILL.md rule 12: log failure before re-raising
        try:
            with sqlite3.connect(valid_db) as conn:
                conn.execute(
                    "INSERT INTO audit_logs (action, rationale) VALUES (?, ?)",
                    (
                        "VAULT_INGEST_FAILED",
                        f"Failed to ingest {vault_path!r}: {ingest_err}",
                    ),
                )
                conn.commit()
        except Exception:
            pass  # audit failure must not suppress the original error
        raise

    # Audit success
    with sqlite3.connect(valid_db) as conn:
        conn.execute(
            "INSERT INTO audit_logs (action, rationale) VALUES (?, ?)",
            ("VAULT_INGEST", f"Ingested vault note: {vault_path!r}"),
        )
        conn.commit()

    logger.info("ingest_vault_note: archived %r as passage_id=%s", vault_path, passage_id)
    return passage_id


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Librarian Control Script CLI")
    subparsers = parser.add_subparsers(dest="command", required=True)
    
    init_parser = subparsers.add_parser("init", help="Initialize the database")
    init_parser.add_argument("db_path", type=str, help="Path to the SQLite database")
    
    bootstrap_parser = subparsers.add_parser("bootstrap", help="Bootstrap factory core schema")
    bootstrap_parser.add_argument("db_path", type=str, help="Path to the SQLite database")
    
    refresh_parser = subparsers.add_parser("refresh-registry", help="Refresh registry markdown file")
    refresh_parser.add_argument("db_path", type=str, help="Path to the SQLite database")
    refresh_parser.add_argument("output_md_path", type=str, help="Path to the output Markdown file")

    ingest_parser = subparsers.add_parser(
        "ingest-vault-note", help="Ingest an Obsidian vault note into the vector archive"
    )
    ingest_parser.add_argument("db_path", type=str, help="Path to the SQLite database")
    ingest_parser.add_argument(
        "vault_path", type=str,
        help="Relative vault path (e.g. '30 - RESOURCES/note.md')"
    )
    ingest_parser.add_argument(
        "--sensitive", action="store_true",
        help="Use local Ollama distillation (default: Gemini)"
    )
    
    args = parser.parse_args()
    
    try:
        if args.command == "init":
            init_db(args.db_path)
            print(f"Database initialized at {args.db_path}")
        elif args.command == "bootstrap":
            bootstrap_factory(args.db_path)
            print(f"Factory bootstrapped at {args.db_path}")
        elif args.command == "refresh-registry":
            generate_registry(args.db_path, args.output_md_path)
            print(f"Registry generated at {args.output_md_path}")
        elif args.command == "ingest-vault-note":
            try:
                pid = ingest_vault_note(
                    args.db_path, args.vault_path, is_sensitive=args.sensitive
                )
                print(f"Archived as passage_id={pid}")
            except FileNotFoundError as e:
                print(f"Note not found: {e}", file=sys.stderr)
                sys.exit(1)
            except RuntimeError as e:
                print(f"Obsidian is not running or not reachable: {e}", file=sys.stderr)
                sys.exit(1)
            except ValueError as e:
                print(f"Validation error: {e}", file=sys.stderr)
                sys.exit(1)
    except Exception as e:
        print(f"Error executing command '{args.command}': {e}", file=sys.stderr)
        sys.exit(1)
