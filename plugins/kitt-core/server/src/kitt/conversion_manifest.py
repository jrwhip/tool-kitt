"""
Conversion manifest for KITT.

Classifies commands and agents into tiers for multi-CLI conversion:
- Tier 1: No Claude references, convert as-is
- Tier 2: Path/file references only, convert with path replacement
- Tier 3: Claude-specific features, skip for other CLIs

Tier 3 is a ``{name: reason}`` dict rather than a bare list so every
exclusion carries its justification in data (a parity test enforces
non-empty reasons). Some tier-3 commands are additionally convertible
for a *specific* CLI (see :data:`CLI_EXTRA_CONVERTIBLE_COMMANDS`);
``is_convertible`` in :mod:`converters` consults that table when a
``cli`` argument is given.
"""

from __future__ import annotations

from typing import Literal, TypeAlias

ResourceType: TypeAlias = Literal["command", "agent"]

# Commands by tier (all use kitt- prefix)
COMMAND_TIERS: dict[str, list[str] | dict[str, str]] = {
    "tier1": [
        # Mental models. The 12 per-framework commands collapsed into one
        # argument-routed command in P2; the frameworks themselves are in
        # its `<frameworks>` block, not in 12 files.
        "kitt-consider",
        # Other generic commands
        "kitt-audit-skill",
        "kitt-audit-slash-command",
        "kitt-audit-subagent",
        "kitt-create-plan",
        "kitt-create-slash-command",
        "kitt-debug",
        "kitt-heal-skill",
        "kitt-run-plan",
        # Now convertible via MCP tools
        "kitt-add-to-todos",
        # Alignment/intervention
        "kitt-realign",
    ],
    "tier2": [
        # Path references only - need replacement
        "kitt-check-todos",
    ],
    "tier3": {
        # Skill-tool wrappers: the body is a one-line ``Skill(...)``
        # invocation, meaningless on CLIs without Claude's Skill tool.
        # Copilot gets these back via CLI_EXTRA_CONVERTIBLE_COMMANDS +
        # SKILL_WRAPPER_COMMANDS (the invocation is rewritten to the
        # native /skill-name form).
        "kitt-create-agent-skill": (
            "wraps Claude's Skill tool (Skill(kitt-create-agent-skills)); "
            "rewritten to native /skill-name form for Copilot only"
        ),
        "kitt-create-hook": (
            "wraps Claude's Skill tool (Skill(kitt-create-hooks)); "
            "rewritten to native /skill-name form for Copilot only"
        ),
        "kitt-create-meta-prompt": (
            "wraps Claude's Skill tool (Skill(kitt-create-meta-prompts)); "
            "rewritten to native /skill-name form for Copilot only"
        ),
        "kitt-create-subagent": (
            "wraps Claude's Skill tool (Skill(kitt-create-subagents)); "
            "rewritten to native /skill-name form for Copilot only"
        ),
        "kitt-capture": (
            "wraps Claude's Skill tool (Skill(kitt-capture-skill)); "
            "rewritten to native /skill-name form for Copilot only"
        ),
        # Claude-CLI-specific hook configurators: their whole purpose is
        # to write hooks into `.claude/settings.json` for Claude Code.
        # Converting them would either apply path replacements that
        # corrupt the literal `.claude/settings.json` instructions or
        # ship instructions for a hook mechanism the target CLI does not
        # have. Expressed here explicitly rather than by omission.
        "kitt-configure-capture-skill-hook": (
            "Claude Code-specific: registers a Stop hook in "
            ".claude/settings.json; path replacement would corrupt the "
            "literal .claude/ paths it must keep"
        ),
        "kitt-configure-git-guard": (
            "Claude Code-specific: registers a PreToolUse hook in "
            ".claude/settings.json; path replacement would corrupt the "
            "literal .claude/ paths it must keep"
        ),
        "kitt-configure-prompt-log": (
            "Claude Code-specific: registers a Stop hook in "
            ".claude/settings.json; path replacement would corrupt the "
            "literal .claude/ paths it must keep"
        ),
        "kitt-configure-skill-usage-hook": (
            "Claude Code-specific: registers a Stop hook in "
            ".claude/settings.json, and the hook it registers parses "
            "Claude Code's own transcript shape; neither the wiring nor "
            "the parser transfers to another CLI"
        ),
        "kitt-configure-token-usage-hook": (
            "Claude Code-specific: registers a Stop hook in "
            ".claude/settings.json, and the hook it registers joins "
            "Claude Code's per-turn usage objects to its tool_use/"
            "tool_result transcript blocks; neither the wiring nor the "
            "parser transfers to another CLI"
        ),
    },
}

