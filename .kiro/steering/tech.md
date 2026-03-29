---
inclusion: always
---

# Technology Stack

## Runtime

- **Python 3.10+** — primary language, synchronous execution only
- **SQLite** (WAL mode) — primary state store via `factory.db`
- **sqlite-vec** — vector extension for 768-dim embeddings (Faint Path semantic search)

## AI / Inference

- **Ollama** — local LLM serving (CPU-bound, air-gapped)
  - `nomic-embed-text` — 768-dim embeddings for Vector Archive
  - `nn-tsuzu/lfm2.5-1.2b-instruct` — lightweight local reasoning
- **Google Gemini API** (`google-generativeai`) — ONLY for non-sensitive log distillation via `safety_engine.py`

## Libraries (Approved)

| Library | Purpose |
|---|---|
| `sqlite-vec` | Vector storage and similarity search |
| `pyyaml` | YAML parsing for agent profiles |
| `ollama` (Python client) | Local LLM inference |
| `google-generativeai` | Cloud distillation (scrubbed logs only) |
| `tkinter` | HITL GUI popup (stdlib) |
| `argparse` | CLI interfaces (stdlib) |
| `logging` | Structured logging (stdlib) |
| `hashlib`, `secrets` | Burn-on-Read token generation (stdlib) |

## Explicitly Forbidden Dependencies

- No ORMs (SQLAlchemy, Tortoise, etc.) — use raw `sqlite3`
- No async frameworks (asyncio, aiohttp, FastAPI) — synchronous by design
- No Docker/Kubernetes — air-gapped local runtime
- No additional vector DBs (Chroma, Qdrant, Pinecone) — sqlite-vec is the single source of truth

## Just-in-Time Help (JITH)

- All CLI interactions must use dynamic `--help` discovery.
- **Invariant:** No hardcoded flags are allowed when invoking CLI tools; always leverage `--help` to safely discover arguments.

## Configuration

- All secrets via environment variables (e.g., `GEMINI_API_KEY`)
- DB path passed as CLI argument to all tools — never hardcoded
- Workspace boundary enforced via `os.path.realpath()` in all file operations

## Verified-Completion Invariant (Sovereign Verification Gate)

- **Database-First:** The `tasks` table in `factory.db` is the **master source of truth** for project status. No external file, comment, or verbal claim overrides it.
- **Invariant:** Antigravity MUST NOT mark a task as `complete` based solely on code changes. A task is only `complete` when ALL of the following have been satisfied:
  1. The code is written and merged.
  2. The corresponding test suite passes (must be demonstrated, not assumed).
  3. For high-stakes items: the Navigator provides an explicit "Sign Off" (HITL) before status is updated.
- **Invariant:** Every task status update written to the `tasks` table MUST include a non-empty `test_summary` field describing what was verified.
