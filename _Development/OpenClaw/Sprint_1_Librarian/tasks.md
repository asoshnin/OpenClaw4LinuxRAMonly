# Tasks: Sprint 1 (The Librarian)

- [ ] **Step 1: Setup Environment**
  - Create `/home/alexey/openclaw-inbox/workspace/` (if missing).
  - Initialize `librarian_ctl.py` with standard imports.
  - *Ref: [DES-01]*

- [ ] **Step 2: Implement Security**
  - Code the `validate_path()` function using `os.path.realpath`.
  - *Ref: [DES-02], Realizes: [REQ-02]*

- [ ] **Step 3: Database Engine**
  - Create `init_db()` with WAL mode pragmas.
  - Implement DDL schema creation.
  - *Ref: [DES-03], Realizes: [REQ-01], [REQ-03]*

- [ ] **Step 4: Bootstrap Seeding**
  - Implement the `bootstrap_factory()` function to execute seed SQL.
  - *Ref: [DES-04], Realizes: [REQ-05]*

- [ ] **Step 5: Registry Generation**
  - Implement `generate_registry()` with atomic write pattern.
  - Ensure YAML frontmatter is included.
  - *Ref: [DES-05], Realizes: [REQ-04]*

- [ ] **Step 6: CLI Interface**
  - Add basic CLI commands: `init`, `bootstrap`, `refresh-registry`.
