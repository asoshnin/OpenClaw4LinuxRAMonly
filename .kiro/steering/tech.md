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

## Configuration

- All secrets via environment variables (e.g., `GEMINI_API_KEY`)
- DB path passed as CLI argument to all tools — never hardcoded
- Workspace boundary enforced via `os.path.realpath()` in all file operations
