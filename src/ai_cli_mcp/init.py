"""
Cross-platform initialization for ai-cli-resources.

Handles:
- Creating .ai-cli/ directory structure in workspace
- Copying default resources to workspace
- Registering MCP server with CLIs (Claude, Gemini, Copilot)
- Converting commands/agents to CLI-native formats
- Creating symlinks (Unix) or copying files (Windows) for Claude
"""

import json
import platform
import shutil
from pathlib import Path

from .converters import to_gemini_toml, to_copilot_agent, is_convertible


def get_package_root() -> Path:
    """Get the package root directory (where bundled defaults live)."""
    return Path(__file__).parent.parent.parent


def is_windows() -> bool:
    return platform.system() == "Windows"


def get_home() -> Path:
    return Path.home()


def create_workspace_structure(workspace: Path) -> None:
    """Create .ai-cli directory structure in workspace."""
    ai_cli = workspace / ".ai-cli"
    dirs = [
        ai_cli / "shared" / "commands",
        ai_cli / "shared" / "skills",
        ai_cli / "shared" / "agents",
        ai_cli / "shared" / "context",
    ]
    for d in dirs:
        d.mkdir(parents=True, exist_ok=True)
    print(f"Created {ai_cli}")


def copy_defaults(workspace: Path) -> None:
    """Copy default resources from package to workspace."""
    package_root = get_package_root()
    dest = workspace / ".ai-cli" / "shared"

    for category in ["commands", "skills", "agents", "context"]:
        src_dir = package_root / category
        dst_dir = dest / category

        if not src_dir.exists():
            continue

        # For skills, copy entire directories (each skill is a directory with SKILL.md)
        if category == "skills":
            for skill_dir in src_dir.iterdir():
                if skill_dir.is_dir():
                    dst_skill = dst_dir / skill_dir.name
                    if not dst_skill.exists():
                        shutil.copytree(skill_dir, dst_skill)
                        print(f"  Copied {category}/{skill_dir.name}/")
                    else:
                        print(f"  Skipped {category}/{skill_dir.name}/ (exists)")
        else:
            # For commands, agents, context - copy .md files
            for src_file in src_dir.glob("*.md"):
                dst_file = dst_dir / src_file.name
                if not dst_file.exists():
                    shutil.copy2(src_file, dst_file)
                    print(f"  Copied {category}/{src_file.name}")
                else:
                    print(f"  Skipped {category}/{src_file.name} (exists)")

            # Also handle subdirectories for commands (like consider/)
            if category == "commands":
                for subdir in src_dir.iterdir():
                    if subdir.is_dir():
                        dst_subdir = dst_dir / subdir.name
                        if not dst_subdir.exists():
                            shutil.copytree(subdir, dst_subdir)
                            print(f"  Copied {category}/{subdir.name}/")
                        else:
                            print(f"  Skipped {category}/{subdir.name}/ (exists)")


def get_mcp_config(workspace: Path, for_copilot: bool = False) -> dict:
    """Generate MCP server configuration.

    Args:
        workspace: Path to the workspace directory
        for_copilot: If True, include 'type' and 'tools' fields required by Copilot CLI
    """
    config = {
        "tool-kitt": {
            "command": "tool-kitt",
            "args": [],
            "env": {
                "TOOL_KITT_WORKSPACE": str(workspace)
            }
        }
    }

    if for_copilot:
        config["tool-kitt"]["type"] = "local"
        config["tool-kitt"]["tools"] = ["*"]

    return config


def update_json_file(path: Path, key: str, value: dict) -> bool:
    """Update a JSON config file, merging the new value."""
    try:
        if path.exists():
            with open(path) as f:
                data = json.load(f)
        else:
            data = {}

        if key not in data:
            data[key] = {}

        data[key].update(value)

        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w") as f:
            json.dump(data, f, indent=2)

        return True
    except Exception as e:
        print(f"  Warning: Could not update {path}: {e}")
        return False


def create_or_update_symlink(src: Path, dst: Path) -> None:
    """Create or update a symlink, removing existing if necessary."""
    if dst.is_symlink():
        dst.unlink()
    elif dst.exists():
        shutil.rmtree(dst)

    dst.parent.mkdir(parents=True, exist_ok=True)

    if is_windows():
        shutil.copytree(src, dst)
        print(f"  Copied {src.name} to {dst}")
    else:
        dst.symlink_to(src)
        print(f"  Symlinked: {dst} -> {src}")


