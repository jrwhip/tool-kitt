"""
Help system for WOPR.

Shared logic used by both the CLI (`wopr help`) and the MCP tool (`get_help`).
"""

from __future__ import annotations

from pathlib import Path

from .catalog import (
    get_catalog_path,
    load_catalog,
    read_lock_file,
)

HELP_TOPICS = {
    "overview": "What WOPR is and how it works",
    "install": "Installation and initialization",
    "packs": "Pack and profile system",
    "commands": "Slash commands (thinking models, planning, debugging, etc.)",
    "skills": "Autonomous workflows (create plans, skills, prompts, etc.)",
    "agents": "Specialized sub-agents (reviewers, architects, auditors, etc.)",
    "mcp": "MCP tools available to all CLIs",
    "cli": "CLI usage for Claude Code, Gemini CLI, and Copilot CLI",
}


def get_help(topic: str | None = None, workspace: Path | None = None) -> str:
    """Return help text for a topic, or the topic index if no topic given."""
    if topic is None:
        return _topic_index(workspace)

    topic = topic.lower().strip()
    handler = {
        "overview": _help_overview,
        "install": _help_install,
        "packs": _help_packs,
        "commands": _help_commands,
        "skills": _help_skills,
        "agents": _help_agents,
        "mcp": _help_mcp,
        "cli": _help_cli,
    }.get(topic)

    if handler:
        return handler(workspace)

    lines = [f"Unknown topic: '{topic}'", "", "Available topics:"]
    lines.extend(f"  {name:12s} {desc}" for name, desc in HELP_TOPICS.items())
    return "\n".join(lines)


def _topic_index(workspace: Path | None = None) -> str:
    lines = [
        "WOPR - Webteam Orchestrated Prompt Runner",
        "Your AI coding assistant's Swiss Army knife.",
        "",
        "Commands, agents, skills, and MCP tools for Claude Code, Gemini CLI, and Copilot CLI.",
        "",
        "HELP TOPICS",
        "",
    ]
    for name, desc in HELP_TOPICS.items():
        lines.append(f"  {name:12s} {desc}")

    lines.append("")
    lines.append("Usage:")
    lines.append("  CLI:  wopr help <topic>")
    lines.append("  MCP:  get_help(topic='<topic>')")

    if workspace:
        installed = _get_installed_packs(workspace)
        if installed:
            lines.append("")
            lines.append(f"Installed packs: {', '.join(installed)}")

    return "\n".join(lines)


def _help_overview(workspace: Path | None = None) -> str:
    lines = [
        "OVERVIEW",
        "",
        "WOPR is a library of commands, agents, skills, and MCP tools designed to",
        "make AI coding assistants more effective. It works with Claude Code, Gemini",
        "CLI, and Copilot CLI.",
        "",
        "Resources are organized into packs that you install selectively. The _core",
        "pack is always installed and provides foundation tools (thinking models,",
        "debugging, planning, todo management). Additional packs add language-specific",
        "or domain-specific capabilities.",
        "",
        "RESOURCE TYPES",
        "",
        "  Commands    Slash commands that expand into structured workflows.",
        "              Invoked with /wopr-<name> in Claude Code or Gemini CLI.",
        "",
        "  Skills      Autonomous multi-step workflows. The agent researches, generates,",
        "              and self-corrects. Invoked by name or via /wopr-<name> wrapper commands.",
        "",
        "  Agents      Specialized sub-agents that run in isolated contexts with a specific",
        "              persona and focus (e.g., code reviewer, architect, Angular reviewer).",
        "",
        "  MCP Tools   Programmatic tools available to all CLIs via the MCP server.",
        "              Includes todo management, git operations, shared resource access,",
        "              and utility tools.",
        "",
        "HOW IT WORKS",
        "",
        "  1. Install:   pipx install wopr",
        "  2. Init:      wopr --init --packs angular,security",
        "  3. Use:       /wopr-consider-pareto, @wopr-code-reviewer, etc.",
        "  4. Manage:    wopr add <pack>, wopr remove <pack>, wopr list",
    ]
    return "\n".join(lines)


