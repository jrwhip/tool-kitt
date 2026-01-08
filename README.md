# Tool-KITT

*Your AI coding assistant's Swiss Army knife.*

Commands, agents, skills, and MCP tools for Claude Code, Gemini CLI, and GitHub Copilot CLI.

All resources use the `kitt-` prefix (like the AI car from Knight Rider).

## Twisted Perspective

AI will probably take your job. That's not doom-saying—it's trajectory. But it's a tide you can't fight against. AI isn't going anywhere, and pretending otherwise is career suicide.

For now, your move is simple: learn to use it. Become as skilled with AI as you are with any other tool, language, or framework you've mastered. Treat it like you treated Git, Docker, or Kubernetes—something you resisted at first, then couldn't live without.

Here's the thing though: opening Copilot in your IDE and typing "make this work" isn't going to cut it. AI needs guidance. It needs context. It needs detailed, precise prompts. It can't think through everything you need—it requires direction. But manually typing detailed prompts every time isn't going to save time or make you the 10x developer you need to become to stay employed in tech as long as possible.

That's where this library comes in. Skills, commands, prompts, and agents—wrapped up nicely in an MCP to work with CLI tools like Claude Code, Gemini CLI, and Copilot CLI. You can build systems, templates, and workflows that give AI the context it needs without repeating yourself.

And here's the silver lining for any card-carrying nerd: working with a CLI AI interface is a lot like talking to WOPR from *WarGames*. You're sitting at a terminal, feeding commands to an intelligence that can outthink you in certain domains, collaborating on problems that matter. That's objectively cool.

And if you're going to become obsolete? Having WOPR do it is about as *bushido* as it gets for a developer. Go out on your shield, talking to the machine.

## What's Inside

