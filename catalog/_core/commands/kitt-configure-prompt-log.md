---
description: Register the prompt-log Stop hook in this project's .claude/settings.json
---

Register the WOPR prompt-log Stop hook in this project. Idempotent; safe to re-run.

The hook appends one entry to `PROMPT_LOG.md` after every Claude Code response. Each entry includes the date, an 8-character session ID, the message index in the JSONL transcript, the user prompt collapsed to one line, and a one-line summary of the response. See `hooks/README.md` for full hook documentation.

**Preview without making changes:**

```
! uv run "${CLAUDE_PLUGIN_ROOT}/scripts/configure_prompt_log.py" --dry-run
```

**Apply:**

```
! uv run "${CLAUDE_PLUGIN_ROOT}/scripts/configure_prompt_log.py"
```

**Target a project other than the current directory:**

```
! uv run "${CLAUDE_PLUGIN_ROOT}/scripts/configure_prompt_log.py" --project-root /path/to/project
```

**After running:** Restart Claude Code for the Stop hook to take effect.

**What it does:**

1. Creates `PROMPT_LOG.md` at the project root if missing, with a header that explains the entry format and how to look up the full JSONL transcript for any entry.
2. Reads `.claude/settings.json` (creates it if missing), checks for duplicate hook registration, then appends the Stop hook entry. Existing settings and other hooks are preserved.

**Idempotent.** Re-running is safe. Already-completed steps are skipped and reported as `ok`.

**Required:** [uv](https://docs.astral.sh/uv/) on PATH; `configure_prompt_log.py` is stdlib-only, so `uv run` executes it directly with no project or dependency resolution needed.
