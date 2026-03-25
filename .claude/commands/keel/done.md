---
name: keel:done
description: Run the KEEL done-gate — only passes when reality matches the declared goal and plan
allowed-tools:
  - Bash
---

```bash
keel done
```

Display the full output. If the gate blocks, explain what's failing and what the agent needs to do to unblock it (`keel delta`, `keel advance`, or `keel replan`).
