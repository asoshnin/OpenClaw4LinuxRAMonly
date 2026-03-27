# Requirements: Sprint 2 (The Architect & HITL Gates)

## [REQ-06] Discovery Interface
The Architect must be able to query the Librarian's state (`factory.db`) to retrieve agent metadata, pipeline topologies, and audit history.
- Scope: Read-only access to `agents`, `pipelines`, and `audit_logs` tables.
- Ref: Spec v1.3 [cite: 6.0 - Sprint 2 Discovery]

## [REQ-07] Hardened HITL Enforcement (One-Time Token)
All high-risk operations (e.g., writing new agent configs, modifying the database) must require a `verified_approval_token`.
- Scope: `deploy_agent`, `delete_resource`, `modify_pipeline`.
- Status: Critical Security Requirement.

## [REQ-08] Token Ephemerality (Burn-on-Read)
To prevent replay attacks or rogue autonomous loops, an approval token must be destroyed immediately after a single validation attempt.
- Logic: Valid = Success + Delete; Invalid = Failure + Delete.
- Status: Critical

## [REQ-09] Manual Token Generation
The generation of an approval token must be an out-of-band process initiated solely by the human Navigator via a dedicated shell command.
- Status: Mandatory [cite: 4.0 - Technical HITL Gates]
