"""The test suite must never read or write the operator's real ``~/.wopr``.

Every globally-scoped WOPR artifact -- install manifest, workspace
registry, learnings, dismissals, skill-usage telemetry -- is addressed
through :func:`catalog.get_global_home`. Its ``$HOME/.wopr`` fallback
means a test that simply forgets to isolate ``WOPR_HOME`` does not fail;
it quietly mutates real state. ``test_multi_workspace_tools`` did exactly
that for as long as ``run_skill`` has recorded telemetry.

These tests pin the two conftest layers that close that class of bug.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from wopr.catalog import get_global_home
from wopr.config import ENV_WOPR_HOME
from wopr.tools._skill_usage import usage_path


def test_global_home_defaults_to_a_per_test_tmp_dir(tmp_path: Path) -> None:
    """A test that never mentions ``WOPR_HOME`` is still isolated.

    This is the layer that would have caught the skill-usage leak: no
    fixture, no env setup, just an incidental call through the global
    home.
    """
    assert get_global_home() == (tmp_path / "wopr-home").resolve()
    assert usage_path().parent == (tmp_path / "wopr-home").resolve()


def test_global_home_refuses_to_resolve_inside_the_real_home(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Losing the ``WOPR_HOME`` override is a loud failure, not a silent write.

    The env default is not enough on its own: ``get_global_home`` also
    reads ``ServerContext``'s config, and a test can delete or override
    the env var. Whatever the route, resolving back into the real home
    must raise rather than hand out a writable path.
    """
    monkeypatch.delenv(ENV_WOPR_HOME, raising=False)

    with pytest.raises(AssertionError, match="inside the real home"):
        get_global_home()


def test_explicit_override_into_the_real_home_is_rejected(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Even a deliberate-looking override cannot target the real home."""
    monkeypatch.setenv(ENV_WOPR_HOME, str(Path.home() / ".wopr"))

    with pytest.raises(AssertionError, match="inside the real home"):
        get_global_home()
