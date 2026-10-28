#!/usr/bin/env python3
"""
prompt-log-hook.py

Appends one structured entry to a prompt log file after every assistant
turn. Designed as a Stop hook for Claude Code; hook events like Stop are a
Claude Code feature, so this file is Claude-specific until other CLIs ship
an equivalent event model.

Entry format:
  ---
  **[YYYY-MM-DD | <8-char-session-id> | msg <index>] <user message on one line>**
  > <one-line summary extracted from the assistant's response>

The session ID and message index let a reader jump from a log entry to the
exact exchange in the JSONL transcript. The transcript itself lives at
~/.claude/projects/<encoded-cwd>/<full-session-id>.jsonl and the message at
the recorded index is the assistant turn this entry summarizes:
  jq -s '.[<index>]' ~/.claude/projects/<encoded-cwd>/<full-session-id>.jsonl

Input: JSON via stdin (hook payload)
  {
    "session_id": "...",
    "transcript_path": "/path/to/transcript.jsonl",
    "cwd": "/path/to/project"
  }

Environment variables (all optional):
  PROMPT_LOG_PATH    Path to the log file. Default: $cwd/PROMPT_LOG.md.
  PROMPT_LOG_CREATE  Set to "1" to create the log file if missing.
                     Default (unset or "0"): skip silently if missing, so
                     the hook is a no-op in directories that have not
                     opted in.

Install by adding to your settings.json:
  {
    "hooks": {
      "Stop": [
        {
          "matcher": "",
          "hooks": [
            {
              "type": "command",
              "command": "python3 /absolute/path/to/prompt-log-hook.py"
            }
          ]
        }
      ]
    }
  }
"""

from __future__ import annotations

import datetime
import json
import logging
import os
import re
import sys
from pathlib import Path
from typing import Any

logger = logging.getLogger("prompt_log_hook")
logging.basicConfig(level=logging.WARNING, format="[prompt-log-hook] %(message)s")


# -- Redaction ------------------------------------------------------------

# Applied to both the user prompt and the assistant summary before either is
# written to disk. PROMPT_LOG.md is a plain committed-or-not markdown file
# with no access control of its own — anything pasted into a session (a
# connection string, a token while debugging an integration, a key while
# configuring a service) would otherwise land here verbatim forever.
# Each pattern replaces the matched secret only, preserving surrounding
# context so the log entry stays readable.
_REDACT_PATTERNS: list[tuple[re.Pattern[str], str]] = [
    # Cloud provider keys
    (re.compile(r"AKIA[0-9A-Z]{16}"), "[REDACTED:aws-access-key]"),
    (re.compile(r"(?i)aws_secret_access_key\s*[=:]\s*\S+"), "aws_secret_access_key=[REDACTED]"),
    # GitHub tokens
    (re.compile(r"ghp_[A-Za-z0-9]{36}"), "[REDACTED:github-token]"),
    (re.compile(r"github_pat_[A-Za-z0-9_]{80,}"), "[REDACTED:github-token]"),
    # Model provider API keys
    (re.compile(r"sk-ant-[A-Za-z0-9_-]{90,}"), "[REDACTED:anthropic-key]"),
    (re.compile(r"sk-[A-Za-z0-9]{20,}"), "[REDACTED:api-key]"),
    # Auth headers
    (re.compile(r"(?i)\bBearer\s+[A-Za-z0-9._-]{10,}"), "Bearer [REDACTED]"),
    (re.compile(r"(?i)\bBasic\s+[A-Za-z0-9+/=]{10,}"), "Basic [REDACTED]"),
    # PEM private key blocks
    (re.compile(
        r"-----BEGIN[^-]*PRIVATE KEY-----.*?-----END[^-]*PRIVATE KEY-----",
        re.DOTALL,
    ), "[REDACTED:private-key]"),
    # JDBC/DSN connection strings with an embedded password
    (re.compile(
        r"(jdbc:[^\s]*password=)[^&\s;]+", re.IGNORECASE
    ), r"\1[REDACTED]"),
    # Generic key/token/secret/password assignment — key=value, key: value,
    # or key="value" — covers .env-style, YAML, and JSON forms in one pass.
    # No leading \b: env-var-style names are commonly prefixed (DB_PASSWORD,
    # SNOWFLAKE_API_KEY), and "_" is a \w character so \b would not break
    # between the prefix and the keyword.
    (re.compile(
        r'(?i)((?:api[_-]?key|token|secret|password|passwd|client[_-]?secret)'
        r'\s*[=:]\s*)(["\']?)([A-Za-z0-9+/_.\-]{8,})\2'
    ), r"\1\2[REDACTED]\2"),
]


def scrub(text: str | None) -> str | None:
    """Redact known secret shapes from a text blob before it's logged.

    Best-effort, not a security boundary — a determined pattern could still
    slip through. It exists to stop the common accidental case (pasting a
    token while debugging, a connection string with a password) from being
    written to a plain, access-control-free markdown file by default.
    """
    if not text:
        return text
    scrubbed = text
    for pattern, replacement in _REDACT_PATTERNS:
        scrubbed = pattern.sub(replacement, scrubbed)
    return scrubbed


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


def extract_text(content: Any) -> str:
    """Extract plain text from a message content field (str or list of blocks)."""
    if isinstance(content, str):
        return content.strip()
    if isinstance(content, list):
        parts = []
        for block in content:
            if isinstance(block, dict) and block.get("type") == "text":
                parts.append(block.get("text", "").strip())
        return "\n".join(parts).strip()
    return ""