def setup_claude(workspace: Path) -> None:
    """Configure Claude CLI."""
    print("\nClaude CLI:")

    shared_dir = workspace / ".ai-cli" / "shared"

    # Update ~/.claude.json with MCP server (global)
    claude_json = get_home() / ".claude.json"
    mcp_config = get_mcp_config(workspace)

    if claude_json.exists():
        try:
            with open(claude_json) as f:
                data = json.load(f)
        except Exception:
            data = {}
    else:
        data = {}

    if "mcpServers" not in data:
        data["mcpServers"] = {}

    data["mcpServers"].update(mcp_config)

    with open(claude_json, "w") as f:
        json.dump(data, f, indent=2)
    print(f"  Updated {claude_json}")

    # Clean up old ai/ subdirectory symlinks if they exist
    for old_path in [
        get_home() / ".claude" / "commands" / "ai",
        get_home() / ".claude" / "agents" / "ai",
        get_home() / ".claude" / "skills" / "ai",
    ]:
        if old_path.is_symlink() or old_path.exists():
            if old_path.is_symlink():
                old_path.unlink()
            else:
                shutil.rmtree(old_path)
            print(f"  Removed old {old_path}")

    # Symlink individual commands (kitt-* files)
    commands_src = shared_dir / "commands"
    commands_dst_dir = get_home() / ".claude" / "commands"
    commands_dst_dir.mkdir(parents=True, exist_ok=True)
    cmd_count = 0
    for cmd_file in commands_src.glob("kitt-*.md"):
        create_or_update_symlink(cmd_file, commands_dst_dir / cmd_file.name)
        cmd_count += 1
    print(f"  Symlinked {cmd_count} commands to {commands_dst_dir}")

    # Symlink individual agents (kitt-* files)
    agents_src = shared_dir / "agents"
    agents_dst_dir = get_home() / ".claude" / "agents"
    agents_dst_dir.mkdir(parents=True, exist_ok=True)
    agent_count = 0
    for agent_file in agents_src.glob("kitt-*.md"):
        create_or_update_symlink(agent_file, agents_dst_dir / agent_file.name)
        agent_count += 1
    print(f"  Symlinked {agent_count} agents to {agents_dst_dir}")

    # Symlink individual skills (kitt-* directories with SKILL.md)
    skills_src = shared_dir / "skills"
    skills_dst_dir = get_home() / ".claude" / "skills"
    skills_dst_dir.mkdir(parents=True, exist_ok=True)
    skill_count = 0
    for skill_dir in skills_src.iterdir():
        if skill_dir.is_dir() and skill_dir.name.startswith("kitt-") and (skill_dir / "SKILL.md").exists():
            create_or_update_symlink(skill_dir, skills_dst_dir / skill_dir.name)
            skill_count += 1
    print(f"  Symlinked {skill_count} skills to {skills_dst_dir}")


def convert_commands_for_gemini(src_dir: Path, dst_dir: Path) -> tuple[int, int]:
    """Convert Claude commands to Gemini TOML format.

    Only converts tier 1 and 2 commands. Tier 3 (Claude-specific) are skipped.

    Returns tuple of (converted, skipped).
    """
    converted = 0
    skipped = 0

    # Remove existing destination if present
    if dst_dir.exists():
        shutil.rmtree(dst_dir)
    dst_dir.mkdir(parents=True, exist_ok=True)

    # Convert kitt-*.md files (flat structure)
    for src_file in src_dir.glob("kitt-*.md"):
        resource_name = src_file.stem
        if not is_convertible(resource_name, 'command'):
            skipped += 1
            continue

        content = src_file.read_text()
        toml_content = to_gemini_toml(content, resource_name)
        dst_file = dst_dir / src_file.with_suffix(".toml").name
        dst_file.write_text(toml_content)
        converted += 1

    return converted, skipped


