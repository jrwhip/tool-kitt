"""Tests for ``kitt.tools.osv_check``.

No test in this module ever opens a real socket: every test that
exercises a "network" path monkeypatches ``osv_check._query_osv_transport``
(the sole transport function) directly, per the network-discipline
requirement for this feature. The one exception is
``TestQueryOsvTransport``, which monkeypatches ``urllib.request.urlopen``
itself to verify the transport's own failure->``_OsvUnreachable``
translation -- still no real network I/O, just a stubbed ``urlopen``.
"""

from __future__ import annotations

import json
import urllib.error
from pathlib import Path
from typing import Any

import pytest

from kitt.tools import osv_check


def _mal_vuln(vuln_id: str = "MAL-2024-1234", summary: str = "Known malicious package") -> dict:
    return {"id": vuln_id, "summary": summary}


class TestInferEcosystem:
    @pytest.mark.parametrize(
        ("command", "expected"),
        [
            ("npx", "npm"),
            ("npx.cmd", "npm"),
            ("/usr/local/bin/npx", "npm"),
            ("uvx", "PyPI"),
            ("uvx.cmd", "PyPI"),
            ("pipx", "PyPI"),
            ("node", None),
            ("kitt", None),
            ("python3", None),
        ],
    )
    def test_infers_expected_ecosystem(self, command: str, expected: str | None):
        assert osv_check._infer_ecosystem(command) == expected


class TestParsePackageFromArgs:
    def test_empty_args_returns_none(self):
        assert osv_check._parse_package_from_args([], "npm") == (None, None)

    def test_unscoped_npm_package_no_version(self):
        assert osv_check._parse_package_from_args(["cowsay"], "npm") == ("cowsay", None)

    def test_unscoped_npm_package_with_version(self):
        assert osv_check._parse_package_from_args(["cowsay@1.5.0"], "npm") == ("cowsay", "1.5.0")

    def test_unscoped_npm_package_at_latest_has_no_version(self):
        assert osv_check._parse_package_from_args(["cowsay@latest"], "npm") == ("cowsay", None)

    def test_scoped_npm_package_with_version(self):
        assert osv_check._parse_package_from_args(
            ["@modelcontextprotocol/server-foo@2.0.0"], "npm"
        ) == ("@modelcontextprotocol/server-foo", "2.0.0")

    def test_scoped_npm_package_no_version(self):
        assert osv_check._parse_package_from_args(
            ["@modelcontextprotocol/server-foo"], "npm"
        ) == ("@modelcontextprotocol/server-foo", None)

    def test_pypi_package_with_version(self):
        assert osv_check._parse_package_from_args(["some-pkg==1.2.3"], "PyPI") == (
            "some-pkg", "1.2.3",
        )

    def test_pypi_package_with_extras(self):
        assert osv_check._parse_package_from_args(["some-pkg[extra]==1.2.3"], "PyPI") == (
            "some-pkg", "1.2.3",
        )

    def test_leading_flags_are_skipped(self):
        assert osv_check._parse_package_from_args(["-y", "cowsay"], "npm") == ("cowsay", None)

    def test_package_flag_long_form_with_equals(self):
        assert osv_check._parse_package_from_args(
            ["--package=cowsay", "cowsay-bin"], "npm"
        ) == ("cowsay", None)

    def test_package_flag_long_form_space_separated(self):
        assert osv_check._parse_package_from_args(
            ["--package", "cowsay", "cowsay-bin"], "npm"
        ) == ("cowsay", None)

    def test_package_flag_short_form(self):
        assert osv_check._parse_package_from_args(["-p", "cowsay", "cowsay-bin"], "npm") == (
            "cowsay", None,
        )

    def test_only_flags_no_positional_returns_none(self):
        assert osv_check._parse_package_from_args(["-y"], "npm") == (None, None)