def _help_install(workspace: Path | None = None) -> str:
    lines = [
        "INSTALLATION",
        "",
        "Install with pipx (recommended):",
        "",
        "  pip install pipx",
        "  pipx ensurepath",
        "  pipx install git+https://github.com/[client-org]/webteam-ai-tools.git",
        "",
        "Or from a local clone:",
        "",
        "  pipx install /path/to/webteam-ai-tools",
        "  pipx install -e /path/to/webteam-ai-tools   # editable, for development",
        "",
        "INITIALIZATION",
        "",
        "  wopr --init                                  # core pack only",
        "  wopr --init --packs angular,security         # specific packs",
        "  wopr --init --profile angular-team           # predefined profile",
        "",
        "This installs resources for all supported CLIs:",
        "  - Claude Code:  commands, agents, and skills symlinked to ~/.claude/",
        "  - Gemini CLI:   commands converted to TOML in ~/.gemini/commands/,",
        "                  skills symlinked to ~/.gemini/skills/",
        "  - Copilot CLI:  skills symlinked to ~/.copilot/skills/, commands",
        "                  generated as slash-invocable skills, agents converted",
        "                  to .agent.md in ~/.copilot/agents/",
        "",
        "All CLIs also get MCP server access. An install manifest is written to",
        "~/.wopr/install-manifest.json recording what landed where.",
        "",
        "UPGRADING",
        "",
        "  pipx upgrade wopr",
        "  wopr --init                                  # re-sync resources",
        "",
        "UNINSTALLING",
        "",
        "  wopr --uninstall                             # dry run",
        "  wopr --uninstall --force                     # actually remove",
        "  wopr --uninstall --force --global            # also remove ~/.wopr/",
    ]
    return "\n".join(lines)


def _help_packs(workspace: Path | None = None) -> str:
    catalog = load_catalog(get_catalog_path())
    packs = catalog.get("packs", {})
    profiles = catalog.get("profiles", {})
    installed = _get_installed_packs(workspace) if workspace else []

    lines = [
        "PACKS AND PROFILES",
        "",
        "Resources are organized into packs. The _core pack is always installed.",
        "Everything else is opt-in.",
        "",
        "AVAILABLE PACKS",
        "",
    ]

    for name, info in sorted(packs.items()):
        desc = info.get("description", "")
        marker = ""
        if info.get("always_installed"):
            marker = " [always installed]"
        elif name in installed:
            marker = " [installed]"
        lines.append(f"  {name:18s} {desc}{marker}")

    if profiles:
        lines.append("")
        lines.append("PROFILES")
        lines.append("")
        for name, info in sorted(profiles.items()):
            desc = info.get("description", "")
            pack_list = ", ".join(info.get("packs", []))
            lines.append(f"  {name:18s} {desc}")
            lines.append(f"  {'':18s} packs: {pack_list}")

    lines.extend([
        "",
        "MANAGING PACKS",
        "",
        "  wopr --init --packs angular,security    Install with specific packs",
        "  wopr --init --profile angular-team       Install with a profile",
        "  wopr add angular security                Add packs after install",
        "  wopr remove angular                      Remove a pack",
        "  wopr list                                Show installed packs",
        "  wopr catalog                             Show all available packs",
    ])

    return "\n".join(lines)


