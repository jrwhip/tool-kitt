#!/usr/bin/env python3
"""
skill-usage-hook.py

Counts NATIVE Claude Code skill invocations into WOPR's skill-usage
sidecar. Designed as a Stop hook for Claude Code.

Why this hook exists at all: WOPR's MCP server can only observe skills
loaded through its own ``run_skill`` tool. On Claude Code the model
invokes skills natively -- the CLI loads ``~/.claude/skills/<name>/
SKILL.md`` itself and the MCP server never hears about it. Without this
hook, the sidecar's numbers for a Claude Code operator are close to
zero regardless of how much the skills are used, which is worse than no
numbers at all. This hook closes that specific gap and nothing else;
see ``docs/skill-usage-telemetry.md`` for what remains uncovered.

WHAT IT READS (verified, not assumed)
-------------------------------------
Claude Code's JSONL transcript, one JSON object per line. A native
skill invocation appears as a ``tool_use`` content block on an
assistant message::

    {"type": "assistant",
     "message": {"role": "assistant",
                 "content": [{"type": "tool_use",
                              "name": "Skill",
                              "input": {"skill": "wopr-whats-next",
                                        "args": "..."},
                              "caller": {"type": "direct"}}]}}

Two details were checked against real transcripts on a live machine
rather than inferred from documentation:

1. ``role`` and ``content`` are nested under ``message``, NOT at the
   top level of the transcript line. Across 40 recent transcripts:
   9931 lines with ``message.role``, 0 lines with a top-level ``role``.
   A hook that reads ``line["role"]`` counts nothing, forever, silently.
   Both shapes are accepted below anyway -- the flat shape costs three
   lines to support and the failure mode of guessing wrong is invisible.
2. The invoked skill name is ``input.skill``. Observed shapes were
   ``{"skill"}`` and ``{"skill", "args"}``. Plugin-provided skills carry
   a namespaced name (``superpowers:brainstorming``); those are skipped
   here because they are not WOPR skills and the sidecar keys on a
   single path component.

WHAT IT WRITES
--------------
Skill NAMES and COUNTS only, by shelling out to::

    wopr skill-usage record hook:claude <name> [<name> ...]

No prompt text, no arguments, no file paths -- ``args`` above is read
past, never recorded. Writing through the ``wopr`` CLI (rather than
touching the JSON directly) keeps one implementation of the sidecar
schema. Note that a plugin install does NOT put ``wopr`` on PATH: the
plugin bundle exposes only ``wopr-serve``, and the MCP registration
launches the server through a ``${CLAUDE_PLUGIN_ROOT}`` bootstrap
script rather than a bare ``wopr``. When ``wopr`` cannot be found the
hook warns and skips recording; set ``SKILL_USAGE_HOOK_WOPR_BIN`` to
the path of a real ``wopr`` executable (e.g. from a uv or pipx
install) to enable recording.

State: a per-session checkpoint in
``$cwd/.claude/.skill-usage-hook-state.json`` records how far into the
transcript has already been counted, so repeated Stop events do not
re-count the same invocations. If the state file is lost, the next run
recounts the session from the start (an overcount bounded by one
session) -- the opposite direction from every other error in this
system, and the reason the checkpoint is written even on a no-op run.

Silent no-op when: the payload is unparseable, the transcript is
missing, no new Skill calls appeared, or ``wopr`` is not on PATH.

Install by adding to your settings.json (or run
``/wopr-configure-skill-usage-hook``):

  {
    "hooks": {
      "Stop": [
        {
          "matcher": "",
          "hooks": [
            {
              "type": "command",
              "command": "python3 /absolute/path/to/skill-usage-hook.py"
            }
          ]
        }
      ]
    }
  }

Environment variables (all optional):
  SKILL_USAGE_HOOK_STATE_PATH  Override the checkpoint file location.
                               Default: $cwd/.claude/.skill-usage-hook-state.json
  SKILL_USAGE_HOOK_WOPR_BIN    Path to the wopr executable to record
                               through. Default: "wopr", which only
                               resolves when wopr was installed onto
                               PATH separately from the plugin bundle.
"""

from __future__ import annotations

import json
import logging
import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

logger = logging.getLogger("skill_usage_hook")
logging.basicConfig(level=logging.WARNING, format="[skill-usage-hook] %(message)s")

# The tool name Claude Code uses for native skill invocation.
SKILL_TOOL_NAME = "Skill"

# Guard rails on what is passed to the recorder. The sidecar keys on a
# single path component, so anything with a separator, a namespace
# prefix, or an implausible length is dropped rather than sanitized:
# a name that does not look like a skill directory is not one.
MAX_NAME_LENGTH = 128
_ILLEGAL_NAME_CHARS = ("/", "\\", "\x00", ":")

