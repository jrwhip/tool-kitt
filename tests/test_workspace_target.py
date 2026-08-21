"""Request-scoped workspace resolution for MCP clients."""

from __future__ import annotations

from pathlib import Path

import pytest
from mcp.types import ListRootsResult, Root

from wopr.config import ServerConfig
from wopr.context import ServerContext
from wopr.tools._workspace_target import (
    InvalidTargetWorkspaceError,
    resolve_request_workspace,
)


class _FakeSession:
    def __init__(self, roots: list[Path]) -> None:
        self._roots = roots

    async def list_roots(self) -> ListRootsResult:
        return ListRootsResult(
            roots=[Root(uri=path.as_uri(), name=path.name) for path in self._roots]
        )


class _FakeContext:
    def __init__(self, roots: list[Path]) -> None:
        self.session = _FakeSession(roots)


async def test_single_mcp_root_resolves_per_request(tmp_path: Path) -> None:
    first = tmp_path / "first"
    second = tmp_path / "second"
    first.mkdir()
    second.mkdir()

    assert await resolve_request_workspace(ctx=_FakeContext([first])) == first
    assert await resolve_request_workspace(ctx=_FakeContext([second])) == second


async def test_explicit_target_overrides_mcp_root(tmp_path: Path) -> None:
    explicit = tmp_path / "explicit"
    advertised = tmp_path / "advertised"
    explicit.mkdir()
    advertised.mkdir()

    resolved = await resolve_request_workspace(
        str(explicit), _FakeContext([advertised])
    )

    assert resolved == explicit


async def test_multiple_mcp_roots_require_explicit_selection(
    tmp_path: Path,
) -> None:
    first = tmp_path / "first"
    second = tmp_path / "second"
    first.mkdir()
    second.mkdir()

    with pytest.raises(InvalidTargetWorkspaceError, match="multiple workspace roots"):
        await resolve_request_workspace(
            ctx=_FakeContext([first, second]),
            allow_legacy_config=False,
        )


async def test_no_request_workspace_fails_without_legacy_fallback() -> None:
    with pytest.raises(InvalidTargetWorkspaceError, match="target_workspace_path"):
        await resolve_request_workspace(
            ctx=_FakeContext([]),
            allow_legacy_config=False,
        )


async def test_legacy_workspace_remains_compatible(tmp_path: Path) -> None:
    ServerContext.reset()
    ServerContext.init(
        ServerConfig(cli_type="claude", wopr_workspace=str(tmp_path))
    )
    try:
        assert await resolve_request_workspace(ctx=_FakeContext([])) == tmp_path
    finally:
        ServerContext.reset()


async def test_copilot_does_not_fall_back_to_pinned_workspace(
    tmp_path: Path,
) -> None:
    ServerContext.reset()
    ServerContext.init(
        ServerConfig(cli_type="copilot", wopr_workspace=str(tmp_path))
    )
    try:
        with pytest.raises(InvalidTargetWorkspaceError):
            await resolve_request_workspace(ctx=_FakeContext([]))
    finally:
        ServerContext.reset()


async def test_copilot_ignores_inherited_claude_project_dir(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    claude = tmp_path / "claude"
    copilot = tmp_path / "copilot"
    claude.mkdir()
    copilot.mkdir()
    monkeypatch.setenv("CLAUDE_PROJECT_DIR", str(claude))
    ServerContext.reset()
    ServerContext.init(ServerConfig(cli_type="copilot"))
    try:
        assert await resolve_request_workspace(
            ctx=_FakeContext([copilot])
        ) == copilot
    finally:
        ServerContext.reset()
