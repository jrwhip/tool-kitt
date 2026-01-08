#!/usr/bin/env python3
"""
AI CLI MCP Server - Shared tools for Claude, Gemini, and Copilot CLIs

Provides unified tools for managing projects, git operations, and accessing
shared commands, skills, and agents.
"""

import json
import os
import subprocess
from pathlib import Path
from typing import Optional

from mcp.server.fastmcp import FastMCP

mcp = FastMCP("ai-cli")

# Workspace path from environment or None (will be set at runtime)
_workspace: Optional[Path] = None

# Package root (where agents/, commands/, skills/ live)
_package_root: Optional[Path] = None


def get_package_root() -> Path:
    """Get the package root directory (where resources are bundled)."""
    global _package_root
    if _package_root is None:
        # Go up from src/ai_cli_mcp/ to package root
        _package_root = Path(__file__).parent.parent.parent
    return _package_root


def get_workspace() -> Path:
    """Get the workspace path."""
    global _workspace
    if _workspace is None:
        ws = os.environ.get("AI_CLI_WORKSPACE")
        if ws:
            _workspace = Path(ws).expanduser().resolve()
        else:
            _workspace = Path.cwd()
    return _workspace


def get_shared_dir() -> Path:
    """Get the shared resources directory (workspace-local or bundled fallback)."""
    workspace = get_workspace()
    local_shared = workspace / ".ai-cli" / "shared"

    if local_shared.exists():
        return local_shared

    # Fall back to bundled defaults in package
    return get_package_root()


def get_commands_dir() -> Path:
    return get_shared_dir() / "commands"


def get_skills_dir() -> Path:
    return get_shared_dir() / "skills"


def get_agents_dir() -> Path:
    return get_shared_dir() / "agents"


def get_context_dir() -> Path:
    return get_shared_dir() / "context"


# ============================================================================
# PROJECT TOOLS
# ============================================================================

@mcp.tool()
def list_projects() -> str:
    """List all projects in the workspace with their status."""
    workspace = get_workspace()
    projects = []

    for item in workspace.iterdir():
        if item.is_dir() and not item.name.startswith('.'):
            project_info = {"name": item.name, "path": str(item)}

            pkg = item / "package.json"
            if pkg.exists():
                try:
                    with open(pkg) as f:
                        data = json.load(f)
                        project_info["type"] = data.get("name", "unknown")
                        project_info["version"] = data.get("version", "unknown")
                except Exception:
                    pass

            if (item / ".git").exists():
                project_info["git"] = True
                try:
                    result = subprocess.run(
                        ["git", "status", "--porcelain"],
                        cwd=item,
                        capture_output=True,
                        text=True
                    )
                    project_info["dirty"] = bool(result.stdout.strip())
                except Exception:
                    pass

            project_info["has_claude"] = (item / ".claude").exists() or (item / "CLAUDE.md").exists()
            project_info["has_gemini"] = (item / ".gemini").exists() or (item / "GEMINI.md").exists()

            projects.append(project_info)

    return json.dumps(projects, indent=2)


@mcp.tool()
def get_project_context(project_name: str) -> str:
    """Get the full context for a project including its CLAUDE.md, package.json, etc."""
    workspace = get_workspace()
    project_path = workspace / project_name

    if not project_path.exists():
        return f"Error: Project '{project_name}' not found in {workspace}"

    context = {"project": project_name, "path": str(project_path)}

    claude_md = project_path / "CLAUDE.md"
    if claude_md.exists():
        context["claude_md"] = claude_md.read_text()

    pkg = project_path / "package.json"
    if pkg.exists():
        try:
            with open(pkg) as f:
                context["package"] = json.load(f)
        except Exception as e:
            context["package_error"] = str(e)

    context["structure"] = [
        item.name for item in project_path.iterdir()
        if not item.name.startswith('.') and item.name != "node_modules"
    ][:20]

    return json.dumps(context, indent=2)


# ============================================================================
# GIT TOOLS
# ============================================================================

@mcp.tool()
def git_status(project_name: str) -> str:
    """Get git status for a project."""
    workspace = get_workspace()
    project_path = workspace / project_name

    if not project_path.exists():
        return f"Error: Project '{project_name}' not found"

    if not (project_path / ".git").exists():
        return f"Error: Project '{project_name}' is not a git repository"

    try:
        result = subprocess.run(
            ["git", "status"],
            cwd=project_path,
            capture_output=True,
            text=True
        )
        return result.stdout or result.stderr
    except Exception as e:
        return f"Error: {e}"


