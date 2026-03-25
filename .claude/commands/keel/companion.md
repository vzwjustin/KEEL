---
name: keel:companion
description: Manage the KEEL background companion — start, stop, or check status
argument-hint: "[start|stop|status]"
allowed-tools:
  - Bash
---

Run the companion subcommand from $ARGUMENTS (default: status):

```bash
keel companion ${ARGUMENTS:-status}
```

Display the output. If starting: confirm it launched and show the PID. If stopping: confirm it exited. If status: show alive/dead, heartbeat age, and whether it's fresh.
