# OpenClaw Factory: Feature Review & Test Plan (V1.0)

## 1. Feature Baseline

Based on the ingestion of the `src/` directory, the following core features and structural components are baseline:

### 1.1. Core Logic & Routing
- **Class: `DynamicLLMRouter`** (`src/routing/dynamic_router.py`)
  - `__init__(local_model, cloud_model)`: Initializes routing with specified model strings.
  - `route_task(task_id, is_sensitive, min_model_tier)`: Core logic for deciding between local and cloud models based on data sensitivity.
- **Exception: `HITLRequiredException`** (`src/routing/dynamic_router.py`)
  - Custom exception raised to halt processing when sensitive data is routed to a cloud tier.

### 1.2. Configuration & Pathing
- **Module: `config.py`** (`src/config.py`)
  - `BASE_DIR`: Dynamically resolved project root.
  - `DB_DIR`: Absolute path to the database directory.
  - `WORKSPACE_DIR`: Absolute path to the agent workspace.
  - `FACTORY_DB_PATH`: Absolute path to the SQLite state database.

### 1.3. Agent & Registry Management
- **Librarian Integration** (`src/dashboard/librarian.py`)
  - `get_registry()`: Deterministic read of the assistant registry from Letta Core Memory.
  - `update_registry(registry)`: Write operations via agent messaging.
  - `save_version_snapshot(...)`: Archival of pre-edit resource states.
- **Architect Tools** (`src/openclaw_skills/architect/architect_tools.py`)
  - `validate_path(target_path)`: Airlock protection logic for workspace file access.
  - `search_factory(...)`: SQLite discovery for agents and pipelines.
  - `validate_token(provided_token)`: Burn-on-read HITL security gate.

---

## 2. Epistemic Sovereignty Tests

These tests verify the "Defense in Depth" mechanism ensuring sensitive data never reaches a cloud provider without explicit approval.

### 2.1. Sensitive Cloud Routing Block
- **Requirement**: `is_sensitive=True` + `min_model_tier='cloud'` must trigger a system halt.
- **Test Case**: Call `DynamicLLMRouter.route_task` with a mock task ID, `is_sensitive=True`, and `min_model_tier='cloud'`.
- **Expected Outcome**: Assert that `HITLRequiredException` is raised and the error message contains the string `[SYS-HALT]`.

### 2.2. Non-Sensitive Cloud Routing
- **Requirement**: Standard cloud routing for non-sensitive data should proceed.
- **Test Case**: Call `DynamicLLMRouter.route_task` with `is_sensitive=False` and `min_model_tier='cloud'`.
- **Expected Outcome**: Assert that the return value is the configured `cloud_model` string.

### 2.3. Local Sensitive Routing
- **Requirement**: Sensitive data remains local if the tier is correctly specified as 'local'.
- **Test Case**: Call `DynamicLLMRouter.route_task` with `is_sensitive=True` and `min_model_tier='local'`.
- **Expected Outcome**: Assert that the return value is the configured `local_model` string and no exception is raised.

---

## 3. Pathing & Initialization Tests

These tests verify the portability and structural integrity of the consolidated codebase.

### 3.1. Dynamic Root Resolution
- **Requirement**: `BASE_DIR` must resolve to the actual project root, not a hardcoded user path.
- **Test Case**: Import `BASE_DIR` from `src.config`.
- **Expected Outcome**: Assert that `BASE_DIR` is an absolute path ending in `agentic_factory`.

### 3.2. Subdirectory Parity
- **Requirement**: Database and Workspace paths must be children of the `BASE_DIR`.
- **Test Case**: Verify `DB_DIR` and `WORKSPACE_DIR`.
- **Expected Outcome**: Assert that both paths exist and are subdirectories of `BASE_DIR`.

### 3.3. Database Path Integrity
- **Requirement**: The `FACTORY_DB_PATH` must point exactly to the canonical SQLite file.
- **Test Case**: Check the value of `FACTORY_DB_PATH`.
- **Expected Outcome**: Assert the path matches `.../agentic_factory/database/factory.db`.

---

## 4. Execution Strategy

1. **Environment Setup**: All tests must be run with the project root in the `PYTHONPATH`.
2. **Framework**: Use `pytest` for automated execution.
3. **Sequence**: Pathing tests must pass before logic tests to ensure a stable environment.