def _help_commands(workspace: Path | None = None) -> str:
    shared_dir = _get_shared_dir(workspace)
    commands = _list_resources(shared_dir / "commands", "*.md") if shared_dir else []

    lines = [
        "COMMANDS",
        "",
        "Slash commands expand into structured workflows when invoked.",
        "",
        "USAGE",
        "",
        "  Claude Code:  /wopr-consider-pareto",
        "  Gemini CLI:   /wopr-consider-pareto",
        "  Copilot CLI:  /wopr-consider-pareto (commands install as native skills)",
        "",
        "CORE COMMANDS (_core pack, always installed)",
        "",
        "  Thinking Models     Mental frameworks for decisions and problems.",
        "                      /wopr-consider-pareto, /wopr-consider-first-principles,",
        "                      /wopr-consider-inversion, /wopr-consider-5-whys, etc.",
        "",
        "  Meta-Prompting      Separate analysis from execution.",
        "                      /wopr-create-prompt, /wopr-run-prompt",
        "",
        "  Todo Management     Capture tasks mid-work, resume later.",
        "                      /wopr-add-to-todos, /wopr-check-todos",
        "",
        "  Context Handoff     Continue work in a fresh context.",
        "                      wopr-whats-next skill",
        "",
        "  Debugging           Systematic debugging methodology.",
        "                      /wopr-debug",
        "",
        "  Alignment           Reset when the AI goes off track.",
        "                      /wopr-realign",
        "",
        "  Planning            Create and execute project plans.",
        "                      /wopr-create-plan, /wopr-run-plan",
        "",
        "PACK COMMANDS (installed with packs)",
        "",
        "  Authoring           Slash command wrappers for core skills. (meta-authoring pack)",
        "                      /wopr-create-agent-skill, /wopr-create-slash-command,",
        "                      /wopr-create-subagent, /wopr-create-hook, /wopr-create-meta-prompt",
        "",
        "  Auditing            Quality auditing for skills, commands, agents. (auditors pack)",
        "                      /wopr-audit-skill, /wopr-audit-slash-command,",
        "                      /wopr-audit-subagent, /wopr-heal-skill",
    ]

    if commands:
        lines.extend([
            "",
            f"INSTALLED ({len(commands)} commands)",
            "",
        ])
        for cmd in sorted(commands):
            lines.append(f"  /wopr-{cmd}" if not cmd.startswith("wopr-") else f"  /{cmd}")

    return "\n".join(lines)


def _help_skills(workspace: Path | None = None) -> str:
    shared_dir = _get_shared_dir(workspace)
    skills = _list_skill_dirs(shared_dir / "skills") if shared_dir else []

    lines = [
        "SKILLS",
        "",
        "Skills are autonomous workflows. The agent reads the skill instructions,",
        "asks clarifying questions, then executes multi-step work independently.",
        "",
        "USAGE",
        "",
        "  Claude Code:  invoke by name or use the wrapper /wopr-<name> command",
        "                (wrapper commands require the meta-authoring pack)",
        "  Gemini CLI:   symlinked to ~/.gemini/skills/",
        "  Copilot CLI:  symlinked to ~/.copilot/skills/; invoke as /wopr-<name>",
        "                or by name (run_skill MCP tool remains as a fallback)",
        "",
        "LOADING TIERS",
        "",
        "  A skill declares how it is surfaced with a `wopr-loading:` frontmatter key:",
        "",
        "    always    (default) installed natively; the CLI lists it every session",
        "    resolver  not listed natively; one line in the generated",
        "              wopr-skill-resolver skill, loaded on demand via run_skill",
        "    dormant   not listed anywhere; still loadable by exact name",
        "",
        "  Every catalog skill is `always` today. Use the other tiers when a pack of",
        "  specialists starts costing more context than it earns.",
        "",
        "CORE SKILLS",
        "",
        "  wopr-doctor                  Read-only scan; reports stack, missing setup, readiness",
        "  wopr-init-project            One-shot project scaffold (wopr.yml + specs + AGENTS.md)",
        "  wopr-create-yml              Just the wopr.yml part of init-project",
        "  wopr-create-agent-instructions  AGENTS.md plus per-CLI pointer files",
        "  wopr-create-plans            Create project plans for agentic execution",
        "  wopr-create-agent-skills     Build new skills by describing what you want",
        "  wopr-create-meta-prompts     Generate staged workflow prompts",
        "  wopr-create-slash-commands   Build custom slash commands",
        "  wopr-create-subagents        Build specialized agent instances",
        "  wopr-create-hooks            Build event-driven automation",
        "  wopr-debug-like-expert       Systematic debugging with evidence gathering",
        "",
        "CREW SKILLS (installed with the crew pack)",
        "",
        "  wopr-run-crew                Four-role crew orchestrator skill.",
        "                               On Copilot the wopr-crew agent is the",
        "                               recommended entry; see wopr help agents.",
        "",
        "PACK SKILLS (installed with packs)",
        "",
        "  wopr-build-angular-apps      Angular conventions and patterns (angular pack)",
        "  wopr-angular-developer       Official Angular skill, from Google (angular pack)",
        "  wopr-build-spring-boot-apps  Spring Boot conventions and patterns (java pack)",
        "",
        "  For .NET: install Microsoft's official plugins directly (Copilot CLI",
        "  and Claude Code): /plugin marketplace add dotnet/skills",
    ]

    if skills:
        lines.extend([
            "",
            f"INSTALLED ({len(skills)} skills)",
            "",
        ])
        for skill in sorted(skills):
            lines.append(f"  {skill}")

    return "\n".join(lines)