@mcp.tool()
def git_diff(project_name: str, staged: bool = False) -> str:
    """Get git diff for a project. Set staged=True for staged changes only."""
    workspace = get_workspace()
    project_path = workspace / project_name

    if not project_path.exists():
        return f"Error: Project '{project_name}' not found"

    cmd = ["git", "diff"]
    if staged:
        cmd.append("--staged")

    try:
        result = subprocess.run(
            cmd,
            cwd=project_path,
            capture_output=True,
            text=True
        )
        return result.stdout or "No changes"
    except Exception as e:
        return f"Error: {e}"


@mcp.tool()
def git_log(project_name: str, count: int = 10) -> str:
    """Get recent git commits for a project."""
    workspace = get_workspace()
    project_path = workspace / project_name

    if not project_path.exists():
        return f"Error: Project '{project_name}' not found"

    try:
        result = subprocess.run(
            ["git", "log", f"-{count}", "--oneline", "--decorate"],
            cwd=project_path,
            capture_output=True,
            text=True
        )
        return result.stdout or result.stderr
    except Exception as e:
        return f"Error: {e}"


# ============================================================================
# SHARED RESOURCES
# ============================================================================

@mcp.tool()
def list_shared_commands() -> str:
    """List all available shared commands."""
    commands = []
    commands_dir = get_commands_dir()
    if commands_dir.exists():
        for cmd_file in commands_dir.rglob("*.md"):
            rel_path = cmd_file.relative_to(commands_dir)
            commands.append({"name": str(rel_path.with_suffix('')), "file": str(cmd_file)})
    return json.dumps(commands, indent=2)


@mcp.tool()
def get_shared_command(command_name: str) -> str:
    """Get the content of a shared command."""
    cmd_file = get_commands_dir() / f"{command_name}.md"
    if cmd_file.exists():
        return cmd_file.read_text()
    return f"Error: Command '{command_name}' not found"


@mcp.tool()
def list_shared_skills() -> str:
    """List all available shared skills."""
    skills = []
    skills_dir = get_skills_dir()
    if skills_dir.exists():
        # Skills are directories with SKILL.md inside
        for skill_dir in skills_dir.iterdir():
            if skill_dir.is_dir():
                skill_file = skill_dir / "SKILL.md"
                if skill_file.exists():
                    skills.append({"name": skill_dir.name, "file": str(skill_file)})
    return json.dumps(skills, indent=2)


@mcp.tool()
def get_shared_skill(skill_name: str) -> str:
    """Get the content of a shared skill."""
    skill_file = get_skills_dir() / skill_name / "SKILL.md"
    if skill_file.exists():
        return skill_file.read_text()
    return f"Error: Skill '{skill_name}' not found"


@mcp.tool()
def list_shared_agents() -> str:
    """List all available shared agents."""
    agents = []
    agents_dir = get_agents_dir()
    if agents_dir.exists():
        for agent_file in agents_dir.glob("*.md"):
            agents.append({"name": agent_file.stem, "file": str(agent_file)})
    return json.dumps(agents, indent=2)


@mcp.tool()
def get_shared_agent(agent_name: str) -> str:
    """Get the content of a shared agent."""
    agent_file = get_agents_dir() / f"{agent_name}.md"
    if agent_file.exists():
        return agent_file.read_text()
    return f"Error: Agent '{agent_name}' not found"


@mcp.tool()
def list_shared_context() -> str:
    """List all available shared context documents."""
    docs = []
    context_dir = get_context_dir()
    if context_dir.exists():
        for doc_file in context_dir.glob("*.md"):
            docs.append({"name": doc_file.stem, "file": str(doc_file)})
    return json.dumps(docs, indent=2)


@mcp.tool()
def get_shared_context(context_name: str) -> str:
    """Get the content of a shared context document."""
    ctx_file = get_context_dir() / f"{context_name}.md"
    if ctx_file.exists():
        return ctx_file.read_text()
    return f"Error: Context '{context_name}' not found"


# ============================================================================
# TODO MANAGEMENT
# ============================================================================

@mcp.tool()
def add_todo(title: str, problem: str, files: str = "", solution: str = "") -> str:
    """Add a todo item to TO-DOS.md in the workspace.

    Args:
        title: Brief action title (e.g., "Fix authentication bug")
        problem: What's wrong or why this is needed
        files: Comma-separated file paths with line numbers (e.g., "src/auth.ts:42-50")
        solution: Optional approach hints or constraints
    """
    from datetime import datetime

    workspace = get_workspace()
    todos_file = workspace / "TO-DOS.md"

    # Generate timestamp
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M")

    # Build todo entry
    entry_parts = [f"- **{title}**"]
    if problem:
        entry_parts.append(f"**Problem:** {problem}")
    if files:
        entry_parts.append(f"**Files:** `{files}`")
    if solution:
        entry_parts.append(f"**Solution:** {solution}")

    todo_entry = " ".join(entry_parts)

    # Build section
    # Create a brief heading from the title (first 5 words max)
    heading_words = title.split()[:5]
    heading = " ".join(heading_words)
    section = f"\n## {heading} - {timestamp}\n\n{todo_entry}\n"

    # Append to file (create if doesn't exist)
    if todos_file.exists():
        content = todos_file.read_text()
        content += section
    else:
        content = f"# TO-DOS\n{section}"

    todos_file.write_text(content)

    return f"Added todo: {title}"


