#!/usr/bin/env python3
"""
WOPR MCP Server.

Registers the deterministic tools an agent cannot replicate on its own:
the learnings corpus and its retrieval, the crew's contract/spec
substrate, routing evals, skill telemetry, skill and dependency
scanning, pack templates, and handoffs.
"""

from __future__ import annotations

import json
import logging
import sys
from pathlib import Path

from mcp.server.fastmcp import FastMCP

from .catalog import read_lock_file
from .config import ServerConfig
from .context import ServerContext, ToolContext
from .tools import (
    crew_contracts,
    handoff,
    learnings,
    osv_check,
    pack_templates,
    routing_eval,
    skill_guard,
    skill_usage,
    stack_detect,
    stub_writers,
    wopr_yml,
)
from .tools._workspace_target import (
    InvalidTargetWorkspaceError,
    resolve_request_workspace,
)

logger = logging.getLogger("wopr")


# ============================================================================
# SERVER-LEVEL TOOLS
# ============================================================================


def _count_in_dir(directory: Path, pattern: str, *, recurse: bool = False) -> int:
    """Count matching files in a directory, returning 0 on any error."""
    if not directory.exists():
        return 0
    try:
        glob = directory.rglob(pattern) if recurse else directory.glob(pattern)
        return sum(1 for _ in glob)
    except OSError:
        return 0


def _register_server_tools(mcp: FastMCP) -> None:
    """Register tools that depend on multiple context values."""

    @mcp.tool()
    async def get_workspace_info(
        target_workspace_path: str = "", ctx: ToolContext | None = None
    ) -> str:
        """Get information about the current workspace configuration.

        Returns details about:
        - Current workspace path
        - Detected CLI type
        - Available WOPR resources, split into LOCAL (workspace-resident
          overrides under ``<workspace>/.ai-cli/shared/`` or
          ``<workspace>/.claude/``) and GLOBAL (the per-CLI deploys
          ``wopr --init`` maintains: ``~/.claude/{skills,agents,commands}/``,
          ``~/.copilot/{skills,agents}/``, ``~/.gemini/{skills,commands}/``).

        Useful for debugging configuration issues. Zero local counters
        do NOT mean WOPR is broken; WOPR's default model is global
        symlinks, with workspace-local overrides being optional.
        """
        server_ctx = ServerContext.get()
        try:
            workspace = await resolve_request_workspace(target_workspace_path, ctx)
        except InvalidTargetWorkspaceError as e:
            return json.dumps({"workspace": None, "error": str(e)}, indent=2)
        home = Path.home()

        def _count_skills_in(skills_dir: Path) -> int:
            if not skills_dir.exists():
                return 0
            try:
                return sum(
                    1 for d in skills_dir.iterdir()
                    if d.is_dir() and (d / "SKILL.md").exists()
                )
            except OSError:
                return 0

        # LOCAL: workspace-scoped overrides (under ``.ai-cli/shared/``
        # via ``ctx.shared_dir`` when present, plus an optional
        # ``<workspace>/.claude/`` for raw Claude Code overrides).
        shared_dir = server_ctx.shared_dir_for(workspace)
        local_skills_count = _count_skills_in(shared_dir / "skills")
        local_agents_count = _count_in_dir(shared_dir / "agents", "*.md")
        local_commands_count = _count_in_dir(
            shared_dir / "commands", "*.md", recurse=True
        )
        local_context_count = _count_in_dir(shared_dir / "context", "*.md")

        # GLOBAL: the per-CLI deploys ``wopr --init`` maintains. These
        # are what each CLI's sessions see, regardless of workspace:
        # Claude gets commands/agents/skills, Copilot gets agents plus
        # native skills (commands are installed as generated skills),
        # Gemini gets generated TOML commands plus skills.
        global_counts = {
            "claude": {
                "skills": _count_skills_in(home / ".claude" / "skills"),
                "agents": _count_in_dir(home / ".claude" / "agents", "wopr-*.md"),
                "commands": _count_in_dir(
                    home / ".claude" / "commands", "wopr-*.md", recurse=True
                ),
            },
            "copilot": {
                "skills": _count_skills_in(home / ".copilot" / "skills"),
                "agents": _count_in_dir(
                    home / ".copilot" / "agents", "wopr-*.agent.md"
                ),
            },
            "gemini": {
                "skills": _count_skills_in(home / ".gemini" / "skills"),
                "commands": _count_in_dir(home / ".gemini" / "commands", "wopr-*.toml"),
            },
        }

        has_local_shared = (workspace / ".ai-cli" / "shared").exists()
        lock = read_lock_file(workspace / ".ai-cli")
        installed_packs = lock.get("installed_packs", []) if lock else []

        result = {
            "workspace": str(workspace),
            "workspace_source": (
                "explicit" if target_workspace_path else "request-or-legacy"
            ),
            "cli_type": server_ctx.cli_type,
            "shared_resources_path": str(shared_dir),
            "using_local_resources": has_local_shared,
            "installed_packs": installed_packs,
            "resources_note": (
                "WOPR resources live globally by default, deployed per CLI: "
                "~/.claude/{skills,agents,commands}/, ~/.copilot/{skills,agents}/ "
                "(commands install there as generated skills), and "
                "~/.gemini/{skills,commands}/. The local counters are "
                "workspace-resident overrides only and are typically zero on "
                "projects that have not customized WOPR."
            ),
            "resources": {
                "local": {
                    "skills": local_skills_count,
                    "agents": local_agents_count,
                    "commands": local_commands_count,
                    "context_docs": local_context_count,
                },
                "global": global_counts,
            },
            "files": {
                "todos": (workspace / "TO-DOS.md").exists(),
                "handoff": (workspace / "whats-next.md").exists(),
                "time_tracking": (workspace / "time-tracking.json").exists(),
                "notes": (workspace / "notes.json").exists(),
                "agents_md": (workspace / "AGENTS.md").exists(),
                "claude_md": (workspace / "CLAUDE.md").exists(),
                "gemini_md": (workspace / "GEMINI.md").exists(),
                "copilot_instructions_md": (
                    workspace / ".github" / "copilot-instructions.md"
                ).exists(),
                "wopr_yml": (workspace / "wopr.yml").exists(),
            },
        }

        return json.dumps(result, indent=2)

    @mcp.tool()
    async def get_help(
        topic: str = "",
        target_workspace_path: str = "",
        ctx: ToolContext | None = None,
    ) -> str:
        """Get help on how to use WOPR.

        Args:
            topic: Help topic. Options: overview, install, packs, commands, skills,
                   agents, mcp, cli. Leave empty to see all topics.

        Returns help text for the given topic, or a topic index if no topic given.
        Useful when users ask "how do I use this?" or need guidance on WOPR features.
        """
        from .help import get_help as _get_help

        try:
            ws = await resolve_request_workspace(target_workspace_path, ctx)
        except InvalidTargetWorkspaceError:
            ws = None
        return _get_help(topic or None, ws)


