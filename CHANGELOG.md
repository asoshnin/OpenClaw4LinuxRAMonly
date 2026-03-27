# Changelog

## 2026-03-16 — ade4a93 — fix(dashboard): fix PATCH agent tool_names response + clean up stale agent IDs

- Fixed PATCH /api/agents/{id} returning full tool dicts instead of name strings (now uses `_extract_tool_names()`)
- Fixed Librarian message format: all 6 POST calls now use `{"messages": [{"role": "user", "content": ...}]}` (Letta v0.16.6+)
- Fixed stale Librarian ID in `librarian.py` (was pointing to deleted agent)
- Cleaned up `agent_ids.py` — removed duplicate stale entries, kept only current IDs

## 2026-03-16 — ee4fc84 — feat(dashboard): add knowledge sources management to agent detail + connected agents display in source detail

- Complete frontend rewrite from Bootstrap 5 to Tailwind CSS dark-mode SPA
- Fixed localhost IPv6 resolution (bound uvicorn to 0.0.0.0 for LAN access)
- Fixed 500 error on agent detail (Letta returns tools as dicts, not strings)
- Fixed archival memory 404 (Letta v0.16.6+ uses `/archival-memory` not `/archival`)
- Fixed empty agent dropdown in Knowledge Assets (now includes all agent categories)
- Added Knowledge Sources section to agent detail modal (attach/detach sources per agent)
- Added Connected Agents display to source detail panel
- Added `GET /api/agents/{agent_id}/sources` backend endpoint
- Added `NoCacheAPIMiddleware` for Cache-Control headers on API responses
- Updated `factory_technical_manual.md` with LAN access and troubleshooting docs