@mcp.tool()
def list_todos() -> str:
    """List all todos from TO-DOS.md in the workspace."""
    import re

    workspace = get_workspace()
    todos_file = workspace / "TO-DOS.md"

    if not todos_file.exists():
        return json.dumps({"todos": [], "message": "No TO-DOS.md file found"})

    content = todos_file.read_text()

    # Parse todos: find all lines starting with "- **"
    todos = []
    current_section = None

    for line in content.split('\n'):
        # Track section headings
        if line.startswith('## '):
            current_section = line[3:].strip()
        # Find todo items
        elif line.strip().startswith('- **'):
            # Extract title from "- **Title**" pattern
            match = re.match(r'- \*\*([^*]+)\*\*', line.strip())
            if match:
                todos.append({
                    "title": match.group(1),
                    "section": current_section,
                    "full_line": line.strip()
                })

    return json.dumps({"todos": todos, "count": len(todos)}, indent=2)


@mcp.tool()
def complete_todo(title: str) -> str:
    """Mark a todo as complete by removing it from TO-DOS.md.

    Args:
        title: The title of the todo to complete (must match exactly)
    """
    workspace = get_workspace()
    todos_file = workspace / "TO-DOS.md"

    if not todos_file.exists():
        return "Error: No TO-DOS.md file found"

    content = todos_file.read_text()
    lines = content.split('\n')

    # Find and remove the todo line
    new_lines = []
    found = False

    for line in lines:
        if f"- **{title}**" in line:
            found = True
            continue  # Skip this line (remove it)
        new_lines.append(line)

    if not found:
        return f"Error: Todo '{title}' not found"

    # Clean up empty sections (## heading with no todo items before next ## or EOF)
    cleaned_lines = []
    i = 0
    while i < len(new_lines):
        line = new_lines[i]
        if line.startswith('## '):
            # Look ahead to find end of this section (next ## heading or EOF)
            j = i + 1
            while j < len(new_lines) and not new_lines[j].startswith('## '):
                j += 1
            # Check if section has any todo items
            has_content = any(new_lines[k].strip().startswith('- **') for k in range(i + 1, j))
            if has_content:
                cleaned_lines.append(line)
            # else: skip empty section heading
        else:
            cleaned_lines.append(line)
        i += 1

    # Remove excess blank lines
    result = '\n'.join(cleaned_lines)
    while '\n\n\n' in result:
        result = result.replace('\n\n\n', '\n\n')

    todos_file.write_text(result)

    return f"Completed: {title}"


# ============================================================================
# HANDOFF / CONTEXT
# ============================================================================

@mcp.tool()
def create_handoff(summary: str, next_steps: str, context: str = "") -> str:
    """Create a whats-next.md handoff document for continuing work in a fresh context.

    Args:
        summary: Brief summary of what was accomplished
        next_steps: What needs to happen next (bullet points recommended)
        context: Optional additional context (files modified, decisions made, etc.)
    """
    from datetime import datetime

    workspace = get_workspace()
    handoff_file = workspace / "whats-next.md"

    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M")

    content = f"""# What's Next - {timestamp}

## Summary
{summary}

## Next Steps
{next_steps}
"""

    if context:
        content += f"""
## Context
{context}
"""

    handoff_file.write_text(content)

    return f"Created handoff document: {handoff_file}"


@mcp.tool()
def get_handoff() -> str:
    """Read the current whats-next.md handoff document if it exists."""
    workspace = get_workspace()
    handoff_file = workspace / "whats-next.md"

    if not handoff_file.exists():
        return "No whats-next.md file found in workspace"

    return handoff_file.read_text()


# ============================================================================
# TIME TRACKING
# ============================================================================

def get_time_tracking_file() -> Path:
    """Get the time tracking JSON file path."""
    return get_workspace() / "time-tracking.json"


def load_time_tracking() -> dict:
    """Load time tracking data from JSON file."""
    tf = get_time_tracking_file()
    if tf.exists():
        try:
            return json.loads(tf.read_text())
        except json.JSONDecodeError:
            pass
    return {"entries": [], "active_timer": None}


def save_time_tracking(data: dict) -> None:
    """Save time tracking data to JSON file."""
    tf = get_time_tracking_file()
    tf.write_text(json.dumps(data, indent=2))


