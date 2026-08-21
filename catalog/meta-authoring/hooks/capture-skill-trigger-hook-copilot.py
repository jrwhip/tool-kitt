#!/usr/bin/env python3
"""
capture-skill-trigger-hook-copilot.py

Copilot CLI port of capture-skill-trigger-hook.py. Nudges the agent to
consider invoking the wopr-capture-skill skill once a session crosses a
tool-call threshold since the last check. WOPR installs the skill
natively under ~/.copilot/skills/wopr-capture-skill/ (invocable as
/wopr-capture-skill); the run_skill MCP tool remains as a fallback when
the native skill is not installed but the wopr MCP server is.

This is NOT the same hook with a different event name. Three things differ
from the Claude version, each verified directly rather than assumed from
either product's docs or comments:

1. Event and config location. Copilot's Stop-equivalent is `agentStop`,
   registered in `.github/hooks/*.json` (`version: 1`, camelCase event
   keys) — confirmed against docs.github.com/en/copilot/reference/
   hooks-reference.

2. Input casing. Copilot ships BOTH camelCase (`sessionId`,
   `transcriptPath`) and PascalCase/VS-Code-format (`session_id`,
   `transcript_path`) payloads for the same event, per the same reference.
   This script reads whichever is present.

3. Transcript format and how to reach the skill. Confirmed by inspecting a
   real local session at ~/.copilot/session-state/<id>/events.jsonl, not
   from documentation (none of the fetched hooks-reference pages describe
   the transcript's internal schema): each line is a JSON object shaped
   like {"type": "tool.execution_start", "data": {...}, "id": "...",
   "timestamp": "...", "parentId": "..."} — nothing like Claude's nested
   `tool_use` content blocks inside assistant messages. Tool calls are
   counted by `type == "tool.execution_start"` lines.

   Separately, how the skill is reached: WOPR installs
   wopr-capture-skill as a NATIVE Copilot skill under
   `~/.copilot/skills/wopr-capture-skill/` (Copilot >= 1.0.36 loads
   skills from there), so the nudge text below points at
   `/wopr-capture-skill` first and names the `run_skill` MCP tool only
   as a fallback for installs where the native skill failed to land
   but the `wopr` MCP server is registered. Accordingly the gate in
   main() fires when EITHER surface is present: the native skill dir
   exists, or `~/.copilot/mcp-config.json` registers `wopr`.

Output schema difference: Copilot's `agentStop` only supports
`decision: "block"|"allow"` plus `reason` — there is no equivalent to
Claude's non-blocking `hookSpecificOutput.additionalContext`. So this
version cannot be a soft nudge the same way; crossing the threshold forces
another turn via `decision: "block"`. The state checkpoint (below) still
advances past the counted tool calls immediately after firing, so the
forced turn does not immediately re-block on the same batch of calls.

None of this has been tested against a live agentStop firing — verified
against a real installed session transcript and the official schema, not
against actual hook invocation behavior.

Input: JSON via stdin (agentStop hook payload, either casing)
  {
    "sessionId" | "session_id": "...",
    "cwd": "/path/to/project",
    "transcriptPath" | "transcript_path": "/path/to/events.jsonl"
  }

Output: JSON on stdout. When the threshold is crossed:
  {"decision": "block", "reason": "<nudge text>"}
Below threshold, or when neither the native wopr-capture-skill skill nor
the wopr MCP server is installed, the hook prints nothing and exits 0
(allow).

Environment variables (all optional):
  CAPTURE_SKILL_HOOK_THRESHOLD   Tool calls since the last nudge required
                                  to fire again. Default: 8.
  CAPTURE_SKILL_HOOK_STATE_PATH  Path to the state file. Default:
                                  $cwd/.github/.capture-skill-hook-state.json

Install by adding to .github/hooks/hooks.json:
  {
    "version": 1,
    "hooks": {
      "agentStop": [
        {
          "type": "command",
          "bash": "python3 /absolute/path/to/capture-skill-trigger-hook-copilot.py",
          "powershell": "python /absolute/path/to/capture-skill-trigger-hook-copilot.py"
        }
      ]
    }
  }
"""

from __future__ import annotations

import json
import logging
import os
import sys
from pathlib import Path
from typing import Any

logger = logging.getLogger("capture_skill_trigger_hook_copilot")
logging.basicConfig(
    level=logging.WARNING, format="[capture-skill-trigger-hook-copilot] %(message)s"
)

DEFAULT_THRESHOLD = 8

NUDGE_TEMPLATE = (
    "This session has made {count} tool calls since the last check. If a "
    "genuinely hard-won, reusable lesson came out of this stretch of work — "
    "something that took real investigation, a corrected wrong assumption, "
    "or a non-obvious fix — invoke the wopr-capture-skill skill now "
    "(/wopr-capture-skill, or the run_skill MCP tool with "
    "skill_name=\"wopr-capture-skill\" as a fallback) while the context is "
    "fresh. Skip "
    "it if nothing here would help a future session; most stretches of "
    "ordinary work do not need this."
)


# -- Helpers ------------------------------------------------------------------

