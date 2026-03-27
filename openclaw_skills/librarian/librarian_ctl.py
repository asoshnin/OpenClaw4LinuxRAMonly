"""
Librarian Control Script - Agentic Factory on OpenClaw
Handles State Management, Airlock Security, and Database Engine
"""

import os
import sys
import argparse
import sqlite3
import json
import yaml
from datetime import datetime

def validate_path(target_path: str) -> str:
    """[DES-02] Realpath validation for Airlock protection."""
    base_dir = os.path.realpath("/home/alexey/openclaw-inbox/workspace/")
    target_abs = os.path.realpath(target_path)
    if not target_abs.startswith(base_dir):
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
        
        # Initial system registration
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
        cursor.execute("SELECT agent_id, name, version FROM agents;")
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
    for agent_id, name, version in agents:
        registry_content += f"- **{name}** (`{agent_id}`) - v{version}\n"
    
    registry_content += "\n## System Pipelines\n\n"
    for pipeline_id, name, status in pipelines:
        registry_content += f"- **{name}** (`{pipeline_id}`) - Status: {status}\n"
        
    temp_path = valid_out_path + ".tmp"
    
    # Write to temp file first for atomic replacement
    with open(temp_path, "w", encoding="utf-8") as f:
        f.write(registry_content)
        
    os.replace(temp_path, valid_out_path)


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
    except Exception as e:
        print(f"Error executing command '{args.command}': {e}", file=sys.stderr)
        sys.exit(1)