def parse_duration(duration_str: str) -> int:
    """Parse duration string like '1h30m', '45m', '2h' to minutes."""
    import re
    total_minutes = 0

    # Match hours
    hours_match = re.search(r'(\d+)h', duration_str)
    if hours_match:
        total_minutes += int(hours_match.group(1)) * 60

    # Match minutes
    minutes_match = re.search(r'(\d+)m', duration_str)
    if minutes_match:
        total_minutes += int(minutes_match.group(1))

    # If just a number, assume minutes
    if total_minutes == 0 and duration_str.isdigit():
        total_minutes = int(duration_str)

    return total_minutes


def format_duration(minutes: int) -> str:
    """Format minutes as 'Xh Ym' string."""
    if minutes < 60:
        return f"{minutes}m"
    hours = minutes // 60
    mins = minutes % 60
    if mins == 0:
        return f"{hours}h"
    return f"{hours}h {mins}m"


def sync_to_toggl(task: str, start_iso: str, duration_minutes: int, project: str = "") -> bool:
    """Sync time entry to Toggl if API key is configured."""
    import urllib.request
    import urllib.error
    import base64

    api_key = os.environ.get("TOGGL_API_KEY")
    if not api_key:
        return False

    # Toggl API v9
    url = "https://api.track.toggl.com/api/v9/me/time_entries"

    # Build payload
    payload = {
        "description": task,
        "start": start_iso,
        "duration": duration_minutes * 60,  # Toggl wants seconds
        "created_with": "ai-cli-mcp"
    }

    if project:
        payload["tags"] = [project]

    # Toggl uses basic auth with API key as username
    auth_string = base64.b64encode(f"{api_key}:api_token".encode()).decode()

    try:
        req = urllib.request.Request(
            url,
            data=json.dumps(payload).encode('utf-8'),
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Basic {auth_string}"
            },
            method="POST"
        )
        urllib.request.urlopen(req, timeout=10)
        return True
    except urllib.error.URLError:
        return False


@mcp.tool()
def start_timer(task: str, project: str = "") -> str:
    """Start tracking time for a task.

    Args:
        task: Description of what you're working on
        project: Optional project name
    """
    from datetime import datetime
    import uuid

    data = load_time_tracking()

    # Check if timer already running
    if data.get("active_timer"):
        active = data["active_timer"]
        return f"Error: Timer already running for '{active['task']}' since {active['start']}"

    # Start new timer
    data["active_timer"] = {
        "id": str(uuid.uuid4()),
        "task": task,
        "project": project,
        "start": datetime.now().isoformat()
    }

    save_time_tracking(data)

    return f"Timer started: {task}" + (f" [{project}]" if project else "")


@mcp.tool()
def stop_timer() -> str:
    """Stop the current timer and log the time entry."""
    from datetime import datetime

    data = load_time_tracking()

    if not data.get("active_timer"):
        return "Error: No timer running"

    active = data["active_timer"]
    start_time = datetime.fromisoformat(active["start"])
    end_time = datetime.now()
    duration_minutes = int((end_time - start_time).total_seconds() / 60)

    # Create entry
    entry = {
        "id": active["id"],
        "task": active["task"],
        "project": active.get("project", ""),
        "start": active["start"],
        "end": end_time.isoformat(),
        "duration_minutes": duration_minutes,
        "synced_to_toggl": False
    }

    # Try Toggl sync
    if sync_to_toggl(entry["task"], entry["start"], duration_minutes, entry["project"]):
        entry["synced_to_toggl"] = True

    # Save entry
    data["entries"].append(entry)
    data["active_timer"] = None
    save_time_tracking(data)

    duration_str = format_duration(duration_minutes)
    result = f"Stopped: {entry['task']} - {duration_str}"
    if entry["synced_to_toggl"]:
        result += " (synced to Toggl)"

    return result


@mcp.tool()
def log_time(task: str, duration: str, project: str = "", date: str = "") -> str:
    """Log a manual time entry.

    Args:
        task: Description of what you worked on
        duration: Duration string like '1h30m', '45m', '2h'
        project: Optional project name
        date: Optional date (YYYY-MM-DD), defaults to today
    """
    from datetime import datetime
    import uuid

    duration_minutes = parse_duration(duration)
    if duration_minutes == 0:
        return "Error: Invalid duration format. Use '1h30m', '45m', '2h', etc."

    # Parse or default date
    if date:
        try:
            entry_date = datetime.strptime(date, "%Y-%m-%d")
        except ValueError:
            return "Error: Invalid date format. Use YYYY-MM-DD"
    else:
        entry_date = datetime.now()

    # Create start time at 9am on that day
    start_time = entry_date.replace(hour=9, minute=0, second=0, microsecond=0)
    end_time = start_time.replace(
        hour=9 + duration_minutes // 60,
        minute=duration_minutes % 60
    )

    entry = {
        "id": str(uuid.uuid4()),
        "task": task,
        "project": project,
        "start": start_time.isoformat(),
        "end": end_time.isoformat(),
        "duration_minutes": duration_minutes,
        "synced_to_toggl": False
    }

    # Try Toggl sync
    if sync_to_toggl(task, entry["start"], duration_minutes, project):
        entry["synced_to_toggl"] = True

    # Save
    data = load_time_tracking()
    data["entries"].append(entry)
    save_time_tracking(data)

    duration_str = format_duration(duration_minutes)
    result = f"Logged: {task} - {duration_str}"
    if project:
        result += f" [{project}]"
    if entry["synced_to_toggl"]:
        result += " (synced to Toggl)"

    return result


