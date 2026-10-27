---
description: Register the token-usage telemetry Stop hook in this project's .claude/settings.json
---

Register the KITT token-usage Stop hook in this project. Idempotent; safe to re-run.

The hook fires at the end of every turn, reads Claude Code's own transcript, and recomputes the session's per-tool token attribution into `~/.kitt/token-usage.json` (override with `TOKEN_USAGE_SIDECAR`). Per-turn usage totals are exact; per-tool figures are an attribution (a turn's tokens are shared by everything in it), with the estimation rules documented in the handler's docstring. It records tool **names, counts, and token figures only** — never prompt text, tool inputs, file paths, or result bodies.

**Why you need it:** cost per crew run is otherwise a guess. Token usage is reported per model turn, never per tool; this hook joins turns to tool calls so "which tools burned the tokens" is answerable from data instead of estimated after the fact. The companion reader renders the sidecar: `python3 "${CLAUDE_PLUGIN_ROOT}/hooks/token-usage-report.py"`.

**Preview without making changes:**

```
! uv run --project "${CLAUDE_PLUGIN_ROOT}/server" python "${CLAUDE_PLUGIN_ROOT}/scripts/configure_hook.py" --hook token-usage --cli claude --dry-run
```

**Apply:**

```
! uv run --project "${CLAUDE_PLUGIN_ROOT}/server" python "${CLAUDE_PLUGIN_ROOT}/scripts/configure_hook.py" --hook token-usage --cli claude
```

After applying, restart the session (hooks load at startup). Verify with `/hooks` or by checking `.claude/settings.json` for the `token-usage-hook.py` entry.
