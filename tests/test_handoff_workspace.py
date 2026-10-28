"""Handoff persistence + workspace-resolution robustness.

``create_handoff`` / ``get_handoff`` resolve their target by precedence:
an explicit ``target_workspace_path`` wins, else the per-CLI ambient
default (``CLAUDE_PROJECT_DIR`` on Claude Code), else a loud error. There
is no fallback to the server's launch directory, and a missing or stale
``KITT_WORKSPACE`` fails loud instead of silently binding to whatever
worktree the process spawned in (the failure mode that once overwrote an
unrelated project's handoff).
"""

from __future__ import annotations

from pathlib import Path

import pytest

from kitt.config import ServerConfig
from kitt.context import ServerContext, WorkspaceNotConfiguredError
from kitt.tools.handoff import create_handoff, get_handoff


class TestCreateHandoff:
    async def test_writes_and_reads_back(self, workspace: Path) -> None:
        result = await create_handoff(
            str(workspace), summary="did stuff", next_steps="do next", context="extra ctx"
        )
        assert "Created handoff document" in result
        assert (workspace / "whats-next.md").exists()
        content = await get_handoff(str(workspace))
        assert "did stuff" in content
        assert "do next" in content
        assert "extra ctx" in content

    async def test_no_target_and_no_ambient_errors(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.delenv("CLAUDE_PROJECT_DIR", raising=False)
        result = await create_handoff(summary="s", next_steps="n")
        assert result.startswith("Error")
        assert "target_workspace_path" in result

    async def test_rejects_relative_target(self) -> None:
        result = await create_handoff("relative/dir", summary="s", next_steps="n")
        assert result.startswith("Error")
        assert "absolute" in result

    async def test_rejects_nonexistent_target(self, tmp_path: Path) -> None:
        missing = tmp_path / "nope" / "deeper"
        result = await create_handoff(str(missing), summary="s", next_steps="n")
        assert result.startswith("Error")
        assert not (missing / "whats-next.md").exists()

    async def test_no_clobber_without_overwrite(self, workspace: Path) -> None:
        await create_handoff(str(workspace), summary="first summary", next_steps="n")
        result = await create_handoff(str(workspace), summary="second summary", next_steps="n")
        assert result.startswith("Error")
        assert "overwrite" in result
        # The unread handoff is preserved, not destroyed.
        assert "first summary" in await get_handoff(str(workspace))

    async def test_overwrite_replaces(self, workspace: Path) -> None:
        await create_handoff(str(workspace), summary="first summary", next_steps="n")
        result = await create_handoff(
            str(workspace), summary="second summary", next_steps="n", overwrite=True
        )
        assert "Created handoff document" in result
        content = await get_handoff(str(workspace))
        assert "second summary" in content
        assert "first summary" not in content


class TestAmbientTarget:
    async def test_ambient_resolves_from_claude_project_dir(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        proj = tmp_path / "session-project"
        proj.mkdir()
        monkeypatch.setenv("CLAUDE_PROJECT_DIR", str(proj))
        # No target passed: should land in CLAUDE_PROJECT_DIR.
        result = await create_handoff(summary="ambient", next_steps="n")
        assert "Created handoff document" in result
        assert (proj / "whats-next.md").exists()
        assert "ambient" in await get_handoff()

    async def test_explicit_target_overrides_ambient(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        ambient = tmp_path / "ambient-proj"
        ambient.mkdir()
        explicit = tmp_path / "explicit-proj"
        explicit.mkdir()
        monkeypatch.setenv("CLAUDE_PROJECT_DIR", str(ambient))
        await create_handoff(str(explicit), summary="explicit wins", next_steps="n")
        assert (explicit / "whats-next.md").exists()
        assert not (ambient / "whats-next.md").exists()


class TestGetHandoff:
    async def test_missing_file_message(self, workspace: Path) -> None:
        result = await get_handoff(str(workspace))
        assert "No whats-next.md" in result

    async def test_no_target_and_no_ambient_errors(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.delenv("CLAUDE_PROJECT_DIR", raising=False)
        result = await get_handoff()
        assert result.startswith("Error")
        assert "target_workspace_path" in result


class TestResolveWorkspace:
    def test_dead_env_workspace_fails_loud(self, tmp_path: Path) -> None:
        dead = tmp_path / "deleted-workspace"  # never created
        assert not dead.exists()
        ServerContext.reset()
        ServerContext.init(ServerConfig(cli_type="claude", kitt_workspace=str(dead)))
        try:
            with pytest.raises(WorkspaceNotConfiguredError):
                _ = ServerContext.get().workspace
        finally:
            ServerContext.reset()

    def test_no_config_fails_loud(self) -> None:
        ServerContext.reset()
        ServerContext.init(ServerConfig(cli_type="claude"))
        try:
            with pytest.raises(WorkspaceNotConfiguredError):
                _ = ServerContext.get().workspace
        finally:
            ServerContext.reset()

    def test_uses_existing_env_workspace(self, tmp_path: Path) -> None:
        live = tmp_path / "live-ws"
        live.mkdir()
        ServerContext.reset()
        ctx = ServerContext.init(
            ServerConfig(cli_type="claude", kitt_workspace=str(live))
        )
        try:
            assert ctx.workspace == live
        finally:
            ServerContext.reset()