@mcp.tool()
def list_time_entries(days: int = 7) -> str:
    """List recent time entries.

    Args:
        days: Number of days to look back (default 7)
    """
    from datetime import datetime, timedelta

    data = load_time_tracking()
    cutoff = datetime.now() - timedelta(days=days)

    recent = []
    for entry in data.get("entries", []):
        try:
            entry_time = datetime.fromisoformat(entry["start"])
            if entry_time >= cutoff:
                recent.append({
                    "task": entry["task"],
                    "project": entry.get("project", ""),
                    "date": entry_time.strftime("%Y-%m-%d"),
                    "duration": format_duration(entry["duration_minutes"]),
                    "duration_minutes": entry["duration_minutes"],
                    "synced": entry.get("synced_to_toggl", False)
                })
        except (KeyError, ValueError):
            continue

    # Sort by date descending
    recent.sort(key=lambda x: x["date"], reverse=True)

    result = {
        "entries": recent,
        "count": len(recent),
        "period_days": days
    }

    # Include active timer if any
    if data.get("active_timer"):
        active = data["active_timer"]
        start_time = datetime.fromisoformat(active["start"])
        elapsed = int((datetime.now() - start_time).total_seconds() / 60)
        result["active_timer"] = {
            "task": active["task"],
            "project": active.get("project", ""),
            "started": active["start"],
            "elapsed": format_duration(elapsed)
        }

    return json.dumps(result, indent=2)


@mcp.tool()
def time_summary(days: int = 7) -> str:
    """Get time summary grouped by project.

    Args:
        days: Number of days to summarize (default 7)
    """
    from datetime import datetime, timedelta
    from collections import defaultdict

    data = load_time_tracking()
    cutoff = datetime.now() - timedelta(days=days)

    by_project = defaultdict(lambda: {"minutes": 0, "tasks": []})
    total_minutes = 0

    for entry in data.get("entries", []):
        try:
            entry_time = datetime.fromisoformat(entry["start"])
            if entry_time >= cutoff:
                project = entry.get("project") or "(no project)"
                minutes = entry["duration_minutes"]
                by_project[project]["minutes"] += minutes
                by_project[project]["tasks"].append(entry["task"])
                total_minutes += minutes
        except (KeyError, ValueError):
            continue

    # Build summary
    summary = {
        "period_days": days,
        "total": format_duration(total_minutes),
        "total_minutes": total_minutes,
        "by_project": {}
    }

    for project, data in sorted(by_project.items(), key=lambda x: -x[1]["minutes"]):
        summary["by_project"][project] = {
            "total": format_duration(data["minutes"]),
            "total_minutes": data["minutes"],
            "task_count": len(set(data["tasks"]))
        }

    return json.dumps(summary, indent=2)


# ============================================================================
# DICE / RANDOM TOOLS
# ============================================================================

@mcp.tool()
def roll_dice(dice: str = "1d6") -> str:
    """Roll dice using standard notation.

    Args:
        dice: Dice notation like "1d6", "2d20", "3d8+5"
    """
    import re
    import random

    # Parse dice notation: XdY+Z or XdY-Z
    match = re.match(r'^(\d+)d(\d+)([+-]\d+)?$', dice.strip().lower())
    if not match:
        return f"Error: Invalid dice notation '{dice}'. Use format like '2d6', '1d20+5'"

    num_dice = int(match.group(1))
    sides = int(match.group(2))
    modifier = int(match.group(3)) if match.group(3) else 0

    if num_dice < 1 or num_dice > 100:
        return "Error: Number of dice must be between 1 and 100"
    if sides < 2 or sides > 1000:
        return "Error: Dice sides must be between 2 and 1000"

    rolls = [random.randint(1, sides) for _ in range(num_dice)]
    total = sum(rolls) + modifier

    result = {
        "dice": dice,
        "rolls": rolls,
        "modifier": modifier,
        "total": total
    }

    return json.dumps(result)


@mcp.tool()
def flip_coin(count: int = 1) -> str:
    """Flip one or more coins.

    Args:
        count: Number of coins to flip (default 1)
    """
    import random

    if count < 1 or count > 100:
        return "Error: Count must be between 1 and 100"

    flips = [random.choice(["heads", "tails"]) for _ in range(count)]

    heads = flips.count("heads")
    tails = flips.count("tails")

    result = {
        "flips": flips,
        "heads": heads,
        "tails": tails,
        "count": count
    }

    return json.dumps(result)