**[Commands](#commands)** (28 total) - Slash commands that expand into structured workflows
- **Meta-Prompting**: Separate planning from execution with staged prompts
- **Todo Management**: Capture context mid-work, resume later with full state
- **Thinking Models**: Mental frameworks (first principles, inversion, 80/20, etc.)
- **Deep Analysis**: Systematic debugging methodology with evidence and hypothesis testing

**[Skills](#skills)** (7 total) - Autonomous workflows that research, generate, and self-heal
- **Create Plans**: Hierarchical project planning for solo developer + Claude workflows
- **Create Agent Skills**: Build new skills by describing what you want
- **Create Meta-Prompts**: Generate staged workflow prompts with dependency detection
- **Create Slash Commands**: Build custom commands with proper structure
- **Create Subagents**: Build specialized Claude instances for isolated contexts
- **Create Hooks**: Build event-driven automation
- **Debug Like Expert**: Systematic debugging with evidence gathering and hypothesis testing

**[Agents](#agents)** (9 total) - Specialized subagents for validation and quality
- **kitt-skill-auditor**: Reviews skills for best practices compliance
- **kitt-slash-command-auditor**: Reviews commands for proper structure
- **kitt-subagent-auditor**: Reviews agent configurations for effectiveness

## Installation

```bash
# Install the package
pip install tool-kitt
# or: uv pip install tool-kitt

# Initialize for all CLIs
tool-kitt --init
```

This installs resources for all supported CLIs:
- **Claude Code**: Commands, agents, and skills symlinked to `~/.claude/`
- **Gemini CLI**: Commands converted to TOML in `~/.gemini/commands/`
- **Copilot CLI**: Agents converted to `.agent.md` in `~/.copilot/agents/`

All CLIs also get MCP server access for shared resources.

### CLI-Specific Usage

**Claude Code:**
```
/kitt-consider-pareto        # Slash commands
@kitt-code-reviewer          # Agents
kitt-create-plans            # Skills
```

**Gemini CLI:**
```
/kitt-consider-pareto        # Slash commands (TOML format)
```

**Copilot CLI:**
```
/agent kitt-code-reviewer    # Custom agents
```

## Commands

### Meta-Prompting

Separate analysis from execution. Describe what you want in natural language, Claude generates a rigorous prompt, then runs it in a fresh sub-agent context.

- [`/kitt-create-prompt`](./commands/kitt-create-prompt.md) - Generate optimized prompts with XML structure
- [`/kitt-run-prompt`](./commands/kitt-run-prompt.md) - Execute saved prompts in sub-agent contexts

### Todo Management

Capture ideas mid-conversation without derailing current work. Resume later with full context intact.

- [`/kitt-add-to-todos`](./commands/kitt-add-to-todos.md) - Capture tasks with full context
- [`/kitt-check-todos`](./commands/kitt-check-todos.md) - Resume work on captured tasks

### Context Handoff

Create structured handoff documents to continue work in a fresh context. Reference with `@whats-next.md` to resume seamlessly.

- [`/kitt-whats-next`](./commands/kitt-whats-next.md) - Create handoff document for fresh context

### Create Extensions

Wrapper commands that invoke the skills below.

- [`/kitt-create-agent-skill`](./commands/kitt-create-agent-skill.md) - Create a new skill
- [`/kitt-create-meta-prompt`](./commands/kitt-create-meta-prompt.md) - Create staged workflow prompts
- [`/kitt-create-slash-command`](./commands/kitt-create-slash-command.md) - Create a new slash command
- [`/kitt-create-subagent`](./commands/kitt-create-subagent.md) - Create a new subagent
- [`/kitt-create-hook`](./commands/kitt-create-hook.md) - Create a new hook
- [`/kitt-create-plan`](./commands/kitt-create-plan.md) - Create hierarchical project plans

### Audit Extensions

Invoke auditor subagents.

- [`/kitt-audit-skill`](./commands/kitt-audit-skill.md) - Audit skill for best practices
- [`/kitt-audit-slash-command`](./commands/kitt-audit-slash-command.md) - Audit command for best practices
- [`/kitt-audit-subagent`](./commands/kitt-audit-subagent.md) - Audit subagent for best practices

### Self-Improvement

- [`/kitt-heal-skill`](./commands/kitt-heal-skill.md) - Fix skills based on execution issues

### Thinking Models

Apply mental frameworks to decisions and problems.

- [`/kitt-consider-pareto`](./commands/kitt-consider-pareto.md) - Apply 80/20 rule to focus on what matters
- [`/kitt-consider-first-principles`](./commands/kitt-consider-first-principles.md) - Break down to fundamentals and rebuild
- [`/kitt-consider-inversion`](./commands/kitt-consider-inversion.md) - Solve backwards (what guarantees failure?)
- [`/kitt-consider-second-order`](./commands/kitt-consider-second-order.md) - Think through consequences of consequences
- [`/kitt-consider-5-whys`](./commands/kitt-consider-5-whys.md) - Drill to root cause
- [`/kitt-consider-occams-razor`](./commands/kitt-consider-occams-razor.md) - Find simplest explanation
- [`/kitt-consider-one-thing`](./commands/kitt-consider-one-thing.md) - Identify highest-leverage action
- [`/kitt-consider-swot`](./commands/kitt-consider-swot.md) - Map strengths, weaknesses, opportunities, threats
- [`/kitt-consider-eisenhower-matrix`](./commands/kitt-consider-eisenhower-matrix.md) - Prioritize by urgent/important
- [`/kitt-consider-10-10-10`](./commands/kitt-consider-10-10-10.md) - Evaluate across time horizons
- [`/kitt-consider-opportunity-cost`](./commands/kitt-consider-opportunity-cost.md) - Analyze what you give up
- [`/kitt-consider-via-negativa`](./commands/kitt-consider-via-negativa.md) - Improve by removing

### Deep Analysis

Systematic debugging with methodical investigation.

- [`/kitt-debug`](./commands/kitt-debug.md) - Apply expert debugging methodology to investigate issues

### Plan Execution

- [`/kitt-run-plan`](./commands/kitt-run-plan.md) - Execute PLAN.md files with intelligent segmentation

## Agents

Specialized subagents for code review, architecture, and auditing.

- [`kitt-architect`](./agents/kitt-architect.md) - Software architecture advisor
- [`kitt-code-auditor`](./agents/kitt-code-auditor.md) - Code quality and security auditor
- [`kitt-code-reviewer`](./agents/kitt-code-reviewer.md) - Thorough code reviewer
- [`kitt-mentor`](./agents/kitt-mentor.md) - Patient teacher and guide
- [`kitt-refactor`](./agents/kitt-refactor.md) - Clean up and improve existing code
- [`kitt-angular-perfectionist-reviewer`](./agents/kitt-angular-perfectionist-reviewer.md) - Angular-specific reviewer
- [`kitt-skill-auditor`](./agents/kitt-skill-auditor.md) - Expert skill auditor for best practices compliance
- [`kitt-slash-command-auditor`](./agents/kitt-slash-command-auditor.md) - Expert slash command auditor
- [`kitt-subagent-auditor`](./agents/kitt-subagent-auditor.md) - Expert subagent configuration auditor

## Skills

### [kitt-create-plans](./skills/kitt-create-plans/)

Hierarchical project planning optimized for solo developer + Claude. Create executable plans that Claude runs, not enterprise documentation that sits unused.

**PLAN.md IS the prompt** - not documentation that gets transformed later. Brief → Roadmap → Research (if needed) → PLAN.md → Execute → SUMMARY.md.

**Domain-aware:** Optionally loads framework-specific expertise from `~/.claude/skills/expertise/` (e.g., macos-apps, iphone-apps) to make plans concrete instead of generic.

**Commands:** `/kitt-create-plan` (invoke skill), `/kitt-run-plan <path>` (execute PLAN.md with intelligent segmentation)

See [kitt-create-plans README](./skills/kitt-create-plans/README.md) for full documentation.

### [kitt-create-agent-skills](./skills/kitt-create-agent-skills/)

Build skills by describing what you want. Asks clarifying questions, researches APIs if needed, and generates properly structured skill files.

Commands: `/kitt-create-agent-skill`, `/kitt-heal-skill`, `/kitt-audit-skill`

### [kitt-create-meta-prompts](./skills/kitt-create-meta-prompts/)

Builds prompts with structured outputs (research.md, plan.md) that subsequent prompts can parse. Adds automatic dependency detection to chain research → plan → implement workflows.

Commands: `/kitt-create-meta-prompt`

### [kitt-create-slash-commands](./skills/kitt-create-slash-commands/)

Build commands that expand into full prompts when invoked.

Commands: `/kitt-create-slash-command`, `/kitt-audit-slash-command`

### [kitt-create-subagents](./skills/kitt-create-subagents/)

Build specialized Claude instances that run in isolated contexts.

Commands: `/kitt-create-subagent`, `/kitt-audit-subagent`

### [kitt-create-hooks](./skills/kitt-create-hooks/)

Build event-driven automation that triggers on tool calls, session events, or prompt submissions.

Commands: `/kitt-create-hook`

### [kitt-debug-like-expert](./skills/kitt-debug-like-expert/)

Deep analysis debugging mode for complex issues. Activates methodical investigation protocol with evidence gathering, hypothesis testing, and rigorous verification.

Commands: `/kitt-debug`

---

## CLI Compatibility

| Resource Type | Claude Code | Gemini CLI | Copilot CLI |
|---------------|-------------|------------|-------------|
| Commands | ✅ All 28 | ✅ 24 (TOML) | ❌ N/A |
| Agents | ✅ All 9 | ❌ N/A | ✅ 9 (.agent.md) |
| Skills | ✅ All 7 | ❌ N/A | ❌ N/A |
| MCP Tools | ✅ 36 | ✅ 36 | ✅ 36 |

### What's Available Per CLI

**Claude Code**: Full access to all commands, agents, and skills.

**Gemini CLI**: 24 commands converted to TOML format:
- All 12 thinking models (`/kitt-consider-*`)
- Meta-prompting: `kitt-create-prompt`, `kitt-run-prompt`, `kitt-create-plan`, `kitt-run-plan`
- Todo management: `kitt-check-todos`, `kitt-add-to-todos`
- Context: `kitt-whats-next`
- Auditing: `kitt-audit-skill`, `kitt-audit-slash-command`, `kitt-audit-subagent`
- Other: `kitt-debug`, `kitt-heal-skill`, `kitt-create-slash-command`

**Copilot CLI**: 9 agents converted to `.agent.md` format:
- `kitt-architect`, `kitt-code-auditor`, `kitt-code-reviewer`, `kitt-mentor`, `kitt-refactor`
- `kitt-angular-perfectionist-reviewer`
- `kitt-skill-auditor`, `kitt-slash-command-auditor`, `kitt-subagent-auditor`

### MCP Tools (All CLIs)

The MCP server provides 36 tools available to all CLIs:

**Dice/Random:**
- `roll_dice` - Roll dice using notation like "2d6+3"
- `flip_coin` - Flip one or more coins
- `random_choice` - Pick from comma-separated options
- `random_number` - Generate random number in range

**Weather:**
- `get_weather` - Current weather for a location (uses Open-Meteo, no API key)
- `get_forecast` - Multi-day forecast

**Notes:**
- `add_note` - Quick note with optional tags
- `list_notes` - List recent notes, filter by tag
- `search_notes` - Full-text search in notes
- `delete_note` - Remove a note

**Time Tracking:**
- `start_timer` - Start tracking time for a task
- `stop_timer` - Stop timer and log entry
- `log_time` - Manual time entry (e.g., "1h30m")
- `list_time_entries` - View recent time entries
- `time_summary` - Get time totals by project

Set `TOGGL_API_KEY` environment variable to automatically sync entries to Toggl.

**Todo Management:**
- `add_todo` - Add todo item to TO-DOS.md
- `list_todos` - List all todos
- `complete_todo` - Mark todo as complete

**Context/Handoff:**
- `create_handoff` - Create whats-next.md document
- `get_handoff` - Read current handoff

**Shared Resources:**
- `list_shared_commands`, `get_shared_command`
- `list_shared_skills`, `get_shared_skill`
- `list_shared_agents`, `get_shared_agent`
- `list_shared_context`, `get_shared_context`

**Project/Git/Dev:** `list_projects`, `get_project_context`, `git_status`, `git_diff`, `git_log`, `run_npm_script`, `check_build`

**Meta:**
- `create_mcp_tool` - Generate boilerplate for new MCP tools

### Skipped Content

Some commands require Claude-specific features (Skill tool, Task tool) with no equivalent:
- **Commands** (4): `kitt-create-hook`, `kitt-create-subagent`, `kitt-create-meta-prompt`, `kitt-create-agent-skill`
- **Skills** (all): Skills are Claude Code-specific

All CLIs get MCP server access for reading shared resources and managing todos/handoffs.

## Attribution

### Dependencies & Libraries

This project aggregates multiple data sources and wraps them into a unified package with an MCP (Model Context Protocol) server, providing compatibility with Claude, Gemini, and Copilot CLI. Some modifications have been made to ensure cross-platform functionality.

- [OpenCode](https://github.com/stephenschoettler/taches-oc-prompts) - Unlicenced
- [networkchuck/claude-engineer](https://github.com/networkchuck/claude-engineer) - MIT
- [networkchuck/agenticSeek](https://github.com/networkchuck/agenticSeek) - MIT
