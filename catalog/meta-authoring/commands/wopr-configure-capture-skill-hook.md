---
description: Register the capture-skill-trigger Stop hook in this project's .claude/settings.json
---

Register the WOPR capture-skill-trigger Stop hook in this project. Idempotent; safe to re-run.

The hook fires at the end of every turn. Once a session has crossed a threshold of tool calls since the last check (default 8), it injects a nudge asking the agent to consider running `wopr-capture-skill` if the stretch of work produced a genuinely hard-won, reusable lesson. It does not capture anything itself and does not force a stop — it puts the question in front of the agent instead of relying on a human remembering to say "capture this." The hook is a silent no-op wherever `wopr-capture-skill` is not installed (project-local `.claude/skills/` or user-level `~/.claude/skills/`), so it is safe to register globally.

**Preview without making changes:**

```
! WOPR_DIR=$(python3 -c "import wopr, pathlib; print(pathlib.Path(wopr.__file__).parent / 'resources')") && python3 "$WOPR_DIR/meta-authoring/scripts/configure_hook.py" --hook capture-skill-trigger --cli claude --dry-run
```

**Apply:**

```
! WOPR_DIR=$(python3 -c "import wopr, pathlib; print(pathlib.Path(wopr.__file__).parent / 'resources')") && python3 "$WOPR_DIR/meta-authoring/scripts/configure_hook.py" --hook capture-skill-trigger --cli claude
```

**Target a project other than the current directory:**

```
! WOPR_DIR=$(python3 -c "import wopr, pathlib; print(pathlib.Path(wopr.__file__).parent / 'resources')") && python3 "$WOPR_DIR/meta-authoring/scripts/configure_hook.py" --hook capture-skill-trigger --cli claude --project-root /path/to/project
```

**After running:** Restart Claude Code for the Stop hook to take effect.

**What it does:**

Reads `.claude/settings.json` (creates it if missing) and appends the Stop hook entry. All other settings and hooks are preserved.

**Customizing the threshold:** the hook honors the `CAPTURE_SKILL_HOOK_THRESHOLD` environment variable (tool calls since the last nudge required to fire again; default 8). Set it in your shell profile or in the `env` block of the project's `.claude/settings.json`.

**Idempotent.** Re-running is safe. Already-registered hooks are reported as `ok`.

**Required:** WOPR must be installed (`pipx install wopr` or equivalent) so the `wopr` package is importable. The `python3 -c` shim resolves the meta-authoring scripts directory regardless of where WOPR was installed.