@mcp.tool()
def random_choice(options: str) -> str:
    """Pick randomly from comma-separated options.

    Args:
        options: Comma-separated list of options (e.g., "pizza,tacos,sushi")
    """
    import random

    choices = [opt.strip() for opt in options.split(",") if opt.strip()]

    if len(choices) < 2:
        return "Error: Provide at least 2 comma-separated options"

    choice = random.choice(choices)

    result = {
        "options": choices,
        "choice": choice
    }

    return json.dumps(result)


@mcp.tool()
def random_number(min_val: int = 1, max_val: int = 100) -> str:
    """Generate a random number in a range.

    Args:
        min_val: Minimum value (inclusive)
        max_val: Maximum value (inclusive)
    """
    import random

    if min_val >= max_val:
        return "Error: min_val must be less than max_val"

    number = random.randint(min_val, max_val)

    result = {
        "min": min_val,
        "max": max_val,
        "number": number
    }

    return json.dumps(result)


# ============================================================================
# WEATHER TOOLS
# ============================================================================

def geocode_location(location: str) -> tuple[float, float, str] | None:
    """Geocode a location string to lat/lon using Open-Meteo."""
    import urllib.request
    import urllib.parse
    import urllib.error

    url = f"https://geocoding-api.open-meteo.com/v1/search?name={urllib.parse.quote(location)}&count=1"

    try:
        with urllib.request.urlopen(url, timeout=10) as response:
            data = json.loads(response.read().decode())
            if data.get("results"):
                r = data["results"][0]
                display = f"{r.get('name', '')}, {r.get('admin1', '')}, {r.get('country', '')}"
                return r["latitude"], r["longitude"], display
    except (urllib.error.URLError, json.JSONDecodeError, KeyError):
        pass
    return None


@mcp.tool()
def get_weather(location: str, units: str = "imperial") -> str:
    """Get current weather for a location.

    Args:
        location: City name or location (e.g., "Austin, TX" or "Paris, France")
        units: "imperial" (°F, mph) or "metric" (°C, km/h)
    """
    import urllib.request
    import urllib.error

    # Geocode location
    geo = geocode_location(location)
    if not geo:
        return f"Error: Could not find location '{location}'"

    lat, lon, display_name = geo

    # Build API URL
    temp_unit = "fahrenheit" if units == "imperial" else "celsius"
    wind_unit = "mph" if units == "imperial" else "kmh"

    url = (
        f"https://api.open-meteo.com/v1/forecast?"
        f"latitude={lat}&longitude={lon}"
        f"&current=temperature_2m,relative_humidity_2m,weather_code,wind_speed_10m"
        f"&temperature_unit={temp_unit}&wind_speed_unit={wind_unit}"
    )

    try:
        with urllib.request.urlopen(url, timeout=10) as response:
            data = json.loads(response.read().decode())
    except (urllib.error.URLError, json.JSONDecodeError) as e:
        return f"Error fetching weather: {e}"

    current = data.get("current", {})

    # Weather code to description
    weather_codes = {
        0: "Clear sky", 1: "Mainly clear", 2: "Partly cloudy", 3: "Overcast",
        45: "Fog", 48: "Depositing rime fog",
        51: "Light drizzle", 53: "Moderate drizzle", 55: "Dense drizzle",
        61: "Slight rain", 63: "Moderate rain", 65: "Heavy rain",
        71: "Slight snow", 73: "Moderate snow", 75: "Heavy snow",
        80: "Slight rain showers", 81: "Moderate rain showers", 82: "Violent rain showers",
        95: "Thunderstorm", 96: "Thunderstorm with slight hail", 99: "Thunderstorm with heavy hail"
    }

    weather_code = current.get("weather_code", 0)
    conditions = weather_codes.get(weather_code, f"Unknown ({weather_code})")

    temp_symbol = "°F" if units == "imperial" else "°C"
    wind_symbol = "mph" if units == "imperial" else "km/h"

    result = {
        "location": display_name,
        "temperature": f"{current.get('temperature_2m', 'N/A')}{temp_symbol}",
        "conditions": conditions,
        "humidity": f"{current.get('relative_humidity_2m', 'N/A')}%",
        "wind": f"{current.get('wind_speed_10m', 'N/A')} {wind_symbol}",
        "units": units
    }

    return json.dumps(result, indent=2)


