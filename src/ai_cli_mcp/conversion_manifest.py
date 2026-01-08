"""
Conversion manifest for ai-cli-resources.

Classifies commands and agents into tiers for multi-CLI conversion:
- Tier 1: No Claude references, convert as-is
- Tier 2: Path/file references only, convert with path replacement
- Tier 3: Claude-specific features, skip for other CLIs
"""

# Commands by tier (all use kitt- prefix now)
COMMAND_TIERS = {
    'tier1': [
        # Mental models (12)
        'kitt-consider-10-10-10',
        'kitt-consider-5-whys',
        'kitt-consider-eisenhower-matrix',
        'kitt-consider-first-principles',
        'kitt-consider-inversion',
        'kitt-consider-occams-razor',
        'kitt-consider-one-thing',
        'kitt-consider-opportunity-cost',
        'kitt-consider-pareto',
        'kitt-consider-second-order',
        'kitt-consider-swot',
        'kitt-consider-via-negativa',
        # Other generic commands (9)
        'kitt-audit-skill',
        'kitt-audit-slash-command',
        'kitt-audit-subagent',
        'kitt-create-plan',
        'kitt-create-slash-command',
        'kitt-debug',
        'kitt-heal-skill',
        'kitt-run-plan',
        'kitt-run-prompt',
        # Now convertible via MCP tools (2)
        'kitt-add-to-todos',
        'kitt-whats-next',
    ],
    'tier2': [
        # Path references only - need replacement
        'kitt-check-todos',
        'kitt-create-prompt',
    ],
    'tier3': [
        # Claude-specific features - skip (require Skill/Task tool)
        'kitt-create-agent-skill',
        'kitt-create-hook',
        'kitt-create-meta-prompt',
        'kitt-create-subagent',
    ],
}

# Agents by tier (all use kitt- prefix now)
AGENT_TIERS = {
    'tier1': [
        # Generic agents
        'kitt-architect',
        'kitt-code-auditor',
        'kitt-code-reviewer',
        'kitt-mentor',
        'kitt-refactor',
        # Auditors - work via file reading, convertible
        'kitt-skill-auditor',
        'kitt-slash-command-auditor',
        'kitt-subagent-auditor',
    ],
    'tier2': [
        # Path references only
        'kitt-angular-perfectionist-reviewer',
    ],
    'tier3': [
        # None currently - all agents are convertible
    ],
}

# Path replacements per CLI
PATH_REPLACEMENTS = {
    'gemini': [
        ('~/.claude/skills/', '~/.gemini/skills/'),
        ('~/.claude/commands/', '~/.gemini/commands/'),
        ('~/.claude/agents/', '~/.gemini/agents/'),
        ('~/.claude/', '~/.gemini/'),
        ('.claude/skills/', '.gemini/skills/'),
        ('.claude/commands/', '.gemini/commands/'),
        ('.claude/agents/', '.gemini/agents/'),
        ('.claude/', '.gemini/'),
        ('CLAUDE.md', 'GEMINI.md'),
    ],
    'copilot': [
        ('~/.claude/skills/', '~/.copilot/'),
        ('~/.claude/commands/', '~/.copilot/'),
        ('~/.claude/agents/', '~/.copilot/agents/'),
        ('~/.claude/', '~/.copilot/'),
        ('.claude/skills/', '.github/'),
        ('.claude/commands/', '.github/'),
        ('.claude/agents/', '.github/agents/'),
        ('.claude/', '.github/'),
        ('CLAUDE.md', '.github/copilot-instructions.md'),
    ],
}


def get_tier(name: str, resource_type: str) -> int:
    """Get tier for a resource (1, 2, or 3)."""
    tiers = COMMAND_TIERS if resource_type == 'command' else AGENT_TIERS

    for tier_num, tier_name in [(1, 'tier1'), (2, 'tier2'), (3, 'tier3')]:
        if name in tiers[tier_name]:
            return tier_num

    # Default to tier 3 (skip) if not found
    return 3


def get_convertible_commands(cli: str) -> list:
    """Get list of commands convertible for a CLI (tier 1 + tier 2)."""
    return COMMAND_TIERS['tier1'] + COMMAND_TIERS['tier2']


def get_convertible_agents(cli: str) -> list:
    """Get list of agents convertible for a CLI (tier 1 + tier 2)."""
    return AGENT_TIERS['tier1'] + AGENT_TIERS['tier2']


def apply_path_replacements(content: str, cli: str) -> str:
    """Apply path replacements for a target CLI."""
    if cli not in PATH_REPLACEMENTS:
        return content

    for old, new in PATH_REPLACEMENTS[cli]:
        content = content.replace(old, new)

    return content