def last_pair(messages: list[dict[str, Any]]) -> tuple[str | None, str | None, int | None]:
    """
    Return (user_text, assistant_text, assistant_idx) from the transcript.
    assistant_idx is the position of the assistant message in the JSONL,
    suitable for use with `jq -s '.[<idx>]'` to jump to the exact exchange.
    """
    user_text: str | None = None
    assistant_text: str | None = None
    assistant_idx: int | None = None
    for i in range(len(messages) - 1, -1, -1):
        msg = messages[i]
        role = msg.get("role", "")
        content = msg.get("content", "")
        text = extract_text(content)
        if not text:
            continue
        if role == "assistant" and assistant_text is None:
            assistant_text = text
            assistant_idx = i
        elif role == "user" and user_text is None:
            user_text = text
        if user_text and assistant_text:
            break
    return user_text, assistant_text, assistant_idx


_ACTION_PATTERN = re.compile(
    r"^(Added|Applied|Built|Completed|Confirmed|Created|Deployed|Fixed|"
    r"Generated|Implemented|Installed|Launched|Merged|Moved|Ran|Removed|"
    r"Renamed|Replaced|Resolved|Running|Tests|Updated|Verified|Wrote|"
    r"All |Build |No )",
    re.IGNORECASE,
)


def summarize(assistant_text: str | None) -> str:
    """
    Extract a one-line summary from the assistant response.
    Strategy: prefer lines that start with action or outcome verbs. Fall
    back to the first non-trivial line, then to the first line.
    """
    if not assistant_text:
        return "(no summary)"

    # Strip leading markdown headers and horizontal rules
    lines = assistant_text.splitlines()
    cleaned = []
    for line in lines:
        stripped = line.strip()
        if not stripped:
            continue
        if stripped.startswith("#") or stripped.startswith("---") or stripped.startswith("==="):
            continue
        cleaned.append(stripped)

    # Prefer lines that start with universal action or outcome verbs.
    # Extend this list in a project-specific wrapper if you want to bias
    # toward domain-specific vocabulary; keep this file stack-agnostic.
    for line in cleaned[:10]:
        if _ACTION_PATTERN.match(line):
            return _truncate(line, 200)

    # Fall back to first non-trivial line
    for line in cleaned[:5]:
        if len(line) > 20:
            return _truncate(line, 200)

    return _truncate(cleaned[0], 200) if cleaned else "(no summary)"


def _truncate(text: str, max_len: int) -> str:
    return text if len(text) <= max_len else text[:max_len].rstrip() + "..."


_TRIVIAL_MESSAGES = {"test", "ping", "", "ok", "yes", "no", "go", "continue"}


def is_trivial(user_text: str | None) -> bool:
    """Skip logging for very short system or auto-continuation messages."""
    if not user_text:
        return True
    return user_text.strip().lower() in _TRIVIAL_MESSAGES


def append_log(
    prompt_log_path: Path,
    user_text: str,
    summary: str,
    session_id: str,
    msg_index: int | None,
) -> None:
    date_str = datetime.date.today().isoformat()
    # Collapse multi-line user prompts to a single readable line
    user_line = " ".join(user_text.split())
    sid = (session_id or "")[:8] or "????????"
    msg_str = f"msg {msg_index}" if msg_index is not None else "msg ?"
    entry = f"\n---\n\n**[{date_str} | {sid} | {msg_str}] {user_line}**\n> {summary}\n"
    try:
        with prompt_log_path.open("a", encoding="utf-8") as f:
            f.write(entry)
    except OSError as e:
        logger.warning("Failed to write %s: %s", prompt_log_path, e)


def resolve_log_path(cwd: str) -> Path:
    """
    Determine where to write the prompt log.
    Priority: PROMPT_LOG_PATH env var, then $cwd/PROMPT_LOG.md.
    """
    override = os.environ.get("PROMPT_LOG_PATH", "").strip()
    if override:
        return Path(override)
    return Path(cwd) / "PROMPT_LOG.md"


def ensure_log_exists(path: Path) -> bool:
    """
    Decide whether to proceed based on whether the log file exists.
    If PROMPT_LOG_CREATE=1, create it if missing and continue.
    Otherwise, return True only if the file already exists. This keeps the
    hook a silent no-op in directories that have not opted in.
    """
    if path.exists():
        return True
    if os.environ.get("PROMPT_LOG_CREATE", "").strip() == "1":
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.touch()
            return True
        except OSError as e:
            logger.warning("Failed to create %s: %s", path, e)
            return False
    return False


# -- Main ---------------------------------------------------------------------

def main() -> None:
    payload = load_stdin()
    cwd = payload.get("cwd", os.getcwd())
    transcript_path = payload.get("transcript_path", "")

    prompt_log = resolve_log_path(cwd)
    if not ensure_log_exists(prompt_log):
        # Log file does not exist and create-if-missing is off. Silent no-op.
        sys.exit(0)

    messages = load_transcript(transcript_path)
    if not messages:
        sys.exit(0)

    user_text, assistant_text, assistant_idx = last_pair(messages)
    if not user_text or is_trivial(user_text):
        sys.exit(0)

    user_text = scrub(user_text) or ""
    assistant_text = scrub(assistant_text)

    session_id = payload.get("session_id", "")
    summary = summarize(assistant_text)
    append_log(prompt_log, user_text, summary, session_id, assistant_idx)


if __name__ == "__main__":
    main()
