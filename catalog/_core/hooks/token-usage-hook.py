#!/usr/bin/env python3
"""
token-usage-hook.py

Records per-tool token usage for a Claude Code session into a durable
sidecar, so a retrospective report can attribute cost to the tools that
drove it. Designed as a Stop hook for Claude Code.

Why this hook exists: token usage is reported by Claude Code per model
TURN (on each assistant message's ``usage`` object), never per tool. The
transcript, however, records which tool each turn called (``tool_use``
blocks) and how large each tool's result was (``tool_result`` blocks).
This hook joins the two so "which tools burned the tokens" becomes
answerable. Transcripts can rotate or be cleaned; the sidecar is the
durable record ``token-usage-report.py`` reads.

WHAT IT READS (verified against real transcripts on this machine)
-----------------------------------------------------------------
The JSONL transcript, one JSON object per line. ``role``/``content``/
``usage`` are nested under ``message`` (NOT top level):

    {"message": {"role": "assistant",
                 "usage": {"input_tokens": 2,
                           "output_tokens": 1247,
                           "cache_creation_input_tokens": 20569,
                           "cache_read_input_tokens": 15462,
                           "output_tokens_details": {"thinking_tokens": 1009}},
                 "content": [{"type": "tool_use", "id": "toolu_...",
                              "name": "Read", "input": {...}}]}}

    {"message": {"role": "user",
                 "content": [{"type": "tool_result",
                              "tool_use_id": "toolu_...",
                              "content": "..."}]}}

ATTRIBUTION (honest about what is exact vs estimated)
-----------------------------------------------------
Per-turn ``usage`` totals are EXACT and summed into the session total.
Per-tool figures are an attribution, not a ground-truth split (a turn's
tokens are shared by everything in it):

- ``calls``               EXACT: count of ``tool_use`` blocks per tool.
- ``gen_output_tokens``   The turn's ``output_tokens`` (includes thinking)
                          attributed to the tool(s) that turn called,
                          split evenly when a turn calls several tools.
                          The cost of DECIDING to call the tool.
- ``result_chars``        EXACT: total characters of the tool's results.
- ``result_tokens_est``   ESTIMATE (result_chars / 4): the context each
                          tool injected, which is re-read (as cached input)
                          on every following turn. Usually the dominant,
                          most actionable per-tool cost.

Turns with no tool call attribute their output to the ``(assistant text)``
bucket so the per-tool numbers reconcile against the session total.

WHAT IT WRITES
--------------
``~/.wopr/token-usage.json`` (override with TOKEN_USAGE_SIDECAR). The
whole session entry is recomputed from the transcript and OVERWRITTEN on
each Stop -- idempotent, no delta bookkeeping, so repeated Stop events or
a resumed session never double-count. No prompt text, no tool inputs, no
file paths, no result bodies are stored -- only names, counts, and token
figures.

Silent no-op when: the payload is unparseable, the transcript is missing,
or the sidecar cannot be written. Safe to register globally.

Install (settings.json), or mirror the skill-usage-hook registration:

  {"hooks": {"Stop": [{"matcher": "",
    "hooks": [{"type": "command",
               "command": "python3 /abs/path/token-usage-hook.py"}]}]}}
"""

from __future__ import annotations

import json
import logging
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

logger = logging.getLogger("token_usage_hook")
logging.basicConfig(level=logging.WARNING, format="[token-usage-hook] %(message)s")

SIDECAR_VERSION = 1
NO_TOOL_BUCKET = "(assistant text)"
CHARS_PER_TOKEN_EST = 4  # Rough, documented; used ONLY for result_tokens_est.


def load_stdin() -> dict[str, Any]:
    try:
        data: dict[str, Any] = json.load(sys.stdin)
        return data if isinstance(data, dict) else {}
    except (json.JSONDecodeError, ValueError) as e:
        logger.warning("Failed to parse stdin payload: %s", e)
        return {}