# Agents by tier (all use kitt- prefix)
AGENT_TIERS: dict[str, list[str] | dict[str, str]] = {
    "tier1": [
        # Generic agents
        "kitt-architect",
        "kitt-code-auditor",
        "kitt-code-reviewer",
        "kitt-mentor",
        "kitt-refactor",
        # Auditors - work via file reading, convertible
        "kitt-skill-auditor",
        "kitt-slash-command-auditor",
        "kitt-subagent-auditor",
        # Crew pack: convertible across all CLIs. The four role
        # agents are terminal workers (no subagent dispatch from
        # within); the orchestrator and evaluator dispatch other
        # agents. All use only Read / Write / Glob / Grep / Bash plus
        # MCP tools, which map cleanly to Copilot. The orchestrator's
        # `Task` tool maps to Copilot's canonical `agent` tool (alias
        # of `custom-agent`) per `to_copilot_agent`'s tool_map, giving
        # Copilot subagent parity with Claude / Gemini's Task-based
        # dispatch.
                "kitt-crew-scout",
        "kitt-crew-coder",
        "kitt-crew-tester",
        "kitt-crew-auditor",
        "kitt-crew-evaluator",
    ],
    "tier2": [
        # Path references only (skill reference files under
        # `skills/...` or `.ai-cli/shared/skills/...`)
        "kitt-angular-perfectionist-reviewer",
        "kitt-angular-architect",
        "kitt-java-architect",
        "kitt-python-architect",
        "kitt-ios-architect",
        "kitt-accessibility-architect",
        "kitt-accessibility-perfectionist-reviewer",
        "kitt-java-perfectionist-reviewer",
        "kitt-python-perfectionist-reviewer",
        "kitt-security-architect",
        "kitt-security-perfectionist-reviewer",
        "kitt-vanilla-web-architect",
        "kitt-vanilla-web-perfectionist-reviewer",
    ],
    "tier3": {
        # None currently - all agents are convertible
    },
}

# Skill-tool wrapper commands: command name -> the skill it wraps plus a
# Copilot-appropriate description. On Claude these bodies call the Skill
# tool; on Copilot the skill is installed natively under
# ~/.copilot/skills/, so ``to_copilot_skill`` rewrites the body to
# invoke ``/<skill-name>`` directly. The descriptions are overridden
# here (not carried from the command frontmatter) because the originals
# name Claude Code / Claude-to-Claude pipelines, which must not leak
# into generated Copilot skills. Data-driven so adding a wrapper is one
# entry here plus its tier-3 reason above.
SKILL_WRAPPER_COMMANDS: dict[str, dict[str, str]] = {
    "kitt-create-agent-skill": {
        "skill": "kitt-create-agent-skills",
        "description": (
            "Create or edit Agent Skills with expert guidance on structure "
            "and best practices"
        ),
    },
    "kitt-create-hook": {
        "skill": "kitt-create-hooks",
        "description": (
            "Invoke the create-hooks skill for expert guidance on hook "
            "development"
        ),
    },
    "kitt-create-meta-prompt": {
        "skill": "kitt-create-meta-prompts",
        "description": (
            "Create optimized prompts for agent-to-agent pipelines "
            "(research -> plan -> implement)"
        ),
    },
    "kitt-create-subagent": {
        "skill": "kitt-create-subagents",
        "description": "Create specialized subagents with expert guidance",
    },
    "kitt-capture": {
        "skill": "kitt-capture-skill",
        "description": (
            "Capture hard-won knowledge from this session as a reusable "
            "skill (project-scoped or user-level)"
        ),
    },
}

# Tier-3 commands that ARE convertible for a specific CLI, with the
# conversion handled by that CLI's converter (Copilot: skill-wrapper
# rewrite in ``to_copilot_skill``). ``is_convertible(name, "command",
# cli="copilot")`` consults this; the default (no ``cli``) preserves
# the original Gemini behavior of skipping all tier 3.
CLI_EXTRA_CONVERTIBLE_COMMANDS: dict[str, frozenset[str]] = {
    "copilot": frozenset(SKILL_WRAPPER_COMMANDS),
}