def load_stdin() -> dict[str, Any]:
    try:
        data: dict[str, Any] = json.load(sys.stdin)
        return data
    except (json.JSONDecodeError, ValueError) as e:
        logger.warning("Failed to parse stdin payload: %s", e)
        return {}


def get_field(payload: dict[str, Any], *names: str) -> Any:
    """Return the first present field among camelCase / PascalCase aliases."""
    for name in names:
        if name in payload:
            return payload[name]
    return None


def load_transcript_lines(path: str) -> list[dict[str, Any]]:
    """Load events.jsonl. Each line is one JSON event object."""
    if not path:
        return []
    transcript_path = Path(path)
    if not transcript_path.exists():
        return []
    events: list[dict[str, Any]] = []
    try:
        with transcript_path.open(encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    events.append(json.loads(line))
                except json.JSONDecodeError:
                    continue
    except OSError as e:
        logger.warning("Failed to read transcript %s: %s", transcript_path, e)
    return events


def count_tool_calls(events: list[dict[str, Any]], start_index: int) -> int:
    """Count tool.execution_start events from start_index to the end."""
    count = 0
    for event in events[start_index:]:
        if event.get("type") == "tool.execution_start":
            count += 1
    return count


def native_capture_skill_installed() -> bool:
    """Check whether the native wopr-capture-skill skill is installed.

    WOPR installs it under ``~/.copilot/skills/wopr-capture-skill/``;
    its presence alone justifies the nudge (the /wopr-capture-skill
    invocation needs no MCP server).
    """
    return (Path.home() / ".copilot" / "skills" / "wopr-capture-skill").exists()


def wopr_mcp_configured() -> bool:
    """Check whether the wopr MCP server is registered for Copilot.

    The MCP server serves run_skill(), the fallback invocation path
    when the native skill is not installed.
    """
    config_path = Path.home() / ".copilot" / "mcp-config.json"
    if not config_path.exists():
        return False
    try:
        with config_path.open(encoding="utf-8") as f:
            config = json.load(f)
    except (OSError, json.JSONDecodeError) as e:
        logger.warning("Failed to read %s: %s", config_path, e)
        return False
    servers = config.get("mcpServers") if isinstance(config, dict) else None
    return isinstance(servers, dict) and "wopr" in servers


def resolve_state_path(cwd: str) -> Path:
    override = os.environ.get("CAPTURE_SKILL_HOOK_STATE_PATH", "").strip()
    if override:
        return Path(override)
    return Path(cwd) / ".github" / ".capture-skill-hook-state.json"


def load_state(state_path: Path) -> dict[str, Any]:
    if not state_path.exists():
        return {}
    try:
        with state_path.open(encoding="utf-8") as f:
            data: dict[str, Any] = json.load(f)
            return data
    except (OSError, json.JSONDecodeError) as e:
        logger.warning("Failed to read state file %s: %s", state_path, e)
        return {}


def save_state(state_path: Path, state: dict[str, Any]) -> None:
    try:
        state_path.parent.mkdir(parents=True, exist_ok=True)
        with state_path.open("w", encoding="utf-8") as f:
            json.dump(state, f)
    except OSError as e:
        logger.warning("Failed to write state file %s: %s", state_path, e)


def resolve_threshold() -> int:
    raw = os.environ.get("CAPTURE_SKILL_HOOK_THRESHOLD", "").strip()
    if not raw:
        return DEFAULT_THRESHOLD
    try:
        value = int(raw)
        return value if value > 0 else DEFAULT_THRESHOLD
    except ValueError:
        return DEFAULT_THRESHOLD


def emit_block(count: int) -> None:
    output = {
        "decision": "block",
        "reason": NUDGE_TEMPLATE.format(count=count),
    }
    print(json.dumps(output))


# -- Main ---------------------------------------------------------------------

def main() -> None:
    payload = load_stdin()
    cwd = get_field(payload, "cwd") or os.getcwd()
    session_id = get_field(payload, "sessionId", "session_id") or ""
    transcript_path = get_field(payload, "transcriptPath", "transcript_path") or ""

    # Nudge only when the skill is actually reachable: natively
    # installed under ~/.copilot/skills/, or via the run_skill fallback
    # the wopr MCP server provides. Gating on the MCP entry alone would
    # silently suppress the nudge for operators who have the native
    # skill but no MCP registration.
    if not (native_capture_skill_installed() or wopr_mcp_configured()):
        sys.exit(0)

    events = load_transcript_lines(transcript_path)
    if not events:
        sys.exit(0)

    state_path = resolve_state_path(cwd)
    state = load_state(state_path)
    session_state = state.get(session_id, {})
    last_index = session_state.get("last_nudged_at_index", 0)

    if last_index > len(events):
        # Transcript shorter than the recorded checkpoint (new/rotated
        # session reusing an old state entry) — restart the count.
        last_index = 0

    count = count_tool_calls(events, last_index)
    threshold = resolve_threshold()

    if count < threshold:
        sys.exit(0)

    emit_block(count)

    state[session_id] = {"last_nudged_at_index": len(events)}
    save_state(state_path, state)


if __name__ == "__main__":
    main()