@mcp.tool()
def get_forecast(location: str, days: int = 3, units: str = "imperial") -> str:
    """Get weather forecast for a location.

    Args:
        location: City name or location
        days: Number of days to forecast (1-7)
        units: "imperial" (°F) or "metric" (°C)
    """
    import urllib.request
    import urllib.error

    if days < 1 or days > 7:
        return "Error: Days must be between 1 and 7"

    geo = geocode_location(location)
    if not geo:
        return f"Error: Could not find location '{location}'"

    lat, lon, display_name = geo

    temp_unit = "fahrenheit" if units == "imperial" else "celsius"

    url = (
        f"https://api.open-meteo.com/v1/forecast?"
        f"latitude={lat}&longitude={lon}"
        f"&daily=temperature_2m_max,temperature_2m_min,weather_code"
        f"&temperature_unit={temp_unit}&forecast_days={days}"
    )

    try:
        with urllib.request.urlopen(url, timeout=10) as response:
            data = json.loads(response.read().decode())
    except (urllib.error.URLError, json.JSONDecodeError) as e:
        return f"Error fetching forecast: {e}"

    daily = data.get("daily", {})

    weather_codes = {
        0: "Clear", 1: "Mainly clear", 2: "Partly cloudy", 3: "Overcast",
        45: "Fog", 48: "Fog",
        51: "Drizzle", 53: "Drizzle", 55: "Drizzle",
        61: "Rain", 63: "Rain", 65: "Heavy rain",
        71: "Snow", 73: "Snow", 75: "Heavy snow",
        80: "Showers", 81: "Showers", 82: "Heavy showers",
        95: "Thunderstorm", 96: "Thunderstorm", 99: "Thunderstorm"
    }

    temp_symbol = "°F" if units == "imperial" else "°C"

    forecast = []
    dates = daily.get("time", [])
    highs = daily.get("temperature_2m_max", [])
    lows = daily.get("temperature_2m_min", [])
    codes = daily.get("weather_code", [])

    for i in range(min(days, len(dates))):
        code = codes[i] if i < len(codes) else 0
        forecast.append({
            "date": dates[i],
            "high": f"{highs[i]}{temp_symbol}" if i < len(highs) else "N/A",
            "low": f"{lows[i]}{temp_symbol}" if i < len(lows) else "N/A",
            "conditions": weather_codes.get(code, "Unknown")
        })

    result = {
        "location": display_name,
        "forecast": forecast,
        "units": units
    }

    return json.dumps(result, indent=2)


# ============================================================================
# NOTE CAPTURE TOOLS
# ============================================================================

def get_notes_file() -> Path:
    """Get the notes JSON file path."""
    return get_workspace() / "notes.json"


def load_notes() -> dict:
    """Load notes from JSON file."""
    nf = get_notes_file()
    if nf.exists():
        try:
            return json.loads(nf.read_text())
        except json.JSONDecodeError:
            pass
    return {"notes": []}


def save_notes(data: dict) -> None:
    """Save notes to JSON file."""
    nf = get_notes_file()
    nf.write_text(json.dumps(data, indent=2))


@mcp.tool()
def add_note(content: str, tags: str = "") -> str:
    """Add a quick note with optional tags.

    Args:
        content: The note content
        tags: Comma-separated tags (e.g., "todo,api,important")
    """
    from datetime import datetime
    import uuid

    tag_list = [t.strip().lower() for t in tags.split(",") if t.strip()]

    note = {
        "id": str(uuid.uuid4())[:8],
        "content": content,
        "tags": tag_list,
        "created": datetime.now().isoformat()
    }

    data = load_notes()
    data["notes"].append(note)
    save_notes(data)

    tag_str = f" [{', '.join(tag_list)}]" if tag_list else ""
    return f"Note added (id: {note['id']}){tag_str}"


@mcp.tool()
def list_notes(tag: str = "", days: int = 30) -> str:
    """List recent notes, optionally filtered by tag.

    Args:
        tag: Filter by this tag (optional)
        days: Number of days to look back (default 30)
    """
    from datetime import datetime, timedelta

    data = load_notes()
    cutoff = datetime.now() - timedelta(days=days)

    notes = []
    for note in data.get("notes", []):
        try:
            created = datetime.fromisoformat(note["created"])
            if created < cutoff:
                continue
            if tag and tag.lower() not in note.get("tags", []):
                continue
            notes.append({
                "id": note["id"],
                "content": note["content"][:100] + ("..." if len(note["content"]) > 100 else ""),
                "tags": note.get("tags", []),
                "created": note["created"]
            })
        except (KeyError, ValueError):
            continue

    notes.sort(key=lambda x: x["created"], reverse=True)

    result = {
        "notes": notes,
        "count": len(notes),
        "filter_tag": tag or None,
        "filter_days": days
    }

    return json.dumps(result, indent=2)