# ============================================================================
# APPLICATION FACTORY
# ============================================================================


def create_app(
    config: ServerConfig | None = None,
    workspace: str | None = None,
) -> FastMCP:
    """Create and configure the WOPR MCP server.

    Args:
        config: Server configuration. Created from environment if not provided.
        workspace: Override workspace path.

    Returns:
        Configured FastMCP instance ready to run.
    """
    if config is None:
        config = ServerConfig.from_env()

    ctx = ServerContext.init(config)

    if workspace:
        ctx.workspace = Path(workspace).expanduser().resolve()

    logger.info("Detected CLI type: %s", ctx.cli_type)

    mcp = FastMCP("wopr")

    # Every tool module registers unconditionally. The prior toolset
    # gated a block of utility tools on an ``extras`` pack lock entry;
    # that pack does not cross over, so the gate went with it.
    _register_server_tools(mcp)
    handoff.register(mcp)
    learnings.register(mcp)
    osv_check.register(mcp)
    skill_guard.register(mcp)
    routing_eval.register(mcp)
    skill_usage.register(mcp)
    stack_detect.register(mcp)
    wopr_yml.register(mcp)
    stub_writers.register(mcp)
    crew_contracts.register(mcp)
    pack_templates.register(mcp)

    return mcp


def run_server(workspace: str | None = None) -> int:
    """Run the MCP server."""
    logging.basicConfig(
        level=logging.INFO,
        format="[wopr] %(levelname)s: %(message)s",
        stream=sys.stderr,
    )

    mcp = create_app(workspace=workspace)
    mcp.run()
    return 0
