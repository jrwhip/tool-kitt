"""Centralized environment variable access for KITT."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Literal, TypeAlias

from .product import ENV_PREFIX

CliType: TypeAlias = Literal["claude", "copilot", "gemini", "unknown"]


# ============================================================================
# Environment variable names
# ============================================================================
#
# Every environment variable KITT reads, named in one place. Other
# modules that genuinely cannot route through ``ServerConfig`` (CLI
# subcommand entry points that run before ``ServerContext.init``) should
# import the relevant constant from here rather than hard-coding the
# string, so a rename is one edit instead of a grep-and-pray.

ENV_AI_CLI_TYPE = "AI_CLI_TYPE"
ENV_AI_CLI_WORKSPACE = "AI_CLI_WORKSPACE"
ENV_KITT_WORKSPACE = f"{ENV_PREFIX}WORKSPACE"
# Legacy alias for ``KITT_WORKSPACE``: the name the 2025 ``tool-kitt``
# release read. Kept so a shell that still exports it keeps working.
ENV_TOOL_KITT_WORKSPACE = "TOOL_KITT_WORKSPACE"
ENV_KITT_CATALOG = f"{ENV_PREFIX}CATALOG"
ENV_KITT_HOME = f"{ENV_PREFIX}HOME"
# Set by the generated ``kitt-core/.mcp.json`` to ``${CLAUDE_PLUGIN_ROOT}``.
# Present only when the server runs from a Claude Code plugin install.
ENV_KITT_PLUGIN_ROOT = f"{ENV_PREFIX}PLUGIN_ROOT"

ENV_CLAUDE_CODE_ENTRYPOINT = "CLAUDE_CODE_ENTRYPOINT"
ENV_GITHUB_COPILOT_TOKEN = "GITHUB_COPILOT_TOKEN"
ENV_GH_COPILOT_TOKEN = "GH_COPILOT_TOKEN"
ENV_GEMINI_API_KEY = "GEMINI_API_KEY"

ENV_TOGGL_API_KEY = "TOGGL_API_KEY"


# ============================================================================
# Plugin install layout
# ============================================================================
#
# ``kitt build-plugins`` emits the server INSIDE the kitt-core plugin.
# These two names are the contract between the generator and the
# runtime: change them here and both sides move together.

PLUGIN_SERVER_DIRNAME = "server"
PLUGIN_RESOURCES_DIRNAME = "resources"


def plugin_resources_root() -> Path | None:
    """Return the bundled resources directory of a plugin install.

    ``None`` when ``KITT_PLUGIN_ROOT`` is unset, which is every
    non-plugin context (source checkout, editable install, pip
    install). Callers treat that as "fall back to the existing
    repo-then-package path arithmetic".

    Read straight from the environment rather than from
    :class:`ServerConfig`, for the same reason
    :func:`catalog.get_global_home` does: the resource resolvers are
    module-level helpers that run on CLI paths where no
    ``ServerContext`` exists yet. The value is process-level and
    immutable, so there is nothing for a config object to add beyond
    an import cycle.
    """
    raw = os.environ.get(ENV_KITT_PLUGIN_ROOT, "").strip()
    if not raw:
        return None
    return (
        Path(raw).expanduser().resolve()
        / PLUGIN_SERVER_DIRNAME
        / PLUGIN_RESOURCES_DIRNAME
    )


def _detect_cli_type(
    explicit: str,
    claude_entrypoint: str | None,
    copilot_token: str | None,
    gemini_key: str | None,
) -> CliType:
    """Detect which AI CLI is running based on environment signals."""
    if explicit == "claude":
        return "claude"
    if explicit == "copilot":
        return "copilot"
    if explicit == "gemini":
        return "gemini"
    if claude_entrypoint:
        return "claude"
    if copilot_token:
        return "copilot"
    if gemini_key:
        return "gemini"
    return "unknown"


@dataclass(frozen=True)
class ServerConfig:
    """All environment variable reads happen here.

    Instantiated once at server startup or during init.
    Frozen to prevent accidental mutation after creation.
    """

    # Workspace paths (checked in priority order by ServerContext)
    ai_cli_workspace: str | None = None
    kitt_workspace: str | None = None

    # Detected CLI type
    cli_type: CliType = "unknown"

    # Catalog
    catalog_path: str | None = None

    # KITT home directory (where global packs, ~/.kitt/LEARNINGS.md, and
    # ~/.kitt/workspaces.txt live). ``None`` falls back to ``~/.kitt``.
    kitt_home: str | None = None

    # External services
    toggl_api_key: str | None = None

    @classmethod
    def from_env(cls) -> ServerConfig:
        """Create config by reading all relevant environment variables."""
        explicit_cli = os.environ.get(ENV_AI_CLI_TYPE, "").lower()
        claude_entrypoint = os.environ.get(ENV_CLAUDE_CODE_ENTRYPOINT)
        copilot_token = (
            os.environ.get(ENV_GITHUB_COPILOT_TOKEN)
            or os.environ.get(ENV_GH_COPILOT_TOKEN)
        )
        gemini_key = os.environ.get(ENV_GEMINI_API_KEY)

        return cls(
            ai_cli_workspace=os.environ.get(ENV_AI_CLI_WORKSPACE),
            kitt_workspace=(
                os.environ.get(ENV_KITT_WORKSPACE)
                or os.environ.get(ENV_TOOL_KITT_WORKSPACE)
            ),
            cli_type=_detect_cli_type(explicit_cli, claude_entrypoint, copilot_token, gemini_key),
            catalog_path=os.environ.get(ENV_KITT_CATALOG),
            kitt_home=os.environ.get(ENV_KITT_HOME),
            toggl_api_key=os.environ.get(ENV_TOGGL_API_KEY),
        )