def _help_agents(workspace: Path | None = None) -> str:
    shared_dir = _get_shared_dir(workspace)
    agents = _list_resources(shared_dir / "agents", "*.md") if shared_dir else []

    lines = [
        "AGENTS",
        "",
        "Agents are specialized sub-agents that run in isolated contexts with a",
        "specific persona. They have access to all tools and focus on a single concern.",
        "",
        "USAGE",
        "",
        "  Claude Code:  select from the agent picker, or the AI spawns them as sub-agents",
        "  Copilot CLI:  /agent wopr-<name>",
        "  Gemini CLI:   use the invoke_agent MCP tool",
        "",
        "CORE AGENTS",
        "",
        "  wopr-architect                  Software architecture advisor",
        "  wopr-code-auditor               Code quality and security auditor",
        "  wopr-code-reviewer              Thorough code reviewer",
        "  wopr-mentor                     Patient teacher and guide",
        "  wopr-refactor                   Clean up and improve existing code",
        "",
        "CREW AGENTS (installed with the crew pack)",
        "",
        "  wopr-crew                    Four-role orchestrator. Dispatches scout/coder/",
        "                               tester/auditor and enforces gates. The Copilot",
        "                               counterpart to the wopr-run-crew skill;",
        "                               also usable on Claude Code / Gemini CLI.",
        "  wopr-crew-scout              Read-only discovery agent (terminal worker)",
        "  wopr-crew-coder              Implements a single REQ (terminal worker)",
        "  wopr-crew-tester             Writes tests + measures coverage (terminal worker)",
        "  wopr-crew-auditor            Final-gate audit + LEARNINGS distillation",
        "  wopr-crew-evaluator          Grades CRAG candidate entries (read-only)",
        "",
        "PACK AGENTS",
        "",
        "  wopr-angular-perfectionist-reviewer   Angular-specific reviewer (angular pack)",
        "  wopr-java-perfectionist-reviewer      Spring Boot reviewer (java pack)",
        "  wopr-python-perfectionist-reviewer    Python reviewer (python pack)",
        "  wopr-*-architect                      Stack architects (angular/ios/java/python)",
        "  wopr-skill-auditor                    Skill quality auditor (auditors pack)",
        "  wopr-slash-command-auditor            Command quality auditor (auditors pack)",
        "  wopr-subagent-auditor                 Agent config auditor (auditors pack)",
    ]

    if agents:
        lines.extend([
            "",
            f"INSTALLED ({len(agents)} agents)",
            "",
        ])
        for agent in sorted(agents):
            lines.append(f"  {agent}")

    return "\n".join(lines)


