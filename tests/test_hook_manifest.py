"""Declarative hook manifests and per-CLI registration rendering.

WOPR used to carry one hand-written ``configure_*.py`` per hook per CLI.
Those scripts differed only in the event name, the config file path, and the
entry shape -- which is why porting the capture-skill hook to Copilot cost a
whole release. These tests pin the replacement: the wiring is declared once
in a ``<name>.HOOK.yaml`` and rendered per CLI, and re-registration is an
upsert by handler identity so it can never duplicate an entry.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from wopr.hook_manifest import (
    HookManifestError,
    HookTarget,
    bash_command,
    discover_hook_manifests,
    find_hook_manifest,
    hook_config_path,
    load_hook_config,
    parse_hook_manifest,
    powershell_command,
    register_hook,
    render_claude_entry,
    render_copilot_entry,
    upsert_claude_hook,
    upsert_copilot_hook,
)

REPO_ROOT = Path(__file__).resolve().parents[1]
CATALOG_HOOKS = REPO_ROOT / "catalog" / "_core" / "hooks"


@pytest.fixture
def hooks_dir(tmp_path: Path) -> Path:
    """A hooks dir with two handlers and one two-target manifest."""
    d = tmp_path / "hooks"
    d.mkdir()
    (d / "demo-hook.py").write_text("#!/usr/bin/env python3\n", encoding="utf-8")
    (d / "demo-hook-copilot.py").write_text("#!/usr/bin/env python3\n", encoding="utf-8")
    (d / "demo.HOOK.yaml").write_text(
        "name: demo\n"
        "description: A demo hook.\n"
        "handler: demo-hook.py\n"
        "targets:\n"
        "  claude:\n"
        "    event: Stop\n"
        '    matcher: ""\n'
        "  copilot:\n"
        "    event: agentStop\n"
        "    handler: demo-hook-copilot.py\n",
        encoding="utf-8",
    )
    return d


# ---------------------------------------------------------------------------
# Parsing and validation
# ---------------------------------------------------------------------------


class TestParsing:
    def test_parses_targets_and_per_cli_handler_override(self, hooks_dir: Path):
        spec = parse_hook_manifest(hooks_dir / "demo.HOOK.yaml")
        assert spec.name == "demo"
        assert set(spec.targets) == {"claude", "copilot"}
        assert spec.target("claude").event == "Stop"
        assert spec.target("claude").handler.name == "demo-hook.py"
        # The Copilot port is a different program, and the manifest says so.
        assert spec.target("copilot").event == "agentStop"
        assert spec.target("copilot").handler.name == "demo-hook-copilot.py"

    def test_default_handler_applies_to_targets_without_an_override(
        self, tmp_path: Path
    ):
        d = tmp_path / "hooks"
        d.mkdir()
        (d / "h.py").write_text("x", encoding="utf-8")
        (d / "h.HOOK.yaml").write_text(
            "name: h\ndescription: d\nhandler: h.py\n"
            "targets:\n  claude:\n    event: Stop\n",
            encoding="utf-8",
        )
        spec = parse_hook_manifest(d / "h.HOOK.yaml")
        assert spec.target("claude").handler.name == "h.py"

    def test_missing_handler_file_is_an_error(self, tmp_path: Path):
        d = tmp_path / "hooks"
        d.mkdir()
        (d / "h.HOOK.yaml").write_text(
            "name: h\ndescription: d\nhandler: nope.py\n"
            "targets:\n  claude:\n    event: Stop\n",
            encoding="utf-8",
        )
        with pytest.raises(HookManifestError, match="handler not found"):
            parse_hook_manifest(d / "h.HOOK.yaml")

    def test_handler_may_not_escape_the_manifest_directory(self, tmp_path: Path):
        d = tmp_path / "hooks"
        d.mkdir()
        (d / "h.HOOK.yaml").write_text(
            "name: h\ndescription: d\nhandler: ../../etc/passwd\n"
            "targets:\n  claude:\n    event: Stop\n",
            encoding="utf-8",
        )
        with pytest.raises(HookManifestError, match="bare filename"):
            parse_hook_manifest(d / "h.HOOK.yaml")

    def test_unsupported_cli_is_an_error(self, tmp_path: Path):
        d = tmp_path / "hooks"
        d.mkdir()
        (d / "h.py").write_text("x", encoding="utf-8")
        (d / "h.HOOK.yaml").write_text(
            "name: h\ndescription: d\nhandler: h.py\n"
            "targets:\n  emacs:\n    event: Stop\n",
            encoding="utf-8",
        )
        with pytest.raises(HookManifestError, match="unsupported CLI"):
            parse_hook_manifest(d / "h.HOOK.yaml")

    @pytest.mark.parametrize(
        "body",
        [
            "name: h\ndescription: d\nhandler: h.py\ntargets: {}\n",
            "description: d\nhandler: h.py\ntargets:\n  claude:\n    event: Stop\n",
            "name: h\nhandler: h.py\ntargets:\n  claude:\n    event: Stop\n",
            "name: h\ndescription: d\nhandler: h.py\n"
            "targets:\n  claude:\n    matcher: ''\n",
        ],
        ids=["no-targets", "no-name", "no-description", "no-event"],
    )
    def test_malformed_manifests_are_rejected(self, tmp_path: Path, body: str):
        d = tmp_path / "hooks"
        d.mkdir()
        (d / "h.py").write_text("x", encoding="utf-8")
        (d / "h.HOOK.yaml").write_text(body, encoding="utf-8")
        with pytest.raises(HookManifestError):
            parse_hook_manifest(d / "h.HOOK.yaml")

    def test_requesting_an_undeclared_target_names_what_exists(self, hooks_dir: Path):
        spec = find_hook_manifest(hooks_dir, "demo")
        object.__setattr__(spec, "targets", {"claude": spec.targets["claude"]})
        with pytest.raises(HookManifestError, match="declared: claude"):
            spec.target("copilot")

    def test_unknown_hook_name_lists_the_known_ones(self, hooks_dir: Path):
        with pytest.raises(HookManifestError, match="known: demo"):
            find_hook_manifest(hooks_dir, "nope")


# ---------------------------------------------------------------------------
# Rendering
# ---------------------------------------------------------------------------


class TestRendering:
    def test_claude_entry_is_the_nested_schema(self, tmp_path: Path):
        handler = tmp_path / "h.py"
        handler.write_text("x", encoding="utf-8")
        target = HookTarget("claude", "Stop", handler, matcher="")
        assert render_claude_entry(target) == {
            "matcher": "",
            "hooks": [{"type": "command", "command": f"python3 {handler}"}],
        }

    def test_claude_entry_omits_matcher_when_undeclared(self, tmp_path: Path):
        handler = tmp_path / "h.py"
        handler.write_text("x", encoding="utf-8")
        entry = render_claude_entry(HookTarget("claude", "Stop", handler))
        assert "matcher" not in entry

    def test_copilot_entry_is_the_flat_schema_with_both_shells(self, tmp_path: Path):
        handler = tmp_path / "h.py"
        handler.write_text("x", encoding="utf-8")
        entry = render_copilot_entry(HookTarget("copilot", "agentStop", handler))
        assert entry["type"] == "command"
        assert entry["bash"] == f"python3 {handler}"
        assert entry["powershell"] == f'python "{handler}"'

    def test_shell_scripts_are_invoked_with_bash_not_python(self, tmp_path: Path):
        handler = tmp_path / "guard.sh"
        handler.write_text("#!/bin/sh\n", encoding="utf-8")
        assert bash_command(handler) == f"bash {handler}"

    def test_shell_script_has_no_windows_invocation(self, tmp_path: Path):
        """Better to refuse than to register a command that fails on Windows."""
        handler = tmp_path / "guard.sh"
        handler.write_text("#!/bin/sh\n", encoding="utf-8")
        with pytest.raises(HookManifestError, match="no Windows invocation"):
            powershell_command(handler)

    def test_paths_with_spaces_are_quoted(self, tmp_path: Path):
        d = tmp_path / "has space"
        d.mkdir()
        handler = d / "h.py"
        handler.write_text("x", encoding="utf-8")
        assert "'" in bash_command(handler)
        assert powershell_command(handler).endswith('"')


# ---------------------------------------------------------------------------
# Upsert by identity -- the property re-init depends on
# ---------------------------------------------------------------------------


class TestUpsertClaude:
    def _target(self, tmp_path: Path, sub: str = "a") -> HookTarget:
        d = tmp_path / sub
        d.mkdir(exist_ok=True)
        handler = d / "demo-hook.py"
        handler.write_text("x", encoding="utf-8")
        return HookTarget("claude", "Stop", handler, matcher="")

    def test_first_registration_appends(self, tmp_path: Path):
        settings: dict = {}
        assert upsert_claude_hook(settings, self._target(tmp_path)) == "registered"
        assert len(settings["hooks"]["Stop"]) == 1

    def test_reregistration_is_unchanged_and_never_duplicates(self, tmp_path: Path):
        settings: dict = {}
        target = self._target(tmp_path)
        upsert_claude_hook(settings, target)
        for _ in range(3):
            assert upsert_claude_hook(settings, target) == "unchanged"
        assert len(settings["hooks"]["Stop"]) == 1

    def test_moved_handler_reconciles_in_place(self, tmp_path: Path):
        """The whole point of identity matching: no stale twin."""
        settings: dict = {}
        upsert_claude_hook(settings, self._target(tmp_path, "old"))
        moved = self._target(tmp_path, "new")
        assert upsert_claude_hook(settings, moved) == "updated"
        entries = settings["hooks"]["Stop"]
        assert len(entries) == 1
        assert str(moved.handler) in entries[0]["hooks"][0]["command"]

    def test_entry_missing_type_self_heals(self, tmp_path: Path):
        target = self._target(tmp_path)
        settings = {
            "hooks": {
                "Stop": [{"matcher": "", "hooks": [{"command": bash_command(target.handler)}]}]
            }
        }
        assert upsert_claude_hook(settings, target) == "updated"
        assert settings["hooks"]["Stop"][0]["hooks"][0]["type"] == "command"

    def test_other_hooks_and_settings_are_preserved(self, tmp_path: Path):
        settings = {
            "theme": "dark",
            "hooks": {
                "Stop": [{"hooks": [{"type": "command", "command": "echo mine"}]}],
                "PreToolUse": [{"hooks": [{"type": "command", "command": "echo pre"}]}],
            },
        }
        upsert_claude_hook(settings, self._target(tmp_path))
        assert settings["theme"] == "dark"
        assert settings["hooks"]["PreToolUse"][0]["hooks"][0]["command"] == "echo pre"
        assert len(settings["hooks"]["Stop"]) == 2

    def test_corrupt_hooks_shape_raises_rather_than_clobbering(self, tmp_path: Path):
        with pytest.raises(HookManifestError):
            upsert_claude_hook({"hooks": []}, self._target(tmp_path))


class TestUpsertCopilot:
    def _target(self, tmp_path: Path, sub: str = "a") -> HookTarget:
        d = tmp_path / sub
        d.mkdir(exist_ok=True)
        handler = d / "demo-hook-copilot.py"
        handler.write_text("x", encoding="utf-8")
        return HookTarget("copilot", "agentStop", handler)

    def test_first_registration_sets_version_and_appends(self, tmp_path: Path):
        config: dict = {}
        assert upsert_copilot_hook(config, self._target(tmp_path)) == "registered"
        assert config["version"] == 1
        assert len(config["hooks"]["agentStop"]) == 1

    def test_reregistration_never_duplicates(self, tmp_path: Path):
        config: dict = {}
        target = self._target(tmp_path)
        upsert_copilot_hook(config, target)
        for _ in range(3):
            assert upsert_copilot_hook(config, target) == "unchanged"
        assert len(config["hooks"]["agentStop"]) == 1

    def test_moved_handler_reconciles_in_place(self, tmp_path: Path):
        config: dict = {}
        upsert_copilot_hook(config, self._target(tmp_path, "old"))
        moved = self._target(tmp_path, "new")
        assert upsert_copilot_hook(config, moved) == "updated"
        assert len(config["hooks"]["agentStop"]) == 1
        assert str(moved.handler) in config["hooks"]["agentStop"][0]["bash"]

    def test_legacy_entry_missing_type_self_heals(self, tmp_path: Path):
        target = self._target(tmp_path)
        config = {
            "version": 1,
            "hooks": {"agentStop": [{"bash": bash_command(target.handler)}]},
        }
        assert upsert_copilot_hook(config, target) == "updated"
        entry = config["hooks"]["agentStop"][0]
        assert entry["type"] == "command"
        assert "powershell" in entry


# ---------------------------------------------------------------------------
# File-level registration
# ---------------------------------------------------------------------------


class TestRegisterHook:
    def test_writes_claude_settings_json(self, hooks_dir: Path, tmp_path: Path):
        project = tmp_path / "project"
        project.mkdir()
        spec = find_hook_manifest(hooks_dir, "demo")
        result, path = register_hook(spec, "claude", project)
        assert result == "registered"
        assert path == project / ".claude" / "settings.json"
        data = json.loads(path.read_text(encoding="utf-8"))
        assert data["hooks"]["Stop"][0]["hooks"][0]["type"] == "command"

    def test_writes_copilot_hooks_json(self, hooks_dir: Path, tmp_path: Path):
        project = tmp_path / "project"
        project.mkdir()
        spec = find_hook_manifest(hooks_dir, "demo")
        result, path = register_hook(spec, "copilot", project)
        assert result == "registered"
        assert path == project / ".github" / "hooks" / "hooks.json"
        data = json.loads(path.read_text(encoding="utf-8"))
        assert data["version"] == 1
        assert data["hooks"]["agentStop"][0]["type"] == "command"

    def test_one_manifest_drives_both_clis(self, hooks_dir: Path, tmp_path: Path):
        """The author-once property: no second manifest, no second script."""
        project = tmp_path / "project"
        project.mkdir()
        spec = find_hook_manifest(hooks_dir, "demo")
        register_hook(spec, "claude", project)
        register_hook(spec, "copilot", project)
        claude = json.loads(
            (project / ".claude" / "settings.json").read_text(encoding="utf-8")
        )
        copilot = json.loads(
            (project / ".github" / "hooks" / "hooks.json").read_text(encoding="utf-8")
        )
        assert "Stop" in claude["hooks"]
        assert "agentStop" in copilot["hooks"]
        assert "demo-hook-copilot.py" in copilot["hooks"]["agentStop"][0]["bash"]
        assert "demo-hook-copilot.py" not in (
            claude["hooks"]["Stop"][0]["hooks"][0]["command"]
        )

    def test_repeated_registration_is_idempotent_on_disk(
        self, hooks_dir: Path, tmp_path: Path
    ):
        project = tmp_path / "project"
        project.mkdir()
        spec = find_hook_manifest(hooks_dir, "demo")
        register_hook(spec, "claude", project)
        first = (project / ".claude" / "settings.json").read_text(encoding="utf-8")
        for _ in range(3):
            assert register_hook(spec, "claude", project)[0] == "unchanged"
        assert (
            project / ".claude" / "settings.json"
        ).read_text(encoding="utf-8") == first

    def test_dry_run_writes_nothing(self, hooks_dir: Path, tmp_path: Path):
        project = tmp_path / "project"
        project.mkdir()
        spec = find_hook_manifest(hooks_dir, "demo")
        result, path = register_hook(spec, "claude", project, dry_run=True)
        assert result == "registered"
        assert not path.exists()

    def test_invalid_json_is_refused_not_overwritten(
        self, hooks_dir: Path, tmp_path: Path
    ):
        project = tmp_path / "project"
        (project / ".claude").mkdir(parents=True)
        settings = project / ".claude" / "settings.json"
        settings.write_text("{not json", encoding="utf-8")
        spec = find_hook_manifest(hooks_dir, "demo")
        with pytest.raises(HookManifestError, match="invalid JSON"):
            register_hook(spec, "claude", project)
        assert settings.read_text(encoding="utf-8") == "{not json"

    def test_hook_config_path_rejects_unknown_cli(self, tmp_path: Path):
        with pytest.raises(HookManifestError):
            hook_config_path(tmp_path, "emacs")

    def test_missing_config_reads_as_empty(self, tmp_path: Path):
        assert load_hook_config(tmp_path / "absent.json") == {}


# ---------------------------------------------------------------------------
# The shipped catalog manifests
# ---------------------------------------------------------------------------


class TestCatalogHookManifests:
    def test_every_shipped_manifest_parses(self):
        specs = discover_hook_manifests(CATALOG_HOOKS)
        assert specs, "no HOOK.yaml manifests found in the _core pack"
        assert {s.name for s in specs} == {
            "capture-skill-trigger",
            "git-branch-guard",
            "prompt-log",
            "skill-usage",
        }

    def test_capture_skill_trigger_declares_a_stop_event(self):
        spec = find_hook_manifest(CATALOG_HOOKS, "capture-skill-trigger")
        assert spec.target("claude").event == "Stop"

    def test_claude_only_hooks_declare_no_copilot_target(self):
        """A guard that fails open is worse than no guard.

        Every shipped hook here is Claude-only: the Copilot port of
        capture-skill-trigger (a separate handler, a separate `agentStop`
        transcript format) was retired along with the rest of WOPR's
        Copilot surface, so its manifest no longer declares a `copilot`
        target either. `skill-usage` is here for the telemetry flavor of
        the same rule: its handler parses Claude Code's transcript shape,
        and a counter that silently returns zero on another CLI is worse
        than a documented gap, because the report still reads as
        authoritative.
        """
        for name in (
            "capture-skill-trigger",
            "git-branch-guard",
            "prompt-log",
            "skill-usage",
        ):
            spec = find_hook_manifest(CATALOG_HOOKS, name)
            assert set(spec.targets) == {"claude"}, name

    def test_every_declared_handler_renders_a_command(self):
        for spec in discover_hook_manifests(CATALOG_HOOKS):
            for cli, target in spec.targets.items():
                command = bash_command(target.handler)
                assert target.handler.name in command, (spec.name, cli)

    def test_shipped_manifests_register_idempotently(self, tmp_path: Path):
        project = tmp_path / "project"
        project.mkdir()
        for spec in discover_hook_manifests(CATALOG_HOOKS):
            for cli in spec.targets:
                assert register_hook(spec, cli, project)[0] == "registered"
                assert register_hook(spec, cli, project)[0] == "unchanged"

        # All three Stop hooks coexist; none displaced another.
        settings = json.loads(
            (project / ".claude" / "settings.json").read_text(encoding="utf-8")
        )
        stop_commands = [
            h["command"] for e in settings["hooks"]["Stop"] for h in e["hooks"]
        ]
        assert len(stop_commands) == 3
        assert any("capture-skill-trigger-hook.py" in c for c in stop_commands)
        assert any("prompt-log-hook.py" in c for c in stop_commands)
        assert any("skill-usage-hook.py" in c for c in stop_commands)
        assert "PreToolUse" in settings["hooks"]

    def test_configure_hook_script_replaced_the_per_cli_duplicates(self):
        scripts = REPO_ROOT / "catalog" / "_core" / "scripts"
        assert (scripts / "configure_hook.py").is_file()
        assert not (scripts / "configure_capture_skill_hook.py").exists()
        assert not (scripts / "configure_capture_skill_hook_copilot.py").exists()
        # The skill-usage hook arrived with a bespoke registration script
        # of its own, reintroducing exactly the duplication the manifest
        # system removed. It is declarative wiring now, like the rest.
        assert not (scripts / "configure_skill_usage_hook.py").exists()

    def test_slash_commands_invoke_the_generic_script(self):
        commands = REPO_ROOT / "catalog" / "_core" / "commands"
        for fname, cli, hook in [
            ("wopr-configure-capture-skill-hook.md", "claude", "capture-skill-trigger"),
            ("wopr-configure-skill-usage-hook.md", "claude", "skill-usage"),
        ]:
            text = (commands / fname).read_text(encoding="utf-8")
            assert "configure_hook.py" in text, fname
            assert f"--cli {cli}" in text, fname
            assert f"--hook {hook}" in text, fname
            assert "configure_capture_skill_hook" not in text, fname
            assert "configure_skill_usage_hook" not in text, fname
