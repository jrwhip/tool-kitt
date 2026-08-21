---
description: Register the capture-skill-trigger agentStop hook in this project's .github/hooks/hooks.json (Copilot CLI)
---

Register the WOPR capture-skill-trigger `agentStop` hook for Copilot CLI in this project. Idempotent; safe to re-run.

**Unverified against live behavior.** This is registered against GitHub's documented `agentStop` schema (`docs.github.com/en/copilot/reference/hooks-reference`), and the transcript-parsing logic is verified against a real local `events.jsonl` file, but no one has confirmed the hook actually fires and behaves as documented on a live Copilot CLI session. Treat this as "should work per the spec," not "confirmed working."

The hook fires at the end of every turn. Once a session has crossed a threshold of tool calls since the last check (default 8), it returns `{"decision": "block", "reason": "..."}`, which forces another turn — Copilot's `agentStop` has no non-blocking equivalent to Claude's `additionalContext`, so this is a harder interruption than the Claude version of this hook. The reason text tells the agent to call the `run_skill` MCP tool with `skill_name="wopr-capture-skill"`. (Copilot also has the skill installed natively at `~/.copilot/skills/wopr-capture-skill/` as of this release, so the agent can equally invoke `/wopr-capture-skill`; `run_skill` remains a supported fallback and is what the hook's text currently points at.) The hook is a silent no-op wherever the `wopr` MCP server is not configured in `~/.copilot/mcp-config.json`, so it is safe to register globally.

**Preview without making changes:**

```
! WOPR_DIR=$(python3 -c "import ai_cli_mcp, pathlib; print(pathlib.Path(ai_cli_mcp.__file__).parent / 'resources')") && python3 "$WOPR_DIR/meta-authoring/scripts/configure_hook.py" --hook capture-skill-trigger --cli copilot --dry-run
```

**Apply:**

```
! WOPR_DIR=$(python3 -c "import ai_cli_mcp, pathlib; print(pathlib.Path(ai_cli_mcp.__file__).parent / 'resources')") && python3 "$WOPR_DIR/meta-authoring/scripts/configure_hook.py" --hook capture-skill-trigger --cli copilot
```

**Target a project other than the current directory:**

```
! WOPR_DIR=$(python3 -c "import ai_cli_mcp, pathlib; print(pathlib.Path(ai_cli_mcp.__file__).parent / 'resources')") && python3 "$WOPR_DIR/meta-authoring/scripts/configure_hook.py" --hook capture-skill-trigger --cli copilot --project-root /path/to/project
```

**What it does:**

Reads `.github/hooks/hooks.json` (creates it if missing, `version: 1`) and appends the `agentStop` hook entry. All other hooks are preserved.

**Customizing the threshold:** the hook honors the `CAPTURE_SKILL_HOOK_THRESHOLD` environment variable (tool calls since the last nudge required to fire again; default 8).

**Idempotent.** Re-running is safe. Already-registered hooks are reported as `ok`.

**Required:** WOPR must be installed (`pipx install wopr` or equivalent) so the `ai_cli_mcp` package is importable.
