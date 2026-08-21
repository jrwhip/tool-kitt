"""Centralized environment variable access for WOPR."""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Literal, TypeAlias

CliType: TypeAlias = Literal["claude", "copilot", "gemini", "unknown"]


# ============================================================================
# Environment variable names
# ============================================================================
#
# Every environment variable WOPR reads, named in one place. Other
# modules that genuinely cannot route through ``ServerConfig`` (CLI
# subcommand entry points that run before ``ServerContext.init``) should
# import the relevant constant from here rather than hard-coding the
# string, so a rename is one edit instead of a grep-and-pray.

ENV_AI_CLI_TYPE = "AI_CLI_TYPE"
ENV_AI_CLI_WORKSPACE = "AI_CLI_WORKSPACE"
ENV_WOPR_WORKSPACE = "WOPR_WORKSPACE"
# Legacy alias for ``WOPR_WORKSPACE``. Kept for back-compat with
# operator shells that still export the old name. Drop once the
# 0.x → 1.0 migration window closes.
ENV_TOOL_KITT_WORKSPACE = "TOOL_KITT_WORKSPACE"
ENV_WOPR_CATALOG = "WOPR_CATALOG"
ENV_WOPR_HOME = "WOPR_HOME"

ENV_CLAUDE_CODE_ENTRYPOINT = "CLAUDE_CODE_ENTRYPOINT"
ENV_GITHUB_COPILOT_TOKEN = "GITHUB_COPILOT_TOKEN"
ENV_GH_COPILOT_TOKEN = "GH_COPILOT_TOKEN"
ENV_GEMINI_API_KEY = "GEMINI_API_KEY"

ENV_TOGGL_API_KEY = "TOGGL_API_KEY"


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
    wopr_workspace: str | None = None

    # Detected CLI type
    cli_type: CliType = "unknown"

    # Catalog
    catalog_path: str | None = None

    # WOPR home directory (where global packs, ~/.wopr/LEARNINGS.md, and
    # ~/.wopr/workspaces.txt live). ``None`` falls back to ``~/.wopr``.
    wopr_home: str | None = None

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
            wopr_workspace=(
                os.environ.get(ENV_WOPR_WORKSPACE)
                or os.environ.get(ENV_TOOL_KITT_WORKSPACE)
            ),
            cli_type=_detect_cli_type(explicit_cli, claude_entrypoint, copilot_token, gemini_key),
            catalog_path=os.environ.get(ENV_WOPR_CATALOG),
            wopr_home=os.environ.get(ENV_WOPR_HOME),
            toggl_api_key=os.environ.get(ENV_TOGGL_API_KEY),
        )
