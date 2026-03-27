---
inclusion: always
---

# Product Overview: OpenClaw for Linux

## Purpose

OpenClaw is a **hardened, self-evolving agentic operating system** built for Linux x86_64. Its core mission is **Epistemic Sovereignty**: the human Navigator (Alexey) retains cryptographically enforced control over every deployment decision via Human-in-the-Loop (HITL) gates. All sensitive AI inference runs locally — no cloud dependency for sensitive operations.

## Target Users

- Solo researcher/developer operating an air-gapped local AI infrastructure
- Hardware: ThinkPad W540 (x86_64, Linux, CPU-bound)
- Single Navigator: Alexey

## Key Product Goals

1. **Epistemic Sovereignty** — The human is always in control; no agent acts without explicit Navigator approval on deployments.
2. **RAM-Only Architecture** — All runtime state lives in SQLite WAL + sqlite-vec. No filesystem state outside the workspace boundary.
3. **Self-Evolution** — The system can provision new agents and pipelines into itself, but only through HITL-guarded workflows.
4. **Local-First Privacy** — Sensitive inference is CPU-bound and air-gapped. Cloud APIs (Gemini) are only used for scrubbed, non-sensitive log distillation.
5. **Resilience** — Self-healing parsers, schema migration support, and audit trails for every operation.

## Current Sprint Focus

See `_Development/OpenClaw/2026-03-27_backlog.md` for the live roadmap.
Next up: Dynamic LLM Router (HITL-Guarded), Static KB Injection, Self-Healing Parsers.
