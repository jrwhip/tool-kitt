#!/usr/bin/env python3
"""
capture-skill-trigger-hook.py

Nudges the agent to consider running the wopr-capture-skill skill after a
session has accumulated enough tool calls that a real, hard-won lesson may
have come out of it. Designed as a Stop hook for Claude Code.

Why a nudge and not an automatic capture: the decision of WHAT is worth
capturing is a judgment call (was this actually hard-won, is it durable, is
it likely to recur) that lives in the wopr-capture-skill skill itself and
needs the agent's read of the conversation, not a regex over the transcript.
A hook cannot invoke a skill directly — the Claude Code hook API has no such
primitive — so the most this hook can do is put the question in front of the
agent instead of leaving it to whether a human remembers to say "capture
this." That is the concrete gap this hook closes: capture-skill today only
fires on an explicit trigger phrase or a proactive one-sentence offer that
depends on the agent happening to notice. This hook makes the check itself
unconditional above a threshold, while leaving the capture decision exactly
where it already lived.

Deterministic pre-filter, then judgment: the threshold below decides when to
ask, never when to write. The default (see CAPTURE_SKILL_HOOK_THRESHOLD)
is deliberately conservative because this nudges a human-in-the-loop agent
rather than firing an autonomous write, and repeated low-value nudges are
worse than a slightly-late one.

Input: JSON via stdin (Stop hook payload)
  {
    "session_id": "...",
    "transcript_path": "/path/to/transcript.jsonl",
    "cwd": "/path/to/project",
    "last_assistant_message": "..."
  }

Output: JSON on stdout. When the threshold is crossed:
  {
    "hookSpecificOutput": {
      "hookEventName": "Stop",
      "additionalContext": "<nudge text>"
    }
  }
Below threshold, or when the skill is not installed anywhere this hook can
see, the hook prints nothing and exits 0 (silent no-op).

additionalContext, not decision:"block" or continue:false, on purpose: it
lets the agent read the nudge and decide, on the next turn, rather than
forcing a hard stop-and-continue cycle on every threshold crossing. A forced
block that the agent evaluates and declines would immediately re-block on
the very next Stop, since the same tool calls are still in the transcript,
unless the hook wrote state either way — additionalContext sidesteps that by
not needing to be "resolved" before the turn can end.

Environment variables (all optional):
  CAPTURE_SKILL_HOOK_THRESHOLD  Tool calls since the last nudge required to
                                 fire again. Default: 8.
  CAPTURE_SKILL_HOOK_STATE_PATH Path to the state file that tracks how much
                                 of the transcript has already been counted.
                                 Default: $cwd/.claude/.capture-skill-hook-state.json

Install by adding to your settings.json:
  {
    "hooks": {
      "Stop": [
        {
          "matcher": "",
          "hooks": [
            {
              "type": "command",
              "command": "python3 /absolute/path/to/capture-skill-trigger-hook.py"
            }
          ]
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

logger = logging.getLogger("capture_skill_trigger_hook")
logging.basicConfig(level=logging.WARNING, format="[capture-skill-trigger-hook] %(message)s")

DEFAULT_THRESHOLD = 8

NUDGE_TEMPLATE = (
    "This session has made {count} tool calls since the last check. If a "
    "genuinely hard-won, reusable lesson came out of this stretch of work — "
    "something that took real investigation, a corrected wrong assumption, "
    "or a non-obvious fix — consider running the capture-skill skill "
    "(wopr-capture-skill on newer installs) now while the context is fresh. "
    "Skip it if nothing here would help a future session; most stretches of "
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


def load_transcript(path: str) -> list[dict[str, Any]]:
    """Load transcript. Claude Code writes JSONL (one JSON object per line)."""
    if not path:
        return []
    transcript_path = Path(path)
    if not transcript_path.exists():
        return []
    messages: list[dict[str, Any]] = []
    try:
        with transcript_path.open(encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    messages.append(json.loads(line))
                except json.JSONDecodeError:
                    continue
    except OSError as e:
        logger.warning("Failed to read transcript %s: %s", transcript_path, e)
    return messages


def count_tool_calls(messages: list[dict[str, Any]], start_index: int) -> int:
    """Count assistant tool_use content blocks from start_index to the end.

    Reads BOTH transcript shapes. Claude Code nests ``role`` and
    ``content`` under a ``message`` key rather than putting them at the
    top level of the JSONL line -- measured across 40 real transcripts on
    a live machine: 9931 lines carrying ``message.role``, zero carrying a
    top-level ``role``. This function previously read only the top-level
    shape, so it returned 0 on every real session and the hook never
    fired: no error, no log, just a nudge that never came. The flat shape
    is still accepted because supporting it costs three lines and the
    failure mode of guessing wrong is invisible.
    """
    count = 0
    for entry in messages[start_index:]:
        message = entry.get("message")
        source = message if isinstance(message, dict) else entry
        if source.get("role") != "assistant":
            continue
        content = source.get("content", "")
        if not isinstance(content, list):
            continue
        for block in content:
            if isinstance(block, dict) and block.get("type") == "tool_use":
                count += 1
    return count


_CAPTURE_SKILL_NAMES = ("wopr-capture-skill", "capture-skill")


def skill_installed(cwd: str) -> bool:
    """Check whether a capture-skill is reachable from this project or the
    user's global Claude config. Checks both the WOPR-pack name
    (``wopr-capture-skill``) and the unprefixed ``capture-skill`` name a
    real install can carry — confirmed against a live machine where the
    installed skill predates the WOPR meta-authoring pack (older SKILL.md,
    same purpose, name never migrated). Checking only the prefixed name
    made this hook a silent, permanent no-op on that machine; there was no
    error, just nothing ever firing. Mirrors prompt-log-hook.py's opt-in
    philosophy otherwise: a hook safe to register globally is a silent
    no-op wherever the thing it nudges toward is not actually installed.
    """
    roots = [
        Path(cwd) / ".claude" / "skills",
        Path(os.path.expanduser("~")) / ".claude" / "skills",
    ]
    return any((root / name).is_dir() for root in roots for name in _CAPTURE_SKILL_NAMES)


def resolve_state_path(cwd: str) -> Path:
    override = os.environ.get("CAPTURE_SKILL_HOOK_STATE_PATH", "").strip()
    if override:
        return Path(override)
    return Path(cwd) / ".claude" / ".capture-skill-hook-state.json"


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


def emit_nudge(count: int) -> None:
    output = {
        "hookSpecificOutput": {
            "hookEventName": "Stop",
            "additionalContext": NUDGE_TEMPLATE.format(count=count),
        }
    }
    print(json.dumps(output))


# -- Main ---------------------------------------------------------------------

def main() -> None:
    payload = load_stdin()
    cwd = payload.get("cwd", os.getcwd())
    session_id = payload.get("session_id", "")
    transcript_path = payload.get("transcript_path", "")

    if not skill_installed(cwd):
        sys.exit(0)

    messages = load_transcript(transcript_path)
    if not messages:
        sys.exit(0)

    state_path = resolve_state_path(cwd)
    state = load_state(state_path)
    session_state = state.get(session_id, {})
    last_index = session_state.get("last_nudged_at_index", 0)

    if last_index > len(messages):
        # Transcript shorter than the recorded checkpoint (new/rotated
        # session reusing an old state entry) — restart the count.
        last_index = 0

    count = count_tool_calls(messages, last_index)
    threshold = resolve_threshold()

    if count < threshold:
        sys.exit(0)

    emit_nudge(count)

    state[session_id] = {"last_nudged_at_index": len(messages)}
    save_state(state_path, state)


if __name__ == "__main__":
    main()