@mcp.tool()
def search_notes(query: str) -> str:
    """Search notes by content.

    Args:
        query: Search term to find in note content
    """
    data = load_notes()
    query_lower = query.lower()

    matches = []
    for note in data.get("notes", []):
        if query_lower in note.get("content", "").lower():
            matches.append({
                "id": note["id"],
                "content": note["content"],
                "tags": note.get("tags", []),
                "created": note["created"]
            })

    matches.sort(key=lambda x: x["created"], reverse=True)

    result = {
        "query": query,
        "matches": matches,
        "count": len(matches)
    }

    return json.dumps(result, indent=2)


@mcp.tool()
def delete_note(note_id: str) -> str:
    """Delete a note by its ID.

    Args:
        note_id: The note ID (shown in list_notes output)
    """
    data = load_notes()

    original_count = len(data["notes"])
    data["notes"] = [n for n in data["notes"] if n.get("id") != note_id]

    if len(data["notes"]) == original_count:
        return f"Error: Note '{note_id}' not found"

    save_notes(data)
    return f"Deleted note: {note_id}"


# ============================================================================
# MCP TOOL CREATOR
# ============================================================================

@mcp.tool()
def create_mcp_tool(name: str, description: str, params: str = "") -> str:
    """Generate boilerplate code for a new MCP tool.

    Args:
        name: Function name for the tool (snake_case)
        description: What the tool does
        params: Parameter definitions, comma-separated (e.g., "query:str,limit:int=10")
    """
    import re

    # Validate name
    if not re.match(r'^[a-z][a-z0-9_]*$', name):
        return "Error: Name must be snake_case (lowercase letters, numbers, underscores)"

    # Parse parameters
    param_list = []
    param_docs = []

    if params:
        for param in params.split(","):
            param = param.strip()
            if not param:
                continue

            # Parse "name:type=default" or "name:type"
            match = re.match(r'^(\w+):(\w+)(?:=(.+))?$', param)
            if not match:
                return f"Error: Invalid param format '{param}'. Use 'name:type' or 'name:type=default'"

            p_name, p_type, p_default = match.groups()

            if p_default:
                param_list.append(f"{p_name}: {p_type} = {p_default}")
            else:
                param_list.append(f"{p_name}: {p_type}")

            param_docs.append(f"        {p_name}: Description")

    # Build function signature
    params_str = ", ".join(param_list) if param_list else ""

    # Build docstring
    if param_docs:
        docstring = f'''    """{description}

    Args:
{chr(10).join(param_docs)}
    """'''
    else:
        docstring = f'    """{description}"""'

    # Generate code
    code = f'''@mcp.tool()
def {name}({params_str}) -> str:
{docstring}
    # TODO: Implement
    result = {{
        "status": "success"
    }}
    return json.dumps(result)
'''

    return f"Generated MCP tool code:\n\n```python\n{code}```\n\nAdd this to your server.py file."


# ============================================================================
# DEV TOOLS
# ============================================================================

@mcp.tool()
def run_npm_script(project_name: str, script: str) -> str:
    """Run an npm/pnpm script in a project. Returns the output."""
    workspace = get_workspace()
    project_path = workspace / project_name

    if not project_path.exists():
        return f"Error: Project '{project_name}' not found"

    pkg = project_path / "package.json"
    if not pkg.exists():
        return f"Error: No package.json in '{project_name}'"

    if (project_path / "pnpm-lock.yaml").exists():
        cmd = ["pnpm", "run", script]
    elif (project_path / "yarn.lock").exists():
        cmd = ["yarn", script]
    else:
        cmd = ["npm", "run", script]

    try:
        result = subprocess.run(
            cmd,
            cwd=project_path,
            capture_output=True,
            text=True,
            timeout=120
        )
        output = result.stdout
        if result.stderr:
            output += "\n\nSTDERR:\n" + result.stderr
        return output or "Script completed with no output"
    except subprocess.TimeoutExpired:
        return "Error: Script timed out after 120 seconds"
    except Exception as e:
        return f"Error: {e}"


@mcp.tool()
def check_build(project_name: str) -> str:
    """Run type-check/build on a project to check for errors."""
    workspace = get_workspace()
    project_path = workspace / project_name

    if not project_path.exists():
        return f"Error: Project '{project_name}' not found"

    pkg = project_path / "package.json"
    if pkg.exists():
        try:
            with open(pkg) as f:
                data = json.load(f)
                scripts = data.get("scripts", {})

                for script in ["typecheck", "type-check", "tsc", "build"]:
                    if script in scripts:
                        return run_npm_script(project_name, script)

                return "No typecheck or build script found in package.json"
        except Exception as e:
            return f"Error reading package.json: {e}"

    return "No package.json found"


# ============================================================================
# ENTRY POINT
# ============================================================================

def run_server(workspace: Optional[str] = None) -> int:
    """Run the MCP server."""
    global _workspace
    if workspace:
        _workspace = Path(workspace).expanduser().resolve()
    mcp.run()
    return 0
