""":command:`wopr learnings` subcommands: ``append`` and ``search``.

Thin wrappers over the MCP tool functions in :mod:`.tools.learnings`.
The point is reach, not new behavior: an agent with Bash but without
the WOPR MCP server (a crew role running under a stripped tool
allowlist, a hook, a CI step, a shell) can still write to and read from
the learnings corpus. Every validation the MCP path applies applies
here too, because this IS the MCP path: the same coroutines, called
directly, with ``target_workspace_path`` supplied explicitly.

That explicit path is the one real difference. Inside an MCP session
the workspace can be inferred from the client's advertised roots or
from ``CLAUDE_PROJECT_DIR``; a shell invocation has neither, so the
workspace defaults to the caller's current directory and
``--workspace`` overrides it.
"""

from __future__ import annotations

import asyncio
import logging
import sys
from pathlib import Path

from .product import LOGGER_NAME
from .tools.learnings import append_learnings, learnings_search

logger = logging.getLogger(LOGGER_NAME)

# ``append_learnings`` and ``learnings_search`` report failure by
# returning a string that starts with this prefix rather than raising,
# because an MCP tool's return value is what the model reads. The CLI
# turns that convention into an exit code so a shell caller can branch
# on it.
_ERROR_PREFIX = "Error:"


def _emit(result: str) -> int:
    """Print a tool result and map the ``Error:`` convention to an exit code."""
    if result.startswith(_ERROR_PREFIX):
        print(result, file=sys.stderr)
        return 1
    print(result)
    return 0


def read_entry(entry: str | None, entry_file: str | None) -> str:
    """Return the entry markdown from ``--entry``, a file, or stdin.

    ``--entry-file -`` reads stdin, which is how a heredoc or a pipe
    gets a multi-line entry in without shell-quoting a whole markdown
    document.
    """
    if entry is not None:
        return entry
    if entry_file == "-":
        return sys.stdin.read()
    if entry_file is not None:
        return Path(entry_file).expanduser().read_text(encoding="utf-8")
    raise ValueError("one of --entry, --entry-file or --entry-file - is required")


def cmd_learnings_append(
    workspace: Path,
    *,
    entry_markdown: str,
    origin: str = "",
) -> int:
    """Append one LEARNINGS.md entry. Same validation as the MCP tool."""
    result = asyncio.run(
        append_learnings(
            str(workspace),
            entry_markdown=entry_markdown,
            origin=origin,
        )
    )
    return _emit(result)


def cmd_learnings_search(
    workspace: Path,
    *,
    req_id: str = "",
    stack_tags: list[str] | None = None,
    max_age_days: int = 180,
    limit: int = 20,
    req_summary: str = "",
) -> int:
    """Retrieve the most relevant LEARNINGS entries for a context."""
    result = asyncio.run(
        learnings_search(
            req_id=req_id,
            stack_tags=stack_tags or [],
            max_age_days=max_age_days,
            limit=limit,
            req_summary=req_summary,
            target_workspace_path=str(workspace),
        )
    )
    return _emit(result)