def load_transcript(path: str) -> list[dict[str, Any]]:
    if not path:
        return []
    p = Path(path)
    if not p.exists():
        return []
    out: list[dict[str, Any]] = []
    try:
        with p.open(encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    out.append(json.loads(line))
                except json.JSONDecodeError:
                    continue
    except OSError as e:
        logger.warning("Failed to read transcript %s: %s", p, e)
    return out


def _msg(entry: dict[str, Any]) -> dict[str, Any]:
    """The message body -- nested under 'message' on real transcripts,
    tolerated flat as well (see skill-usage-hook for why)."""
    m = entry.get("message")
    return m if isinstance(m, dict) else entry


def _thinking_tokens(usage: dict[str, Any]) -> int:
    d = usage.get("output_tokens_details")
    if isinstance(d, dict) and isinstance(d.get("thinking_tokens"), int):
        return d["thinking_tokens"]
    return 0


def _result_len(block: dict[str, Any]) -> int:
    """Character length of a tool_result's content, whether it is a plain
    string or a list of content parts (text/image blocks)."""
    content = block.get("content")
    if isinstance(content, str):
        return len(content)
    if isinstance(content, list):
        total = 0
        for part in content:
            if isinstance(part, dict):
                total += len(part.get("text") or "") or len(json.dumps(part))
            elif isinstance(part, str):
                total += len(part)
        return total
    if content is None:
        return 0
    return len(json.dumps(content))


def compute_session(messages: list[dict[str, Any]]) -> dict[str, Any]:
    totals = {
        "turns": 0,
        "input_tokens": 0,
        "output_tokens": 0,
        "cache_creation_input_tokens": 0,
        "cache_read_input_tokens": 0,
        "thinking_tokens": 0,
    }
    tools: dict[str, dict[str, int]] = {}

    def bucket(name: str) -> dict[str, int]:
        return tools.setdefault(
            name,
            {"calls": 0, "gen_output_tokens": 0, "result_chars": 0, "result_tokens_est": 0},
        )

    id_to_name: dict[str, str] = {}

    # Pass 1: assistant turns -- totals, call counts, output attribution.
    for entry in messages:
        m = _msg(entry)
        if m.get("role") != "assistant":
            continue
        usage = m.get("usage")
        if not isinstance(usage, dict):
            continue
        totals["turns"] += 1
        totals["input_tokens"] += int(usage.get("input_tokens") or 0)
        out = int(usage.get("output_tokens") or 0)
        totals["output_tokens"] += out
        totals["cache_creation_input_tokens"] += int(usage.get("cache_creation_input_tokens") or 0)
        totals["cache_read_input_tokens"] += int(usage.get("cache_read_input_tokens") or 0)
        totals["thinking_tokens"] += _thinking_tokens(usage)

        content = m.get("content")
        calls = [
            b for b in content
            if isinstance(b, dict) and b.get("type") == "tool_use" and isinstance(b.get("name"), str)
        ] if isinstance(content, list) else []

        if not calls:
            bucket(NO_TOOL_BUCKET)["gen_output_tokens"] += out
            continue

        share = out // len(calls)
        remainder = out - share * len(calls)
        for i, b in enumerate(calls):
            name = b["name"]
            tb = bucket(name)
            tb["calls"] += 1
            tb["gen_output_tokens"] += share + (remainder if i == 0 else 0)
            tid = b.get("id")
            if isinstance(tid, str):
                id_to_name[tid] = name

    # Pass 2: tool_result sizes -> the tool that produced them.
    for entry in messages:
        m = _msg(entry)
        if m.get("role") != "user":
            continue
        content = m.get("content")
        if not isinstance(content, list):
            continue
        for b in content:
            if not isinstance(b, dict) or b.get("type") != "tool_result":
                continue
            name = id_to_name.get(b.get("tool_use_id"))
            if not name:
                continue
            n = _result_len(b)
            tb = bucket(name)
            tb["result_chars"] += n
            tb["result_tokens_est"] += n // CHARS_PER_TOKEN_EST

    return {"totals": totals, "tools": tools}


def resolve_sidecar() -> Path:
    override = os.environ.get("TOKEN_USAGE_SIDECAR", "").strip()
    if override:
        return Path(override)
    return Path.home() / ".wopr" / "token-usage.json"


def load_sidecar(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {"version": SIDECAR_VERSION, "sessions": {}}
    try:
        with path.open(encoding="utf-8") as f:
            data = json.load(f)
        if isinstance(data, dict) and isinstance(data.get("sessions"), dict):
            return data
    except (OSError, json.JSONDecodeError) as e:
        logger.warning("Failed to read sidecar %s: %s", path, e)
    return {"version": SIDECAR_VERSION, "sessions": {}}


def main() -> None:
    payload = load_stdin()
    session_id = payload.get("session_id") or payload.get("sessionId") or ""
    transcript_path = payload.get("transcript_path") or payload.get("transcriptPath") or ""
    cwd = payload.get("cwd") or os.getcwd()
    if not session_id:
        sys.exit(0)

    messages = load_transcript(transcript_path)
    if not messages:
        sys.exit(0)

    session = compute_session(messages)
    session["cwd"] = cwd
    session["updated_at"] = datetime.now(timezone.utc).isoformat()

    sidecar_path = resolve_sidecar()
    sidecar = load_sidecar(sidecar_path)
    sidecar["version"] = SIDECAR_VERSION
    sidecar["sessions"][session_id] = session  # Overwrite: idempotent.

    try:
        sidecar_path.parent.mkdir(parents=True, exist_ok=True)
        with sidecar_path.open("w", encoding="utf-8") as f:
            json.dump(sidecar, f, indent=2)
    except OSError as e:
        logger.warning("Failed to write sidecar %s: %s", sidecar_path, e)
        sys.exit(0)


if __name__ == "__main__":
    main()