# Commands installed as generated Copilot skills that should NOT be
# auto-selected by the model (``disable-model-invocation: true``).
# The rule: a command-skill is explicit-invocation-only when its value
# comes from the operator deliberately choosing it, not from topical
# relevance --
#   - kitt-consider is a lens the operator applies on demand; auto-
#     selection would inject a decision framework the operator did not
#     ask for into unrelated conversations;
#   - kitt-realign is a frustration-reset the *operator* triggers; a
#     model deciding to "realign" itself defeats the point;
#   - the skill wrappers are aliases for skills that already carry
#     their own auto-selection descriptions; letting both auto-select
#     would double-register the same trigger surface.
#
# Listed by name rather than derived from a prefix: the 12
# kitt-consider-* commands collapsed into one, so a prefix rule would
# now match nothing and silently stop marking anything.
EXPLICIT_INVOCATION_ONLY_COMMANDS: frozenset[str] = frozenset(
    {"kitt-consider", "kitt-realign"}
) | frozenset(SKILL_WRAPPER_COMMANDS)

# Path replacements per CLI
PATH_REPLACEMENTS: dict[str, list[tuple[str, str]]] = {
    "gemini": [
        ("~/.claude/skills/", "~/.gemini/skills/"),
        ("~/.claude/commands/", "~/.gemini/commands/"),
        ("~/.claude/agents/", "~/.gemini/agents/"),
        ("~/.claude/", "~/.gemini/"),
        (".claude/skills/", ".gemini/skills/"),
        (".claude/commands/", ".gemini/commands/"),
        (".claude/agents/", ".gemini/agents/"),
        (".claude/", ".gemini/"),
        ("CLAUDE.md", "GEMINI.md"),
    ],
    # NOTE on ordering: replacements run sequentially, so the `~/...`
    # pairs must come before the bare `.claude/...` pairs (the former
    # contain the latter as substrings), and the generic `.claude/`
    # catch-all must come last among the `.claude` pairs.
    "copilot": [
        ("~/.claude/skills/", "~/.copilot/skills/"),
        # User-level commands install on Copilot as generated skills,
        # so command-path references point at the skills dir.
        ("~/.claude/commands/", "~/.copilot/skills/"),
        ("~/.claude/agents/", "~/.copilot/agents/"),
        ("~/.claude/", "~/.copilot/"),
        # Project-level `.claude/commands/` must survive unchanged:
        # whether Copilot reads project `.claude/commands/` is
        # unconfirmed either way, so the safest translation is none.
        # A bare identity pair would NOT protect it -- the later
        # generic `.claude/` rule would still rewrite it -- so it is
        # hidden behind a NUL sentinel and restored after the generic
        # rule has run. NUL cannot occur in catalog markdown, so the
        # sentinel is collision-free.
        (".claude/commands/", "\x00KITT-KEEP-CLAUDE-COMMANDS\x00"),
        (".claude/skills/", ".github/skills/"),
        (".claude/agents/", ".github/agents/"),
        (".claude/", ".github/"),
        ("\x00KITT-KEEP-CLAUDE-COMMANDS\x00", ".claude/commands/"),
        ("CLAUDE.md", ".github/copilot-instructions.md"),
    ],
}


def get_tier(name: str, resource_type: ResourceType) -> int:
    """Get tier for a resource (1, 2, or 3)."""
    tiers = COMMAND_TIERS if resource_type == "command" else AGENT_TIERS

    for tier_num, tier_name in [(1, "tier1"), (2, "tier2"), (3, "tier3")]:
        # tier1/tier2 are lists; tier3 is a {name: reason} dict.
        # ``in`` works uniformly (dict membership checks keys).
        if name in tiers[tier_name]:
            return tier_num

    # Default to tier 3 (skip) if not found
    return 3


def get_tier3_reason(name: str, resource_type: ResourceType) -> str | None:
    """Return the recorded reason a resource is tier 3, or None."""
    tiers = COMMAND_TIERS if resource_type == "command" else AGENT_TIERS
    tier3 = tiers["tier3"]
    if not isinstance(tier3, dict):
        # The tier tables above declare tier3 as {name: reason}; a bare
        # assert would vanish under ``python -O`` and let a malformed
        # table produce a silent None instead of naming the bug.
        raise TypeError(
            f"tier3 for {resource_type} must be a dict of name -> reason, "
            f"got {type(tier3).__name__}"
        )
    return tier3.get(name)


def get_convertible_commands() -> list[str]:
    """Get list of commands convertible for other CLIs (tier 1 + tier 2)."""
    return list(COMMAND_TIERS["tier1"]) + list(COMMAND_TIERS["tier2"])


def get_convertible_agents() -> list[str]:
    """Get list of agents convertible for other CLIs (tier 1 + tier 2)."""
    return list(AGENT_TIERS["tier1"]) + list(AGENT_TIERS["tier2"])


def apply_path_replacements(content: str, cli: str) -> str:
    """Apply path replacements for a target CLI."""
    if cli not in PATH_REPLACEMENTS:
        return content

    for old, new in PATH_REPLACEMENTS[cli]:
        content = content.replace(old, new)

    return content
