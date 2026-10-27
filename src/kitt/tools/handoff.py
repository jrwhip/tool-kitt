"""Context handoff tools."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import TYPE_CHECKING

from .._atomic_write import atomic_write_text
from ..context import ToolContext
from ._workspace_target import (
    InvalidTargetWorkspaceError,
    resolve_request_workspace,
)

if TYPE_CHECKING:
    from mcp.server.fastmcp import FastMCP


async def create_handoff(
    target_workspace_path: str = "",
    *,
    summary: str,
    next_steps: str,
    context: str = "",
    overwrite: bool = False,
    ctx: ToolContext | None = None,
) -> str:
    """Write a whats-next.md handoff into a project workspace.

    Args:
        target_workspace_path: Absolute path to the project workspace root
            (where whats-next.md should live), and must exist. Optional on
            Claude Code, where it defaults to the session's project via
            CLAUDE_PROJECT_DIR; on other CLIs pass it explicitly. KITT never
            guesses from the server's launch directory.
        summary: Brief summary of what was accomplished.
        next_steps: What needs to happen next (bullet points recommended).
        context: Optional additional context (files modified, decisions, etc.).
        overwrite: Replace an existing whats-next.md. Defaults to False so an
            unread handoff is never silently destroyed. Read the existing one
            with get_handoff first, then pass overwrite=True to replace it.
    """
    try:
        workspace = await resolve_request_workspace(
            target_workspace_path, ctx, allow_legacy_config=False
        )
    except InvalidTargetWorkspaceError as e:
        return str(e)

    handoff_file = workspace / "whats-next.md"
    if handoff_file.exists() and not overwrite:
        return (
            f"Error: {handoff_file} already exists. Refusing to overwrite a "
            "handoff you have not read. Read it with "
            f"get_handoff({str(workspace)!r}) first, then call create_handoff "
            "again with overwrite=True to replace it."
        )

    timestamp = datetime.now(tz=timezone.utc).strftime("%Y-%m-%d %H:%M")

    content = f"""# What's Next - {timestamp}

## Summary
{summary}

## Next Steps
{next_steps}
"""

    if context:
        content += f"""
## Context
{context}
"""

    try:
        atomic_write_text(handoff_file, content)
    except OSError as e:
        return f"Error: could not write {handoff_file}: {e}"

    return f"Created handoff document: {handoff_file}"


async def get_handoff(
    target_workspace_path: str = "", ctx: ToolContext | None = None
) -> str:
    """Read the whats-next.md handoff from a project workspace.

    Args:
        target_workspace_path: Absolute path to the project workspace root
            whose whats-next.md should be read, and must exist. Optional on
            Claude Code (defaults to the session's project via
            CLAUDE_PROJECT_DIR); on other CLIs pass it explicitly.
    """
    try:
        workspace = await resolve_request_workspace(
            target_workspace_path, ctx, allow_legacy_config=False
        )
    except InvalidTargetWorkspaceError as e:
        return str(e)

    handoff_file = workspace / "whats-next.md"
    if not handoff_file.exists():
        return f"No whats-next.md file found in {workspace}"

    try:
        return handoff_file.read_text(encoding="utf-8")
    except OSError as e:
        return f"Error: Failed to read whats-next.md: {e}"


def register(mcp: FastMCP) -> None:
    """Register handoff tools with the MCP server."""
    mcp.tool()(create_handoff)
    mcp.tool()(get_handoff)