def setup_gemini(workspace: Path) -> None:
    """Configure Gemini CLI."""
    print("\nGemini CLI:")

    shared_dir = workspace / ".ai-cli" / "shared"

    gemini_settings = get_home() / ".gemini" / "settings.json"
    mcp_config = get_mcp_config(workspace)

    if update_json_file(gemini_settings, "mcpServers", mcp_config):
        print(f"  Updated {gemini_settings}")

    # Clean up old ai/ subdirectory if it exists
    old_gemini_ai = get_home() / ".gemini" / "commands" / "ai"
    if old_gemini_ai.exists():
        shutil.rmtree(old_gemini_ai)
        print(f"  Removed old {old_gemini_ai}")

    # Convert commands to TOML format (flat, no subdirectory)
    commands_src = shared_dir / "commands"
    commands_dst = get_home() / ".gemini" / "commands"
    converted, skipped = convert_commands_for_gemini(commands_src, commands_dst)
    print(f"  Converted {converted} commands to {commands_dst}")
    if skipped:
        print(f"  Skipped {skipped} Claude-specific commands")


def convert_agents_for_copilot(src_dir: Path, dst_dir: Path) -> tuple[int, int]:
    """Convert Claude agents to Copilot .agent.md format.

    Only converts tier 1 and 2 agents. Tier 3 (Claude-specific) are skipped.

    Returns tuple of (converted, skipped).
    """
    converted = 0
    skipped = 0

    # Remove existing destination if present
    if dst_dir.exists():
        shutil.rmtree(dst_dir)
    dst_dir.mkdir(parents=True, exist_ok=True)

    # Convert kitt-*.md files to .agent.md
    for src_file in src_dir.glob("kitt-*.md"):
        resource_name = src_file.stem
        if not is_convertible(resource_name, 'agent'):
            skipped += 1
            continue

        content = src_file.read_text()
        agent_content = to_copilot_agent(content, resource_name)
        # Copilot uses .agent.md extension
        dst_file = dst_dir / f"{src_file.stem}.agent.md"
        dst_file.write_text(agent_content)
        converted += 1

    return converted, skipped


def setup_copilot(workspace: Path) -> None:
    """Configure Copilot CLI."""
    print("\nCopilot CLI:")

    shared_dir = workspace / ".ai-cli" / "shared"

    copilot_config = get_home() / ".copilot" / "mcp-config.json"
    mcp_config = get_mcp_config(workspace, for_copilot=True)

    if update_json_file(copilot_config, "mcpServers", mcp_config):
        print(f"  Updated {copilot_config}")

    # Convert agents to .agent.md format
    agents_src = shared_dir / "agents"
    agents_dst = get_home() / ".copilot" / "agents"
    converted, skipped = convert_agents_for_copilot(agents_src, agents_dst)
    print(f"  Converted {converted} agents to {agents_dst}")
    if skipped:
        print(f"  Skipped {skipped} Claude-specific agents")


def initialize_workspace(workspace: Path) -> int:
    """Initialize Tool-KITT for a workspace."""
    print(f"Initializing Tool-KITT")
    print(f"Workspace: {workspace}")
    print("=" * 50)

    if not workspace.exists():
        print(f"Error: Directory does not exist: {workspace}")
        return 1

    # Create workspace structure
    print("\nCreating workspace structure...")
    create_workspace_structure(workspace)

    # Copy defaults to workspace
    print("\nCopying default resources...")
    copy_defaults(workspace)

    # Setup CLIs
    print("\nConfiguring AI CLIs...")
    setup_claude(workspace)
    setup_gemini(workspace)
    setup_copilot(workspace)

    print("\n" + "=" * 50)
    print("Setup complete!")
    print(f"\nWorkspace: {workspace}")
    print(f"Resources: {workspace / '.ai-cli' / 'shared'}")
    print("\nClaude Code:")
    print("  Commands: /kitt-* (e.g., /kitt-consider-pareto)")
    print("  Agents:   @kitt-* (e.g., @kitt-code-reviewer)")
    print("  Skills:   kitt-* (e.g., kitt-create-plans)")
    print("\nGemini CLI:")
    print("  Commands: /kitt-* (e.g., /kitt-consider-pareto)")
    print("\nCopilot CLI:")
    print("  Agents:   /agent kitt-* (e.g., kitt-code-reviewer)")
    print("\nAll CLIs: MCP tools available (36 tools)")
    print("\nRestart your CLI to load changes.")

    return 0
