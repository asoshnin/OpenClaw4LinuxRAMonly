# Requirements: Sprint 1 (The Librarian)

## [REQ-01] Persistent State Management
The system must use a local SQLite database (`factory.db`) for all agent and pipeline metadata to ensure long-term scalability and prevent Markdown bloat.
- Status: Mandatory
- Baseline: Spec v1.3 [cite: 5.1]

## [REQ-02] Hardened Airlock Security
All file operations performed by the Librarian must be cryptographically constrained.
- Enforcement: Use `os.path.realpath` to resolve symlinks.
- Constraint: Assert that the resolved path starts with `/home/alexey/openclaw-inbox/workspace/`.
- Status: Critical

## [REQ-03] SQLite Durability (WAL Mode)
To prevent database corruption during system crashes or power failures, SQLite must be configured with Write-Ahead Logging (WAL).
- Configuration: `PRAGMA journal_mode=WAL;` and `PRAGMA synchronous=NORMAL;`.
- Status: Mandatory

## [REQ-04] Atomic Markdown Generation
The Librarian must generate `REGISTRY.md` from the database state using atomic writes.
- Protocol: Write to `REGISTRY.md.tmp` first, then rename to `REGISTRY.md`.
- Status: Mandatory

## [REQ-05] Bootstrap Seeding
The first run of the Librarian must include a "Bootstrap Phase" to manually seed the `agents` and `pipelines` tables with the initial system profiles (Kimi and Librarian).
- Status: Mandatory
