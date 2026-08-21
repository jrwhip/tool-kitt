"""Tests for ``wopr.tools._version_check``.

``get_latest_tag`` shells out to ``git ls-remote``; every test here mocks
``subprocess.run`` rather than touching the network, matching the "no
network calls in the test suite" rule enforced by the autouse
``_no_network_version_check`` fixture in conftest.py.
"""

from __future__ import annotations

import subprocess
from types import SimpleNamespace

from wopr.tools import _version_check
from wopr.tools._version_check import check_version_drift, get_latest_tag


def _fake_ls_remote(tags: list[str], returncode: int = 0):
    stdout = "\n".join(f"deadbeef\trefs/tags/{t}" for t in tags)
    return lambda *a, **kw: SimpleNamespace(returncode=returncode, stdout=stdout, stderr="")


class TestGetLatestTag:
    def test_returns_highest_semver_tag(self, monkeypatch):
        monkeypatch.setattr(
            subprocess, "run", _fake_ls_remote(["v0.13.1", "v0.17.2", "v0.9.0"])
        )
        assert get_latest_tag() == "v0.17.2"

    def test_ignores_non_semver_refs(self, monkeypatch):
        monkeypatch.setattr(
            subprocess, "run", _fake_ls_remote(["v0.17.2", "not-a-version", "v0.17.2^{}"])
        )
        assert get_latest_tag() == "v0.17.2"

    def test_returns_none_on_nonzero_exit(self, monkeypatch):
        monkeypatch.setattr(subprocess, "run", _fake_ls_remote(["v0.17.2"], returncode=128))
        assert get_latest_tag() is None

    def test_returns_none_on_empty_output(self, monkeypatch):
        monkeypatch.setattr(subprocess, "run", _fake_ls_remote([]))
        assert get_latest_tag() is None

    def test_returns_none_on_timeout(self, monkeypatch):
        def raise_timeout(*a, **kw):
            raise subprocess.TimeoutExpired(cmd="git", timeout=2.0)

        monkeypatch.setattr(subprocess, "run", raise_timeout)
        assert get_latest_tag() is None

    def test_returns_none_when_git_missing(self, monkeypatch):
        def raise_oserror(*a, **kw):
            raise OSError("git not found")

        monkeypatch.setattr(subprocess, "run", raise_oserror)
        assert get_latest_tag() is None

    def test_does_not_wipe_subprocess_environment(self, monkeypatch):
        """Regression: env must be a copy of os.environ, not a bare dict.

        A bare ``{"GIT_TERMINAL_PROMPT": "0"}`` replacement would drop PATH
        and SSH_AUTH_SOCK, breaking git resolution and SSH auth entirely.
        """
        captured = {}

        def capture_env(*a, **kw):
            captured["env"] = kw.get("env")
            return SimpleNamespace(returncode=0, stdout="", stderr="")

        monkeypatch.setenv("SOME_MARKER_VAR", "present")
        monkeypatch.setattr(subprocess, "run", capture_env)
        get_latest_tag()
        assert captured["env"] is not None
        assert captured["env"].get("SOME_MARKER_VAR") == "present"
        assert captured["env"].get("GIT_TERMINAL_PROMPT") == "0"


class TestCheckVersionDrift:
    def test_behind_when_installed_is_lower(self, monkeypatch):
        monkeypatch.setattr(_version_check, "get_latest_tag", lambda **kw: "v0.17.2")
        drift = check_version_drift("0.13.1")
        assert drift.status == "behind"
        assert drift.latest == "v0.17.2"
        assert drift.installed == "0.13.1"

    def test_current_when_versions_match(self, monkeypatch):
        monkeypatch.setattr(_version_check, "get_latest_tag", lambda **kw: "v0.17.2")
        drift = check_version_drift("0.17.2")
        assert drift.status == "current"

    def test_ahead_when_installed_is_higher(self, monkeypatch):
        monkeypatch.setattr(_version_check, "get_latest_tag", lambda **kw: "v0.17.2")
        drift = check_version_drift("0.18.0-dev")
        assert drift.status == "ahead"

    def test_unknown_when_latest_could_not_be_determined(self, monkeypatch):
        monkeypatch.setattr(_version_check, "get_latest_tag", lambda **kw: None)
        drift = check_version_drift("0.17.2")
        assert drift.status == "unknown"
        assert drift.latest is None

    def test_unknown_when_installed_version_is_unparseable(self, monkeypatch):
        monkeypatch.setattr(_version_check, "get_latest_tag", lambda **kw: "v0.17.2")
        drift = check_version_drift("not-a-version")
        assert drift.status == "unknown"

    def test_never_raises_on_network_failure(self, monkeypatch):
        def raise_oserror(*a, **kw):
            raise OSError("network unreachable")

        monkeypatch.setattr(subprocess, "run", raise_oserror)
        drift = check_version_drift("0.17.2")
        assert drift.status == "unknown"
