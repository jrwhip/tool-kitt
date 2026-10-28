"""Tests for the ``kitt`` command line surface.

The parser moved from one flat positional to real subparsers when
``build-plugins`` and ``learnings`` landed, so the first class here pins
the invocations that already existed: a regression in argument order or
in a dispatch branch would otherwise only show up when a hook or an
operator hit it.

The ``learnings`` tests exercise the real coroutines, not a mock. The
whole point of the subcommand is that a Bash-capable agent gets the
same validation the MCP tool applies; a test against a stub would prove
nothing about that.
"""

from __future__ import annotations

import io
from pathlib import Path

import pytest

from kitt import cli

VALID_ENTRY = """## LRN-2026-08-21-a: Prefer explicit workspace paths

**Context**: Shell callers have no MCP roots to infer from.

**Lesson**: Pass the workspace explicitly.
"""


class TestParserShape:
    def test_no_subcommand_means_run_the_server(self, monkeypatch: pytest.MonkeyPatch):
        called: list[str | None] = []
        monkeypatch.setattr(
            "kitt.server.run_server", lambda ws: called.append(ws) or 0
        )
        assert cli.main([]) == 0
        assert called == [None]

    def test_workspace_option_is_accepted_before_the_subcommand(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ):
        seen: list[Path] = []
        monkeypatch.setattr(
            "kitt.manager.cmd_list", lambda ws, is_global=False: seen.append(ws) or 0
        )
        assert cli.main(["--workspace", str(tmp_path), "list"]) == 0
        assert seen == [tmp_path.resolve()]

    def test_workspace_option_is_accepted_after_the_subcommand(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ):
        """The old flat parser allowed either order; keep it that way."""
        seen: list[Path] = []
        monkeypatch.setattr(
            "kitt.manager.cmd_list", lambda ws, is_global=False: seen.append(ws) or 0
        )
        assert cli.main(["list", "--workspace", str(tmp_path)]) == 0
        assert seen == [tmp_path.resolve()]

    def test_global_flag_reaches_the_list_command(
        self, monkeypatch: pytest.MonkeyPatch
    ):
        seen: list[bool] = []
        monkeypatch.setattr(
            "kitt.manager.cmd_list",
            lambda ws, is_global=False: seen.append(is_global) or 0,
        )
        assert cli.main(["list", "--global"]) == 0
        assert seen == [True]

    def test_catalog_option_reaches_the_catalog_command(
        self, monkeypatch: pytest.MonkeyPatch
    ):
        seen: list[str | None] = []
        monkeypatch.setattr(
            "kitt.manager.cmd_catalog", lambda path: seen.append(path) or 0
        )
        assert cli.main(["catalog", "--catalog", "/tmp/cat"]) == 0
        assert seen == ["/tmp/cat"]

    def test_skill_usage_args_arrive_as_bare_positionals(
        self, monkeypatch: pytest.MonkeyPatch
    ):
        """The Stop hook shells out to `kitt skill-usage record ...`."""
        seen: list[list[str]] = []
        monkeypatch.setattr(
            "kitt.skill_usage_cli.cmd_skill_usage",
            lambda args, ws: seen.append(args) or 0,
        )
        assert cli.main(["skill-usage", "record", "claude-skill", "kitt-doctor"]) == 0
        assert seen == [["record", "claude-skill", "kitt-doctor"]]

    def test_help_topic_is_optional(self, monkeypatch: pytest.MonkeyPatch):
        seen: list[str | None] = []
        monkeypatch.setattr(
            "kitt.help.get_help", lambda topic, ws: seen.append(topic) or ""
        )
        assert cli.main(["help"]) == 0
        assert cli.main(["help", "packs"]) == 0
        assert seen == [None, "packs"]

    def test_version_flag_exits_cleanly(self, capsys: pytest.CaptureFixture[str]):
        with pytest.raises(SystemExit) as excinfo:
            cli.main(["--version"])
        assert excinfo.value.code == 0
        assert "kitt" in capsys.readouterr().out

    def test_serve_entry_point_runs_the_server(self, monkeypatch: pytest.MonkeyPatch):
        """`kitt-serve` is what the generated .mcp.json shim executes."""
        called: list[str | None] = []
        monkeypatch.setattr(
            "kitt.server.run_server", lambda ws: called.append(ws) or 0
        )
        assert cli.serve() == 0
        assert called == [None]


class TestBuildPluginsSubcommand:
    def test_out_is_required(self):
        with pytest.raises(SystemExit) as excinfo:
            cli.main(["build-plugins"])
        assert excinfo.value.code == 2

    def test_generates_the_marketplace(self, tmp_path: Path):
        out = tmp_path / "kitt-plugins"
        assert cli.main(["build-plugins", "--out", str(out)]) == 0
        assert (out / ".claude-plugin" / "marketplace.json").is_file()
        assert (out / "kitt-core" / ".claude-plugin" / "plugin.json").is_file()

    def test_hosts_the_manifest_at_the_marketplace_root(self, tmp_path: Path):
        root = tmp_path / "repo"
        out = root / "plugins"
        assert cli.main(
            ["build-plugins", "--out", str(out), "--marketplace-root", str(root)]
        ) == 0
        assert (root / ".claude-plugin" / "marketplace.json").is_file()
        assert not (out / ".claude-plugin").exists()
        assert (out / "kitt-core" / ".claude-plugin" / "plugin.json").is_file()

    def test_rejects_an_out_dir_outside_the_marketplace_root(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ):
        assert cli.main(
            [
                "build-plugins",
                "--out", str(tmp_path / "elsewhere"),
                "--marketplace-root", str(tmp_path / "repo"),
            ]
        ) == 1
        assert "must sit inside" in capsys.readouterr().err

    def test_reports_the_failure_and_exits_nonzero(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ):
        out = tmp_path / "not-ours"
        out.mkdir()
        (out / "precious.txt").write_text("keep me", encoding="utf-8")

        assert cli.main(["build-plugins", "--out", str(out)]) == 1

        err = capsys.readouterr().err
        assert "Refusing to write" in err
        assert (out / "precious.txt").is_file()