def _help_mcp(workspace: Path | None = None) -> str:
    lines = [
        "MCP TOOLS",
        "",
        "The MCP server provides tools available to all CLIs. These are always",
        "available regardless of which packs are installed.",
        "",
        "RESOURCE ACCESS",
        "",
        "  list_shared_commands, get_shared_command     Browse and read commands",
        "  list_shared_skills, get_shared_skill         Browse and read skills",
        "  list_shared_agents, get_shared_agent         Browse and read agents",
        "  list_shared_context, get_shared_context       Browse and read context docs",
        "  run_skill                                    Load skill for inline execution",
        "                                               (legacy fallback; Copilot and",
        "                                               Gemini have native skills)",
        "  invoke_agent                                 Load agent for inline execution",
        "                                               (Gemini's agent path; legacy",
        "                                               fallback elsewhere)",
        "",
        "SKILL TELEMETRY",
        "",
        "  skill_usage_report                           Observed usage per skill. Counts",
        "                                               are a LOWER BOUND: only run_skill",
        "                                               and the optional Claude Stop hook",
        "                                               are observed; Copilot and Gemini",
        "                                               native invocations are not counted",
        "  pin_skill                                    Never mark a rare skill stale",
        "",
        "TODO MANAGEMENT",
        "",
        "  add_todo, list_todos, complete_todo          Manage TO-DOS.md",
        "",
        "CONTEXT HANDOFF",
        "",
        "  create_handoff, get_handoff                  Manage whats-next.md",
        "",
        "PROJECT AND GIT",
        "",
        "  list_projects, get_project_context           Project discovery",
        "  git_status, git_diff, git_log                Git operations",
        "  run_npm_script, check_build                  Build and script runner",
        "",
        "WORKSPACE",
        "",
        "  get_workspace_info                           Debug configuration",
        "  get_help                                     This help system",
        "",
        "UTILITY (extras pack)",
        "",
        "  roll_dice, flip_coin, random_choice          Dice and random",
        "  random_number                                Random number in range",
        "  get_weather, get_forecast                    Weather (Open-Meteo, no API key)",
        "  add_note, list_notes, search_notes           Notes",
        "  delete_note                                  Remove a note",
        "  start_timer, stop_timer, log_time            Time tracking",
        "  list_time_entries, time_summary              Time reports",
    ]
    return "\n".join(lines)


def _help_cli(workspace: Path | None = None) -> str:
    lines = [
        "CLI USAGE",
        "",
        "TERMINAL",
        "",
        "  wopr --init                      Initialize (core pack only)",
        "  wopr --init --packs a,b          Initialize with specific packs",
        "  wopr --init --profile name       Initialize with a profile",
        "  wopr add <pack> [pack...]        Add packs to workspace",
        "  wopr remove <pack> [pack...]     Remove packs from workspace",
        "  wopr list                        Show installed packs",
        "  wopr catalog                     Show all available packs",
        "  wopr skill-usage report          Observed skill usage (a lower bound)",
        "  wopr skill-usage pin <name>      Never mark a rare skill stale",
        "  wopr help [topic]                Show help",
        "  wopr --uninstall [--force]       Remove wopr from all CLIs",
        "  wopr --version                   Show version",
        "",
        "CLAUDE CODE",
        "",
        "  /wopr-<command>                  Invoke a slash command",
        "  Select from agent picker         Use an agent as a sub-agent",
        "  Skills invoked by name           Or via /wopr-<skill> wrapper commands",
        "  MCP tools called automatically   The AI uses them as needed",
        "",
        "GEMINI CLI",
        "",
        "  /wopr-<command>                  Invoke a slash command (TOML format)",
        "  Skills in ~/.gemini/skills/      Symlinked from shared resources",
        "  MCP tools called automatically   The AI uses them as needed",
        "",
        "COPILOT CLI",
        "",
        "  /wopr-<command>                  Invoke a command (installed as a skill)",
        "  /wopr-<skill>                    Invoke a skill (~/.copilot/skills/)",
        "  /agent wopr-<name>               Use a custom agent",
        "  MCP tools called automatically   The AI uses them as needed",
        "  run_skill('<name>') via MCP      Legacy fallback for inline skill load",
    ]
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _get_installed_packs(workspace: Path | None) -> list[str]:
    if not workspace:
        return []
    lock = read_lock_file(workspace / ".ai-cli")
    if not lock:
        return []
    return lock.get("installed_packs", [])


def _get_shared_dir(workspace: Path | None) -> Path | None:
    if not workspace:
        return None
    shared = workspace / ".ai-cli" / "shared"
    return shared if shared.exists() else None


def _list_resources(directory: Path | None, pattern: str) -> list[str]:
    if not directory or not directory.exists():
        return []
    return [f.stem for f in directory.glob(pattern)]


def _list_skill_dirs(directory: Path | None) -> list[str]:
    if not directory or not directory.exists():
        return []
    return [
        d.name for d in directory.iterdir()
        if d.is_dir() and (d / "SKILL.md").exists()
    ]