# Cap on names handed to one subprocess call, so a pathological
# transcript cannot build an unbounded argv.
MAX_NAMES_PER_CALL = 500


def load_stdin() -> dict[str, Any]:
    try:
        data: dict[str, Any] = json.load(sys.stdin)
        return data
    except (json.JSONDecodeError, ValueError) as e:
        logger.warning("Failed to parse stdin payload: %s", e)
        return {}


def load_transcript(path: str) -> list[dict[str, Any]]:
    """Load the JSONL transcript; one JSON object per line."""
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


def is_recordable_name(name: Any) -> bool:
    """True when ``name`` is a plain skill directory name.

    Namespaced plugin skills (``superpowers:brainstorming``) fail on the
    colon, which is the intended outcome: they are not WOPR skills and
    the sidecar has no key for them.
    """
    if not isinstance(name, str):
        return False
    name = name.strip()
    if not name or name in (".", "..") or len(name) > MAX_NAME_LENGTH:
        return False
    return not any(ch in name for ch in _ILLEGAL_NAME_CHARS)


def extract_skill_names(
    messages: list[dict[str, Any]], start_index: int
) -> list[str]:
    """Collect invoked skill names from ``start_index`` to the end.

    Accepts both the nested (``line["message"]["content"]``) and flat
    (``line["content"]``) transcript shapes; see the module docstring for
    why the nested one is the shape real transcripts use.
    """
    names: list[str] = []
    for entry in messages[start_index:]:
        message = entry.get("message")
        source = message if isinstance(message, dict) else entry
        if source.get("role") != "assistant":
            continue
        content = source.get("content")
        if not isinstance(content, list):
            continue
        for block in content:
            if not isinstance(block, dict):
                continue
            if block.get("type") != "tool_use" or block.get("name") != SKILL_TOOL_NAME:
                continue
            block_input = block.get("input")
            if not isinstance(block_input, dict):
                continue
            skill = block_input.get("skill")
            if is_recordable_name(skill):
                names.append(str(skill).strip())
    return names


def resolve_state_path(cwd: str) -> Path:
    override = os.environ.get("SKILL_USAGE_HOOK_STATE_PATH", "").strip()
    if override:
        return Path(override)
    return Path(cwd) / ".claude" / ".skill-usage-hook-state.json"


def load_state(state_path: Path) -> dict[str, Any]:
    if not state_path.exists():
        return {}
    try:
        with state_path.open(encoding="utf-8") as f:
            data: dict[str, Any] = json.load(f)
            return data if isinstance(data, dict) else {}
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


def record(names: list[str]) -> bool:
    """Hand the names to ``wopr skill-usage record``. True when recorded.

    A missing ``wopr`` on PATH is a silent no-op: the hook is safe to
    register globally, including on machines where WOPR was uninstalled.
    """
    if not names:
        return False
    wopr_bin = os.environ.get("SKILL_USAGE_HOOK_WOPR_BIN", "").strip() or "wopr"
    if shutil.which(wopr_bin) is None:
        logger.warning("%s is not on PATH; skipping usage recording", wopr_bin)
        return False
    try:
        subprocess.run(
            [wopr_bin, "skill-usage", "record", "hook:claude", *names],
            check=False,
            capture_output=True,
            timeout=30,
        )
    except (OSError, subprocess.SubprocessError) as e:
        logger.warning("Failed to record skill usage: %s", e)
        return False
    return True


def main() -> None:
    payload = load_stdin()
    cwd = payload.get("cwd") or os.getcwd()
    session_id = payload.get("session_id") or payload.get("sessionId") or ""
    transcript_path = (
        payload.get("transcript_path") or payload.get("transcriptPath") or ""
    )

    messages = load_transcript(transcript_path)
    if not messages:
        sys.exit(0)

    state_path = resolve_state_path(cwd)
    state = load_state(state_path)
    session_state = state.get(session_id)
    last_index = 0
    if isinstance(session_state, dict):
        raw_index = session_state.get("counted_through_index", 0)
        if isinstance(raw_index, int) and 0 <= raw_index <= len(messages):
            last_index = raw_index
        # A checkpoint past the end means a new or rotated session reused
        # an old entry; recount from the start rather than trusting it.

    names = extract_skill_names(messages, last_index)
    if names:
        record(names[:MAX_NAMES_PER_CALL])

    # Advance the checkpoint even when nothing was recorded, so the next
    # Stop starts from here instead of rescanning (and re-counting) the
    # same span.
    state[session_id] = {"counted_through_index": len(messages)}
    save_state(state_path, state)


if __name__ == "__main__":
    main()