class TestLearningsAppend:
    def test_appends_to_the_workspace_file(
        self, workspace: Path, capsys: pytest.CaptureFixture[str]
    ):
        (workspace / "kitt.yml").write_text("version: 1\n", encoding="utf-8")

        code = cli.main(
            [
                "learnings", "append",
                "--workspace", str(workspace),
                "--entry", VALID_ENTRY,
            ]
        )

        assert code == 0
        learnings = (workspace / "LEARNINGS.md").read_text(encoding="utf-8")
        assert "LRN-2026-08-21-a" in learnings
        assert "Appended entry to" in capsys.readouterr().out

    def test_records_the_origin_slug(self, workspace: Path):
        (workspace / "kitt.yml").write_text("version: 1\n", encoding="utf-8")

        code = cli.main(
            [
                "learnings", "append",
                "--workspace", str(workspace),
                "--entry", VALID_ENTRY,
                "--origin", "crew-auditor",
            ]
        )

        assert code == 0
        text = (workspace / "LEARNINGS.md").read_text(encoding="utf-8")
        assert "origin: crew-auditor" in text

    def test_rejects_an_entry_without_a_valid_header(
        self, workspace: Path, capsys: pytest.CaptureFixture[str]
    ):
        """Same validation as the MCP tool: this IS the MCP tool."""
        (workspace / "kitt.yml").write_text("version: 1\n", encoding="utf-8")

        code = cli.main(
            [
                "learnings", "append",
                "--workspace", str(workspace),
                "--entry", "## Just a heading\n\nno LRN id\n",
            ]
        )

        assert code == 1
        assert "must start with" in capsys.readouterr().err
        assert not (workspace / "LEARNINGS.md").exists()

    def test_rejects_an_entry_that_leaks_identifying_content(
        self, workspace: Path, capsys: pytest.CaptureFixture[str]
    ):
        (workspace / "kitt.yml").write_text("version: 1\n", encoding="utf-8")

        code = cli.main(
            [
                "learnings", "append",
                "--workspace", str(workspace),
                "--entry",
                "## LRN-2026-08-21-b: Leaky\n\nMail someone@example.com about it.\n",
            ]
        )

        assert code == 1
        assert "rejected" in capsys.readouterr().err

    def test_reads_the_entry_from_a_file(self, workspace: Path, tmp_path: Path):
        (workspace / "kitt.yml").write_text("version: 1\n", encoding="utf-8")
        entry_file = tmp_path / "entry.md"
        entry_file.write_text(VALID_ENTRY, encoding="utf-8")

        code = cli.main(
            [
                "learnings", "append",
                "--workspace", str(workspace),
                "--entry-file", str(entry_file),
            ]
        )

        assert code == 0
        assert "LRN-2026-08-21-a" in (workspace / "LEARNINGS.md").read_text("utf-8")

    def test_reads_the_entry_from_stdin(
        self, workspace: Path, monkeypatch: pytest.MonkeyPatch
    ):
        """A heredoc is how a shell caller passes multi-line markdown."""
        (workspace / "kitt.yml").write_text("version: 1\n", encoding="utf-8")
        monkeypatch.setattr("sys.stdin", io.StringIO(VALID_ENTRY))

        code = cli.main(
            [
                "learnings", "append",
                "--workspace", str(workspace),
                "--entry-file", "-",
            ]
        )

        assert code == 0
        assert "LRN-2026-08-21-a" in (workspace / "LEARNINGS.md").read_text("utf-8")

    def test_an_entry_source_is_required(self, workspace: Path):
        with pytest.raises(SystemExit) as excinfo:
            cli.main(["learnings", "append", "--workspace", str(workspace)])
        assert excinfo.value.code == 2

    def test_entry_and_entry_file_are_mutually_exclusive(self, workspace: Path):
        with pytest.raises(SystemExit) as excinfo:
            cli.main(
                [
                    "learnings", "append",
                    "--workspace", str(workspace),
                    "--entry", VALID_ENTRY,
                    "--entry-file", "-",
                ]
            )
        assert excinfo.value.code == 2


class TestLearningsSearch:
    def test_searches_the_workspace_corpus(
        self, workspace: Path, capsys: pytest.CaptureFixture[str]
    ):
        (workspace / "kitt.yml").write_text("version: 1\n", encoding="utf-8")
        (workspace / "LEARNINGS.md").write_text(VALID_ENTRY, encoding="utf-8")

        code = cli.main(
            [
                "learnings", "search",
                "--workspace", str(workspace),
                "--req-id", "REQ-1",
                "--limit", "5",
            ]
        )

        assert code == 0
        assert capsys.readouterr().out.strip()

    def test_parses_comma_separated_stack_tags(
        self, workspace: Path, monkeypatch: pytest.MonkeyPatch
    ):
        seen: dict[str, object] = {}

        async def _fake_search(**kwargs: object) -> str:
            seen.update(kwargs)
            return "ok"

        monkeypatch.setattr("kitt.learnings_cli.learnings_search", _fake_search)

        assert (
            cli.main(
                [
                    "learnings", "search",
                    "--workspace", str(workspace),
                    "--stack-tags", "angular, fastapi ,",
                ]
            )
            == 0
        )
        assert seen["stack_tags"] == ["angular", "fastapi"]

    def test_an_action_is_required(self, capsys: pytest.CaptureFixture[str]):
        assert cli.main(["learnings"]) == 2
        assert "append or search" in capsys.readouterr().err
