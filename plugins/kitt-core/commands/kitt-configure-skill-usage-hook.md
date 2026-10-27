---
description: Register the skill-usage telemetry Stop hook in this project's .claude/settings.json
---

Register the KITT skill-usage Stop hook in this project. Idempotent; safe to re-run.

The hook fires at the end of every turn, reads Claude Code's own transcript, and counts native `Skill` tool invocations into KITT's usage sidecar (`~/.kitt/skill-usage.json`) by shelling out to `kitt skill-usage record`. It records skill **names and counts only** — never prompt text, arguments, or file paths.

**Why you need it:** this hook is the only writer of skill-usage telemetry. Claude Code invokes skills natively, invisible to any MCP-side counter, so without the hook every count reads zero no matter how heavily the skills are used. See the skill-usage telemetry doc (docs/skill-usage-telemetry.md in a repo checkout) for the full coverage boundary before you act on any number.

**Preview without making changes:**

```
! uv run --project "${CLAUDE_PLUGIN_ROOT}/server" python "${CLAUDE_PLUGIN_ROOT}/scripts/configure_hook.py" --hook skill-usage --cli claude --dry-run
```

**Apply:**

```
! uv run --project "${CLAUDE_PLUGIN_ROOT}/server" python "${CLAUDE_PLUGIN_ROOT}/scripts/configure_hook.py" --hook skill-usage --cli claude
```

**Target a project other than the current directory:**

```
! uv run --project "${CLAUDE_PLUGIN_ROOT}/server" python "${CLAUDE_PLUGIN_ROOT}/scripts/configure_hook.py" --hook skill-usage --cli claude --project-root /path/to/project
```

**After running:** Restart Claude Code for the Stop hook to take effect.

**What it does:**

Reads `.claude/settings.json` (creates it if missing) and appends the Stop hook entry. All other settings and hooks are preserved.

**Reading the data:** `kitt skill-usage report` from a terminal, or the `skill_usage_report` MCP tool in a session. Mark a deliberately-rare skill with `kitt skill-usage pin <name>` (or the `pin_skill` tool) so it is never labelled stale.

**Idempotent.** Re-running is safe. Already-registered hooks are reported as `ok`.

**Required:** [uv](https://docs.astral.sh/uv/) on PATH. This command runs `configure_hook.py` inside the `kitt-core` plugin's bundled server environment via `uv run --project`, which resolves the `kitt` package (for `kitt.hook_manifest`) the same way the MCP server itself does. The hook it registers shells out to `kitt skill-usage record`, and is a silent no-op wherever `kitt` is not on PATH at hook-fire time.
