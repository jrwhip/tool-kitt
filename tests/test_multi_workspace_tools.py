"""Workspace-scoped resolution does not leak across projects.

The prior toolset's version of this module also exercised ``run_skill``,
``add_note`` / ``list_notes``, ``list_projects`` and ``log_time``. None
of those tools cross over, so only the project-path containment case
survives here; the handoff and learnings tools carry the same
cross-workspace isolation guarantees and are covered by their own
modules.
"""

from __future__ import annotations

from pathlib import Path

from wopr.config import ServerConfig
from wopr.context import ServerContext


def test_project_name_cannot_escape_selected_workspace(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    sibling = tmp_path / "sibling"
    workspace.mkdir()
    sibling.mkdir()
    ServerContext.reset()
    server_ctx = ServerContext.init(ServerConfig(cli_type="copilot"))
    try:
        _path, error = server_ctx.resolve_project_path("../sibling", workspace)
        assert error is not None
        assert "escapes workspace" in error
    finally:
        ServerContext.reset()
