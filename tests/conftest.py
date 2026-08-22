"""Shared pytest fixtures for the WOPR test suite.

Consolidates the ``workspace`` fixture (``tmp_path / "ws"`` +
``ServerContext`` reset + ``WOPR_HOME`` env override) and the
``FakeMcp`` registration-recording helper that several test modules
would otherwise each inline.

The fixtures are namespaced as plain function fixtures with no
custom prefix; pytest discovers them via this conftest's location
under ``tests/`` and makes them available to every test in the
suite without imports.
"""

from __future__ import annotations

import sys
from collections.abc import Callable, Iterator
from pathlib import Path
from typing import Any

import pytest

from wopr import catalog
from wopr.config import ENV_WOPR_HOME, ServerConfig
from wopr.context import ServerContext

_REAL_HOME = Path.home().resolve()


def _rebind_everywhere(
    monkeypatch: pytest.MonkeyPatch, name: str, real: Any, replacement: Any
) -> None:
    """Point every ``sys.modules`` binding of ``real`` at ``replacement``.

    Modules import these helpers by name (``from ..catalog import
    get_global_home``), so patching only the defining module would leave
    every importer calling the unguarded original. Collection imports all
    source and test modules before fixtures run, so the sweep sees them.
    """
    for module in list(sys.modules.values()):
        if getattr(module, name, None) is real:
            monkeypatch.setattr(module, name, replacement)


@pytest.fixture(autouse=True)
def _wopr_home_never_points_at_the_real_home(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Make it impossible for a test to read or write the real ``~/.wopr``.

    Everything WOPR keeps globally -- learnings, the workspace registry,
    the skill-usage sidecar -- is
    addressed through :func:`catalog.get_global_home`, which falls back to
    ``$HOME/.wopr`` when ``WOPR_HOME`` is unset. A test that forgets the
    ``workspace`` / ``isolated_env`` fixture therefore does not fail: it
    silently mutates the operator's real state. That is not hypothetical
    either -- ``test_multi_workspace_tools`` used a bare ``tmp_path`` and
    accumulated dozens of ``wopr-local`` invocations in the developer's
    ``~/.wopr/skill-usage.json`` before anyone noticed, because
    ``run_skill`` records telemetry as a side effect.

    Two layers, because either one alone leaves a hole:

    1. Default ``WOPR_HOME`` to a per-test tmp dir, so a test that never
       thinks about global state still gets isolation. Fixtures and tests
       that set their own value run after this and win.
    2. Guard :func:`get_global_home` itself, so an explicit override --
       or a config/``ServerContext`` path that bypasses the env var --
       cannot resolve back inside the real home. This one fails loudly
       instead of corrupting state, which is the only acceptable outcome
       for a leak nobody would otherwise see.
    """
    monkeypatch.setenv(ENV_WOPR_HOME, str(tmp_path / "wopr-home"))

    real = catalog.get_global_home

    def _guarded(_real: Any = real) -> Path:
        home = _real()
        if home == _REAL_HOME or _REAL_HOME in home.parents:
            raise AssertionError(
                f"get_global_home() resolved to {home}, inside the real home "
                f"({_REAL_HOME}). A test is about to read or write the "
                f"operator's actual WOPR state; set WOPR_HOME to a tmp dir "
                f"(the `workspace` / `isolated_env` fixtures already do)."
            )
        return home

    _rebind_everywhere(monkeypatch, "get_global_home", real, _guarded)


@pytest.fixture
def workspace(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[Path]:
    """Provide an isolated workspace with a wired-up ServerContext.

    Creates ``tmp_path / "ws"`` as the workspace, initializes a fresh
    ``ServerContext`` pointing at it, and isolates ``WOPR_HOME`` to a
    sibling tmp dir so tests cannot leak into the operator's real
    ``~/.wopr``. Resets the singleton on both entry and exit so a
    crashing test cannot bleed state into the next one.

    Tests that need both the workspace AND the WOPR_HOME path can use
    :func:`isolated_env` instead.
    """
    ws = tmp_path / "ws"
    ws.mkdir()
    ServerContext.reset()
    ctx = ServerContext.init(ServerConfig(cli_type="claude"))
    ctx.workspace = ws
    monkeypatch.setenv("WOPR_HOME", str(tmp_path / "wopr-home"))
    yield ws
    ServerContext.reset()


@pytest.fixture
def isolated_env(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> Iterator[tuple[Path, Path]]:
    """Like :func:`workspace`, but also yields the ``WOPR_HOME`` path.

    Tests that exercise the cross-workspace registry need the home
    path directly; tests that only care about the workspace use the
    simpler ``workspace`` fixture.
    """
    ws = tmp_path / "ws"
    ws.mkdir()
    home = tmp_path / "wopr-home"
    home.mkdir()
    ServerContext.reset()
    ctx = ServerContext.init(ServerConfig(cli_type="claude"))
    ctx.workspace = ws
    monkeypatch.setenv("WOPR_HOME", str(home))
    yield ws, home
    ServerContext.reset()


class _FakeMcp:
    """Minimal MCP server stub that records tool registrations.

    Used by every ``TestRegister`` class to verify that a tool
    module's ``register(mcp)`` wires up the expected set of tools.
    Replaces four near-identical inline class definitions.
    """

    def __init__(self) -> None:
        self.registered: list[str] = []

    def tool(self) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
        def decorator(fn: Callable[..., Any]) -> Callable[..., Any]:
            self.registered.append(fn.__name__)
            return fn

        return decorator


@pytest.fixture
def fake_mcp() -> _FakeMcp:
    """Fresh :class:`_FakeMcp` per test.

    Tests use ``fake_mcp.registered`` as the assertion surface,
    typically with ``sorted(fake_mcp.registered) == [...]`` to pin
    the expected tool set without depending on registration order.
    """
    return _FakeMcp()
