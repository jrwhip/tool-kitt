"""Tests for conversion manifest tier classification."""

from pathlib import Path

from kitt.conversion_manifest import (
    COMMAND_TIERS,
    EXPLICIT_INVOCATION_ONLY_COMMANDS,
    SKILL_WRAPPER_COMMANDS,
    apply_path_replacements,
    get_convertible_agents,
    get_convertible_commands,
    get_tier,
    get_tier3_reason,
)
from kitt.converters import is_convertible

CATALOG_DIR = Path(__file__).resolve().parents[1] / "catalog"


def _catalog_command_names() -> set[str]:
    return {p.stem for p in CATALOG_DIR.glob("*/commands/kitt-*.md")}


class TestGetTier:
    def test_tier1_command(self):
        assert get_tier("kitt-debug", "command") == 1

    def test_tier2_command(self):
        assert get_tier("kitt-check-todos", "command") == 2

    def test_tier3_command(self):
        assert get_tier("kitt-create-hook", "command") == 3

    def test_unknown_defaults_to_tier3(self):
        assert get_tier("nonexistent-command", "command") == 3

    def test_tier1_agent(self):
        assert get_tier("kitt-architect", "agent") == 1

    def test_tier2_agent(self):
        assert get_tier("kitt-angular-perfectionist-reviewer", "agent") == 2


class TestGetConvertible:
    def test_commands_include_tier1_and_tier2(self):
        commands = get_convertible_commands()
        assert "kitt-debug" in commands
        assert "kitt-check-todos" in commands

    def test_commands_exclude_tier3(self):
        commands = get_convertible_commands()
        assert "kitt-create-hook" not in commands

    def test_catalog_has_no_command_skill_name_collisions(self):
        commands = {
            path.stem: path
            for path in CATALOG_DIR.glob("*/commands/kitt-*.md")
        }
        skills = {
            path.parent.name: path.parent
            for path in CATALOG_DIR.glob("*/skills/kitt-*/SKILL.md")
        }

        assert commands.keys().isdisjoint(skills.keys())


class TestManifestMatchesCatalog:
    """The tier tables are hand-maintained; the catalog is the truth.

    A command deleted from the catalog but left in a tier list makes
    ``get_convertible_commands`` advertise a file that is not there. A
    command added to the catalog but missing from every tier silently
    defaults to tier 3 and is skipped forever with no recorded reason.
    Both happened during the P2 command consolidation, which is why this
    is a test rather than a convention.
    """

    def test_every_catalog_command_is_classified(self):
        classified = (
            set(COMMAND_TIERS["tier1"])
            | set(COMMAND_TIERS["tier2"])
            | set(COMMAND_TIERS["tier3"])
        )
        assert _catalog_command_names() - classified == set()

    def test_every_classified_command_exists_in_the_catalog(self):
        classified = (
            set(COMMAND_TIERS["tier1"])
            | set(COMMAND_TIERS["tier2"])
            | set(COMMAND_TIERS["tier3"])
        )
        assert classified - _catalog_command_names() == set()

    def test_explicit_invocation_only_commands_exist(self):
        """The set was derived from a ``kitt-consider-`` prefix until the
        12 framework commands collapsed into one. A prefix rule now
        matches nothing, so the names are listed literally and pinned
        here against the catalog."""
        assert EXPLICIT_INVOCATION_ONLY_COMMANDS - _catalog_command_names() == set()
        assert "kitt-consider" in EXPLICIT_INVOCATION_ONLY_COMMANDS
        assert "kitt-realign" in EXPLICIT_INVOCATION_ONLY_COMMANDS

    def test_agents_include_tier1_and_tier2(self):
        agents = get_convertible_agents()
        assert "kitt-architect" in agents
        assert "kitt-angular-perfectionist-reviewer" in agents

    def test_crew_agents_are_tier1(self):
        """The five role agents must convert
        across all CLIs so Copilot operators get parity with Claude /
        Gemini for the four-role crew (DEMO-123). Listed in
        tier1 because their tool surface (Read / Write / Glob / Grep
        / Bash / Task) maps cleanly to Copilot via the existing
        ``to_copilot_agent`` tool_map (Task -> custom-agent).
        """
        for name in (
                        "kitt-crew-scout",
            "kitt-crew-coder",
            "kitt-crew-tester",
            "kitt-crew-auditor",
            "kitt-crew-evaluator",
        ):
            assert get_tier(name, "agent") == 1, (
                f"expected {name} in agent tier1; got {get_tier(name, 'agent')}"
            )
        agents = get_convertible_agents()
        for name in (
                        "kitt-crew-scout",
            "kitt-crew-coder",
            "kitt-crew-tester",
            "kitt-crew-auditor",
            "kitt-crew-evaluator",
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
        assert is_convertible("kitt-debug", "command") is True
        assert is_convertible("kitt-debug", "command", cli="copilot") is True
        assert is_convertible("kitt-debug", "command", cli="gemini") is True

    def test_unknown_names_not_convertible_anywhere(self):
        assert is_convertible("nonexistent", "command", cli="copilot") is False

    def test_tier3_reasons_available(self):
        reason = get_tier3_reason("kitt-configure-git-guard", "command")
        assert reason and ".claude/settings.json" in reason
        assert get_tier3_reason("kitt-debug", "command") is None


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
            apply_path_replacements("~/.claude/commands/kitt-x.md", "copilot")
            == "~/.copilot/skills/kitt-x.md"
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
