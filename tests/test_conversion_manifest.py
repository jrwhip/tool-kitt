"""Tests for conversion manifest tier classification."""

from pathlib import Path

from wopr.conversion_manifest import (
    SKILL_WRAPPER_COMMANDS,
    apply_path_replacements,
    get_convertible_agents,
    get_convertible_commands,
    get_tier,
    get_tier3_reason,
)
from wopr.converters import is_convertible


class TestGetTier:
    def test_tier1_command(self):
        assert get_tier("wopr-debug", "command") == 1

    def test_tier2_command(self):
        assert get_tier("wopr-check-todos", "command") == 2

    def test_tier3_command(self):
        assert get_tier("wopr-create-hook", "command") == 3

    def test_unknown_defaults_to_tier3(self):
        assert get_tier("nonexistent-command", "command") == 3

    def test_tier1_agent(self):
        assert get_tier("wopr-architect", "agent") == 1

    def test_tier2_agent(self):
        assert get_tier("wopr-angular-perfectionist-reviewer", "agent") == 2


class TestGetConvertible:
    def test_commands_include_tier1_and_tier2(self):
        commands = get_convertible_commands()
        assert "wopr-debug" in commands
        assert "wopr-check-todos" in commands

    def test_commands_exclude_tier3(self):
        commands = get_convertible_commands()
        assert "wopr-create-hook" not in commands

    def test_catalog_has_no_command_skill_name_collisions(self):
        catalog_dir = Path(__file__).resolve().parents[1] / "catalog"
        commands = {
            path.stem: path
            for path in catalog_dir.glob("*/commands/wopr-*.md")
        }
        skills = {
            path.parent.name: path.parent
            for path in catalog_dir.glob("*/skills/wopr-*/SKILL.md")
        }

        assert commands.keys().isdisjoint(skills.keys())

    def test_agents_include_tier1_and_tier2(self):
        agents = get_convertible_agents()
        assert "wopr-architect" in agents
        assert "wopr-angular-perfectionist-reviewer" in agents

    def test_crew_agents_are_tier1(self):
        """The five role agents plus the orchestrator must convert
        across all CLIs so Copilot operators get parity with Claude /
        Gemini for the four-role crew ([TICKET-ID]). Listed in
        tier1 because their tool surface (Read / Write / Glob / Grep
        / Bash / Task) maps cleanly to Copilot via the existing
        ``to_copilot_agent`` tool_map (Task -> custom-agent).
        """
        for name in (
            "wopr-crew",
            "wopr-crew-scout",
            "wopr-crew-coder",
            "wopr-crew-tester",
            "wopr-crew-auditor",
            "wopr-crew-evaluator",
        ):
            assert get_tier(name, "agent") == 1, (
                f"expected {name} in agent tier1; got {get_tier(name, 'agent')}"
            )
        agents = get_convertible_agents()
        for name in (
            "wopr-crew",
            "wopr-crew-scout",
            "wopr-crew-coder",
            "wopr-crew-tester",
            "wopr-crew-auditor",
            "wopr-crew-evaluator",
        ):
            assert name in agents


class TestPerCliConvertibility:
    def test_default_preserves_gemini_behavior(self):
        """No ``cli`` argument = tier-only behavior: all tier 3 skipped."""
        for name in SKILL_WRAPPER_COMMANDS:
            assert is_convertible(name, "command") is False, name

    def test_wrappers_convertible_for_copilot_only(self):
        for name in SKILL_WRAPPER_COMMANDS:
            assert is_convertible(name, "command", cli="copilot") is True, name
            assert is_convertible(name, "command", cli="gemini") is False, name

    def test_tier1_convertible_for_every_cli(self):
        assert is_convertible("wopr-debug", "command") is True
        assert is_convertible("wopr-debug", "command", cli="copilot") is True
        assert is_convertible("wopr-debug", "command", cli="gemini") is True

    def test_unknown_names_not_convertible_anywhere(self):
        assert is_convertible("nonexistent", "command", cli="copilot") is False

    def test_tier3_reasons_available(self):
        reason = get_tier3_reason("wopr-configure-git-guard", "command")
        assert reason and ".claude/settings.json" in reason
        assert get_tier3_reason("wopr-debug", "command") is None


class TestPathReplacements:
    def test_gemini_paths(self):
        content = "Look in ~/.claude/commands/ for files"
        result = apply_path_replacements(content, "gemini")
        assert "~/.gemini/commands/" in result

    def test_copilot_paths(self):
        content = "CLAUDE.md has instructions"
        result = apply_path_replacements(content, "copilot")
        assert ".github/copilot-instructions.md" in result

    def test_unknown_cli_no_change(self):
        content = "~/.claude/commands/"
        assert apply_path_replacements(content, "vscode") == content

    def test_copilot_user_skills_and_commands_map_to_copilot_skills(self):
        assert (
            apply_path_replacements("~/.claude/skills/foo/", "copilot")
            == "~/.copilot/skills/foo/"
        )
        # User-level commands install on Copilot as generated skills.
        assert (
            apply_path_replacements("~/.claude/commands/wopr-x.md", "copilot")
            == "~/.copilot/skills/wopr-x.md"
        )

    def test_copilot_project_skills_map_to_github_skills(self):
        assert (
            apply_path_replacements("look in .claude/skills/ here", "copilot")
            == "look in .github/skills/ here"
        )

    def test_copilot_project_commands_survive_unchanged(self):
        """Project-level ``.claude/commands/`` reading by Copilot is
        unconfirmed either way; the literal path must survive. The NUL
        sentinel protects it from the sequential generic ``.claude/``
        rule, and no sentinel byte may leak into the output."""
        content = "Check .claude/commands/ and also .claude/settings.json"
        result = apply_path_replacements(content, "copilot")
        assert ".claude/commands/" in result
        assert "\x00" not in result
        # The generic rule still applies to other .claude/ paths.
        assert ".github/settings.json" in result

    def test_copilot_home_commands_not_confused_with_project_commands(self):
        # `~/.claude/commands/` contains `.claude/commands/` as a
        # substring; ordering must translate the home form first.
        result = apply_path_replacements(
            "~/.claude/commands/ vs .claude/commands/", "copilot"
        )
        assert result == "~/.copilot/skills/ vs .claude/commands/"
