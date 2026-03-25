---
name: keel:drift
description: Detect drift between the active plan and current repo state
allowed-tools:
  - Bash
---

```bash
keel drift
```

Display the full output. Highlight any high-confidence or deterministic drift signals. If drift is found, suggest the appropriate recovery action (`keel recover`, `keel replan`, or `keel advance`).
