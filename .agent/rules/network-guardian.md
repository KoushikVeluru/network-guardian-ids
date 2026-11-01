# Network Guardian workspace rules
- Authoritative spec: docs/MASTER_PROMPT.md. Read it fully at the start of every new session.
- Current status: docs/PROGRESS.md. Read it second. Do not redo completed phases.
- Decisions log: docs/DECISIONS.md.
- Never start a phase until the user says START PHASE N.
- Never fabricate data, metrics, columns or test results. Show real command output.
- The detection pipeline must never depend on an LLM.
- Ask before: sudo/apt, Docker or WSL config changes, deleting files, large downloads, git push, dependencies outside the approved stack.
