---
description: Regenerate the REGISTRY.md file after modifying agents or pipelines in factory.db
---
# Refresh OpenClaw Registry

When there have been changes to the agents or pipelines in `factory.db`, the `REGISTRY.md` file must be regenerated automatically. Do not edit `REGISTRY.md` by hand.

1. Find the path to the workspace's `factory.db`.
2. Run the `librarian_ctl.py` script with the `refresh-registry` command:

```bash
python3 openclaw_skills/librarian/librarian_ctl.py refresh-registry /path/to/workspace/factory.db ./REGISTRY.md
```

3. Ensure that the updated `REGISTRY.md` is included in any subsequent commits.