class TestQueryOsvTransport:
    """The one place a real ``urlopen`` failure is simulated (stubbed, not networked)."""

    def test_url_error_becomes_osv_unreachable(self, monkeypatch: pytest.MonkeyPatch):
        def _raise(*args, **kwargs):
            raise urllib.error.URLError("no route to host")

        monkeypatch.setattr(osv_check.urllib.request, "urlopen", _raise)
        with pytest.raises(osv_check._OsvUnreachable):
            osv_check._query_osv_transport(
                {"package": {"name": "x", "ecosystem": "npm"}}, timeout=1.0
            )

    def test_bad_json_becomes_osv_unreachable(self, monkeypatch: pytest.MonkeyPatch):
        class _FakeResp:
            def __enter__(self):
                return self

            def __exit__(self, *exc):
                return False

            def read(self):
                return b"not json"

        monkeypatch.setattr(osv_check.urllib.request, "urlopen", lambda *a, **kw: _FakeResp())
        with pytest.raises(osv_check._OsvUnreachable):
            osv_check._query_osv_transport(
                {"package": {"name": "x", "ecosystem": "npm"}}, timeout=1.0
            )


class TestCheckPackageForMalware:
    def test_non_npx_command_returns_none_without_querying(self, monkeypatch: pytest.MonkeyPatch):
        calls = []
        monkeypatch.setattr(
            osv_check, "_query_osv_transport", lambda *a, **kw: calls.append(1) or {"vulns": []}
        )
        assert osv_check.check_package_for_malware("node", ["server.js"]) is None
        assert calls == []

    def test_clean_package_returns_none(self, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.setattr(osv_check, "_query_osv_transport", lambda *a, **kw: {"vulns": []})
        assert osv_check.check_package_for_malware("npx", ["cowsay"]) is None

    def test_regular_cve_is_ignored(self, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.setattr(
            osv_check,
            "_query_osv_transport",
            lambda *a, **kw: {"vulns": [{"id": "CVE-2024-9999", "summary": "not malware"}]},
        )
        assert osv_check.check_package_for_malware("npx", ["cowsay"]) is None

    def test_malware_advisory_returns_block_message(self, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.setattr(
            osv_check,
            "_query_osv_transport",
            lambda *a, **kw: {"vulns": [_mal_vuln()]},
        )
        result = osv_check.check_package_for_malware("npx", ["evil-package"])
        assert result is not None
        assert "BLOCKED" in result
        assert "evil-package" in result
        assert "MAL-2024-1234" in result

    def test_unreachable_network_fails_open(self, monkeypatch: pytest.MonkeyPatch):
        def _raise(*args, **kwargs):
            raise osv_check._OsvUnreachable("down")

        monkeypatch.setattr(osv_check, "_query_osv_transport", _raise)
        assert osv_check.check_package_for_malware("npx", ["cowsay"]) is None

    def test_unparseable_args_returns_none(self, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.setattr(osv_check, "_query_osv_transport", lambda *a, **kw: {"vulns": []})
        assert osv_check.check_package_for_malware("npx", []) is None


class TestEnumerateRegisteredMcpEntries:
    def _fake_home(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
        home = tmp_path / "home"
        home.mkdir()
        monkeypatch.setattr(Path, "home", lambda: home)
        return home

    def test_no_configs_returns_empty(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
        self._fake_home(tmp_path, monkeypatch)
        assert osv_check._enumerate_registered_mcp_entries() == {}

    def test_merges_across_all_three_configs(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ):
        home = self._fake_home(tmp_path, monkeypatch)
        (home / ".claude.json").write_text(
            json.dumps({"mcpServers": {"foo": {"command": "npx", "args": ["foo-pkg"]}}}),
            encoding="utf-8",
        )
        (home / ".copilot").mkdir()
        (home / ".copilot" / "mcp-config.json").write_text(
            json.dumps({"mcpServers": {"bar": {"command": "uvx", "args": ["bar-pkg"]}}}),
            encoding="utf-8",
        )
        (home / ".gemini").mkdir()
        (home / ".gemini" / "settings.json").write_text(
            json.dumps({"mcpServers": {"baz": {"command": "node", "args": ["baz.js"]}}}),
            encoding="utf-8",
        )
        entries = osv_check._enumerate_registered_mcp_entries()
        assert set(entries) == {"foo", "bar", "baz"}
        assert entries["foo"]["command"] == "npx"

    def test_first_config_wins_on_name_collision(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ):
        home = self._fake_home(tmp_path, monkeypatch)
        (home / ".claude.json").write_text(
            json.dumps({"mcpServers": {"kitt": {"command": "kitt", "args": []}}}),
            encoding="utf-8",
        )
        (home / ".copilot").mkdir()
        (home / ".copilot" / "mcp-config.json").write_text(
            json.dumps({"mcpServers": {"kitt": {"command": "npx", "args": ["evil"]}}}),
            encoding="utf-8",
        )
        entries = osv_check._enumerate_registered_mcp_entries()
        assert entries["kitt"]["command"] == "kitt"


class TestCheckMcpServersForMalware:
    def _fake_home_with_servers(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, servers: dict[str, Any]
    ) -> Path:
        home = tmp_path / "home"
        home.mkdir()
        monkeypatch.setattr(Path, "home", lambda: home)
        (home / ".claude.json").write_text(
            json.dumps({"mcpServers": servers}), encoding="utf-8"
        )
        return home

    def test_default_is_skipped_and_never_queries_network(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ):
        self._fake_home_with_servers(
            tmp_path, monkeypatch, {"foo": {"command": "npx", "args": ["foo-pkg"]}}
        )
        calls = []
        monkeypatch.setattr(
            osv_check, "_query_osv_transport", lambda *a, **kw: calls.append(1) or {"vulns": []}
        )
        result = json.loads(osv_check.check_mcp_servers_for_malware())
        assert result["status"] == "skipped"
        assert "foo" in result["servers_registered"]
        assert calls == []

    def test_enabled_clean_servers_report_ok(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ):
        self._fake_home_with_servers(
            tmp_path,
            monkeypatch,
            {
                "foo": {"command": "npx", "args": ["foo-pkg"]},
                "local": {"command": "kitt", "args": []},
            },
        )
        monkeypatch.setattr(osv_check, "_query_osv_transport", lambda *a, **kw: {"vulns": []})
        result = json.loads(osv_check.check_mcp_servers_for_malware(enable_network=True))
        assert result["status"] == "ok"
        assert result["checked_servers"] == ["foo"]
        assert result["findings"] == []
        assert result["went_offline"] is False

    def test_enabled_finds_malware(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
        self._fake_home_with_servers(
            tmp_path, monkeypatch, {"evil": {"command": "npx", "args": ["evil-pkg"]}}
        )
        monkeypatch.setattr(
            osv_check, "_query_osv_transport", lambda *a, **kw: {"vulns": [_mal_vuln()]}
        )
        result = json.loads(osv_check.check_mcp_servers_for_malware(enable_network=True))
        assert result["status"] == "findings"
        assert result["findings"][0]["server_name"] == "evil"
        assert "evil-pkg" in result["findings"][0]["message"]

    def test_unreachable_network_reports_skipped_offline_and_stops_early(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ):
        self._fake_home_with_servers(
            tmp_path,
            monkeypatch,
            {
                "alpha": {"command": "npx", "args": ["alpha-pkg"]},
                "beta": {"command": "npx", "args": ["beta-pkg"]},
            },
        )
        calls = []

        def _raise(*args, **kwargs):
            calls.append(1)
            raise osv_check._OsvUnreachable("offline")

        monkeypatch.setattr(osv_check, "_query_osv_transport", _raise)
        result = json.loads(osv_check.check_mcp_servers_for_malware(enable_network=True))
        assert result["status"] == "skipped_offline"
        assert result["went_offline"] is True
        # Stops after the first unreachable result rather than retrying
        # the same timeout for every remaining npx/uvx server.
        assert len(calls) == 1

    def test_non_npx_uvx_servers_are_never_queried(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ):
        self._fake_home_with_servers(
            tmp_path,
            monkeypatch,
            {
                "local-tool": {"command": "kitt", "args": []},
                "docker-based": {"command": "docker", "args": ["run", "some/image"]},
            },
        )
        calls = []
        monkeypatch.setattr(
            osv_check, "_query_osv_transport", lambda *a, **kw: calls.append(1) or {"vulns": []}
        )
        result = json.loads(osv_check.check_mcp_servers_for_malware(enable_network=True))
        assert result["status"] == "ok"
        assert result["checked_servers"] == []
        assert calls == []

    def test_no_registered_servers_reports_ok(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ):
        home = tmp_path / "home"
        home.mkdir()
        monkeypatch.setattr(Path, "home", lambda: home)
        result = json.loads(osv_check.check_mcp_servers_for_malware(enable_network=True))
        assert result["status"] == "ok"
        assert result["checked_servers"] == []


class TestRegister:
    def test_register_registers_expected_tools(self, fake_mcp):
        osv_check.register(fake_mcp)
        assert sorted(fake_mcp.registered) == ["check_mcp_servers_for_malware"]
