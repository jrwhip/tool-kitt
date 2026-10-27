"""Shared validation for caller-supplied target workspace paths.

The stateful write tools (``create_handoff``, ``add_todo``,
``append_learnings``, and friends) require the caller to name the
project they act on, exactly like ``seed_learnings`` already does. A
single long-lived MCP server is shared across many git worktrees and
CLI sessions, so it cannot infer which project a call belongs to.
Inferring it from the server's launch directory is how a handoff once
overwrote an unrelated worktree. These tools therefore take an explicit
``target_workspace_path`` and validate it here instead of guessing.

Private import name (leading underscore): this is not part of KITT's
MCP-tool surface, only a helper the tool modules share so the
validation rules and error wording live in one place.
"""

from __future__ import annotations

import asyncio
import os
from pathlib import Path
from typing import TYPE_CHECKING
from urllib.parse import unquote, urlparse

from mcp.shared.exceptions import McpError

from ..context import ServerContext

if TYPE_CHECKING:
    from ..context import ToolContext

class InvalidTargetWorkspaceError(ValueError):
    """A caller-supplied ``target_workspace_path`` failed validation.

    The message is already prefixed with ``Error:`` and written for an
    agent to read, so tool functions can return ``str(exc)`` verbatim.
    """


def resolve_target_workspace(target_workspace_path: str) -> Path:
    """Validate a caller-supplied workspace path and return it resolved.

    The path must be supplied, absolute, and point at an existing
    directory. There is deliberately no fallback to the current working
    directory: a missing or wrong path fails loud rather than silently
    targeting whatever directory the server happens to be sitting in.

    Raises:
        InvalidTargetWorkspaceError: when the path is missing, relative,
            or not an existing directory. Callers catch it and return its
            message string to the agent.
    """
    if not target_workspace_path or not str(target_workspace_path).strip():
        raise InvalidTargetWorkspaceError(
            "Error: target_workspace_path is required. Pass the absolute path "
            "to the project directory this should act on. KITT does not infer "
            "the workspace from the server's launch directory."
        )
    ws = Path(target_workspace_path).expanduser()
    if not ws.is_absolute():
        raise InvalidTargetWorkspaceError(
            f"Error: target_workspace_path {target_workspace_path!r} is not "
            "absolute. Pass the project's absolute path."
        )
    ws = ws.resolve()
    if not ws.is_dir():
        raise InvalidTargetWorkspaceError(
            f"Error: target workspace does not exist: {ws}"
        )
    return ws


def _resolve_ambient_workspace() -> Path | None:
    """Best-effort per-CLI default workspace when no explicit target is given.

    Claude Code sets ``CLAUDE_PROJECT_DIR`` in the spawned MCP server's
    environment to the session's project root: a reliable, per-session
    signal that does not require guessing from the server's launch
    directory. This is the only cheap ambient signal KITT consumes.

    Deliberately NOT consulted:

    - **MCP roots on Claude Code:** advertised but unimplemented; calling
      ``list_roots()`` hangs ~5s then errors, so it is never attempted.
    Request-aware tools use :func:`resolve_request_workspace` instead, which
    can consume MCP roots from Copilot and other clients. This synchronous
    helper remains for non-MCP internal callers and compatibility paths.

    Returns the resolved directory, or ``None`` if no signal is available
    (the caller then errors rather than guessing).
    """
    claude_project_dir = os.environ.get("CLAUDE_PROJECT_DIR")
    if claude_project_dir and claude_project_dir.strip():
        candidate = Path(claude_project_dir).expanduser()
        if candidate.is_dir():
            return candidate.resolve()
    return None


def _path_from_root_uri(uri: str) -> Path | None:
    """Convert an MCP file root URI to an existing local directory."""
    parsed = urlparse(uri)
    if parsed.scheme != "file":
        return None
    path = Path(unquote(parsed.path)).expanduser()
    if parsed.netloc and parsed.netloc not in {"", "localhost"}:
        path = Path(f"//{parsed.netloc}{unquote(parsed.path)}")
    if path.is_dir():
        return path.resolve()
    return None


async def _resolve_mcp_roots(ctx: ToolContext | None) -> list[Path]:
    """Return unique existing directory roots advertised by the MCP client."""
    if ctx is None:
        return []
    try:
        result = await asyncio.wait_for(ctx.session.list_roots(), timeout=2.0)
    except (TimeoutError, McpError, RuntimeError):
        return []

    roots: list[Path] = []
    for root in result.roots:
        path = _path_from_root_uri(str(root.uri))
        if path is not None and path not in roots:
            roots.append(path)
    return roots


async def resolve_request_workspace(
    target_workspace_path: str = "",
    ctx: ToolContext | None = None,
    *,
    allow_legacy_config: bool = True,
) -> Path:
    """Resolve a workspace for one MCP tool request.

    Precedence is explicit caller input, a trusted Claude session directory,
    MCP roots, then the legacy server registration. Multiple MCP roots are
    deliberately ambiguous: callers must select one explicitly instead of
    relying on ordering supplied by the client.
    """
    if target_workspace_path and str(target_workspace_path).strip():
        return resolve_target_workspace(target_workspace_path)

    try:
        server_ctx = ServerContext.get()
    except RuntimeError:
        server_ctx = None

    if server_ctx is None or server_ctx.cli_type == "claude":
        ambient = _resolve_ambient_workspace()
        if ambient is not None:
            return ambient

    roots = await _resolve_mcp_roots(ctx)
    if len(roots) == 1:
        return roots[0]
    if len(roots) > 1:
        choices = ", ".join(str(path) for path in roots)
        raise InvalidTargetWorkspaceError(
            "Error: the MCP client advertised multiple workspace roots. Pass "
            f"target_workspace_path explicitly. Available roots: {choices}"
        )

    if allow_legacy_config and server_ctx is not None and server_ctx.cli_type != "copilot":
        return server_ctx.workspace

    raise InvalidTargetWorkspaceError(
        "Error: target_workspace_path was not provided and the MCP client did "
        "not advertise a single workspace root. Pass the absolute path to the "
        "project this tool should act on."
    )


def resolve_workspace_for_tool(target_workspace_path: str) -> Path:
    """Resolve the workspace for a stateful tool call.

    Precedence: an explicit ``target_workspace_path`` always wins;
    otherwise the per-CLI ambient default (see
    :func:`_resolve_ambient_workspace`); and if neither is available, raise
    rather than fall back to the server's launch directory.

    Raises:
        InvalidTargetWorkspaceError: when an explicit path fails validation,
            or when no path was given and no ambient signal is available.
    """
    if target_workspace_path and str(target_workspace_path).strip():
        return resolve_target_workspace(target_workspace_path)
    ambient = _resolve_ambient_workspace()
    if ambient is not None:
        return ambient
    raise InvalidTargetWorkspaceError(
        "Error: target_workspace_path was not provided and KITT could not "
        "determine it automatically (no CLAUDE_PROJECT_DIR in the server's "
        "environment). Pass the absolute path to the project this should "
        "act on."
    )
