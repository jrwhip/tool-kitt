---
description: Register the skill-usage telemetry Stop hook in this project's .claude/settings.json
---

Register the WOPR skill-usage Stop hook in this project. Idempotent; safe to re-run.

The hook fires at the end of every turn, reads Claude Code's own transcript, and counts native `Skill` tool invocations into WOPR's usage sidecar (`~/.wopr/skill-usage.json`) by shelling out to `wopr skill-usage record`. It records skill **names and counts only** — never prompt text, arguments, or file paths.

**Why you need it:** without this hook, WOPR only ever sees skills loaded through its `run_skill` MCP tool. Claude Code invokes skills natively, so on Claude Code the numbers are close to zero no matter how heavily the skills are used. This hook closes that gap. It does not close the Copilot or Gemini gap — nothing does today. See `docs/skill-usage-telemetry.md` for the full coverage boundary before you act on any number.

**Preview without making changes:**

```
! WOPR_DIR=$(python3 -c "import wopr, pathlib; print(pathlib.Path(wopr.__file__).parent / 'resources')") && python3 "$WOPR_DIR/meta-authoring/scripts/configure_hook.py" --hook skill-usage --cli claude --dry-run
```

**Apply:**

```
! WOPR_DIR=$(python3 -c "import wopr, pathlib; print(pathlib.Path(wopr.__file__).parent / 'resources')") && python3 "$WOPR_DIR/meta-authoring/scripts/configure_hook.py" --hook skill-usage --cli claude
```

**Target a project other than the current directory:**

```
! WOPR_DIR=$(python3 -c "import wopr, pathlib; print(pathlib.Path(wopr.__file__).parent / 'resources')") && python3 "$WOPR_DIR/meta-authoring/scripts/configure_hook.py" --hook skill-usage --cli claude --project-root /path/to/project
```

**After running:** Restart Claude Code for the Stop hook to take effect.

**What it does:**

Reads `.claude/settings.json` (creates it if missing) and appends the Stop hook entry. All other settings and hooks are preserved.

**Reading the data:** `wopr skill-usage report` from a terminal, or the `skill_usage_report` MCP tool in a session. Mark a deliberately-rare skill with `wopr skill-usage pin <name>` (or the `pin_skill` tool) so it is never labelled stale.

**Idempotent.** Re-running is safe. Already-registered hooks are reported as `ok`.

**Required:** WOPR must be installed (`pipx install wopr` or equivalent) so the `wopr` package is importable and `wopr` is on PATH. The hook is a silent no-op when `wopr` is not on PATH.
