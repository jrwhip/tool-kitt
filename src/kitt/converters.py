"""
Format converters for ai-cli-resources.

Converts Claude format (Markdown + YAML frontmatter) to:
- Gemini CLI TOML commands
- Copilot CLI .agent.md files

Uses conversion_manifest for tier-aware conversion:
- Tier 1: Convert as-is
- Tier 2: Convert with path replacements
- Tier 3: Skip (handled by callers)
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Literal

import yaml

from .conversion_manifest import (
    CLI_EXTRA_CONVERTIBLE_COMMANDS,
    EXPLICIT_INVOCATION_ONLY_COMMANDS,
    SKILL_WRAPPER_COMMANDS,
    apply_path_replacements,
    get_tier,
)

# Claude -> Copilot tool-name mapping, normalized to Copilot's CANONICAL
# tool names (docs.github.com custom-agents reference, fetched
# 2026-07-31). Copilot also accepts the aliases (`shell` for `execute`,
# `custom-agent` for `agent`, ...), but generated frontmatter should not
# depend on alias acceptance staying stable.
#
#   canonical  aliases
#   execute    shell, Bash, powershell
#   read       Read, NotebookRead
#   edit       Edit, MultiEdit, Write, NotebookEdit
#   search     Grep, Glob
#   agent      custom-agent, Task
#   web        WebSearch, WebFetch
#   todo       TodoWrite
COPILOT_TOOL_MAP: dict[str, str] = {
    "Read": "read",
    "NotebookRead": "read",
    "Write": "edit",
    "Edit": "edit",
    "MultiEdit": "edit",
    "NotebookEdit": "edit",
    "Grep": "search",
    "Glob": "search",
    "Bash": "execute",
    "Task": "agent",
    "WebFetch": "web",
    "WebSearch": "web",
    "TodoWrite": "todo",
}

# Phrase substituted for ``$ARGUMENTS`` in generated Copilot skills.
# Copilot Agent Skills have no positional-argument placeholder; the
# operator's message is the argument.
COPILOT_ARGUMENTS_PHRASE = "the user's request (from their message)"


@dataclass
class ParsedDocument:
    """Parsed Claude format file (YAML frontmatter + body)."""

    frontmatter: dict[str, Any] = field(default_factory=dict)
    body: str = ""


def parse_claude(content: str) -> ParsedDocument:
    """Parse Claude format file (YAML frontmatter + body)."""
    content = content.strip()

    # No frontmatter
    if not content.startswith("---"):
        return ParsedDocument(body=content)

    # Find end of frontmatter
    rest = content[3:]  # Skip opening ---
    end_idx = rest.find("\n---")

    if end_idx == -1:
        # Malformed - no closing ---, treat as no frontmatter
        return ParsedDocument(body=content)

    yaml_content = rest[:end_idx].strip()
    body = rest[end_idx + 4:].strip()  # Skip \n---

    # Parse YAML
    try:
        frontmatter = yaml.safe_load(yaml_content) or {}
    except yaml.YAMLError:
        frontmatter = {}

    return ParsedDocument(frontmatter=frontmatter, body=body)


def to_gemini_toml(content: str, resource_name: str = "") -> str:
    """
    Convert Claude command format to Gemini TOML format.

    Args:
        content: Claude format file content
        resource_name: Name of the resource (for tier lookup)

    Conversions:
    - $ARGUMENTS → {{args}}
    - description → description field
    - argument-hint, allowed-tools → ignored (no Gemini equivalent)
    - Path replacements for tier 2 content
    """
    parsed = parse_claude(content)
    frontmatter = parsed.frontmatter
    body = parsed.body

    # Apply path replacements for tier 2 content
    tier = get_tier(resource_name, "command") if resource_name else 1
    if tier == 2:
        body = apply_path_replacements(body, "gemini")

    # Replace argument placeholder
    body = body.replace("$ARGUMENTS", "{{args}}")

    # Convert dynamic bash syntax: !`command` → !{command}
    body = re.sub(r"!\s*`([^`]+)`", r"!{\1}", body)

    # Convert file references: @path → @{path}
    # Match @ followed by a path (not already in braces, not followed by space/newline)
    body = re.sub(r"@([^\s{@\n][^\s\n]*)", r"@{\1}", body)

    # Escape triple single quotes in body if present (for TOML literal strings)
    body = body.replace("'''", "\\'\\'\\'")

    # Build TOML
    lines = []

    if "description" in frontmatter:
        desc = frontmatter["description"]
        # Apply path replacements to description too
        if tier == 2:
            desc = apply_path_replacements(desc, "gemini")
        # Escape quotes in description
        desc = desc.replace('"', '\\"')
        lines.append(f'description = "{desc}"')

    # Use literal strings (''') to avoid escape processing for backslashes
    lines.append(f"prompt = '''\n{body}\n'''")

    return "\n".join(lines)


def to_copilot_agent(content: str, resource_name: str = "") -> str:
    """
    Convert Claude agent format to Copilot .agent.md format.

    Args:
        content: Claude format file content
        resource_name: Name of the resource (for tier lookup)

    Conversions:
    - name → name (lowercase-with-hyphens for filename)
    - description → description
    - tools → mapped to Copilot equivalents
    - body → unchanged (Markdown works in both)
    - Path replacements for tier 2 content
    """
    parsed = parse_claude(content)
    frontmatter = parsed.frontmatter
    body = parsed.body

    # Apply path replacements for tier 2 content
    tier = get_tier(resource_name, "agent") if resource_name else 1
    if tier == 2:
        body = apply_path_replacements(body, "copilot")

    # Tool mapping: Claude → Copilot (canonical names)
    tool_map = COPILOT_TOOL_MAP

    # Build new frontmatter
    new_fm = {}

    if "name" in frontmatter:
        new_fm["name"] = frontmatter["name"]

    if "description" in frontmatter:
        desc = frontmatter["description"]
        # Apply path replacements to description too
        if tier == 2:
            desc = apply_path_replacements(desc, "copilot")
        new_fm["description"] = desc

    # Map tools if present
    if "tools" in frontmatter:
        claude_tools = frontmatter["tools"]
        if isinstance(claude_tools, str):
            claude_tools = [t.strip() for t in claude_tools.split(",")]

        copilot_tools = set()
        for tool in claude_tools:
            # Unknown names (MCP tools like ``mcp__kitt__*``) pass
            # through unchanged; MCP tool names are exact identifiers,
            # not aliases to normalize.
            mapped = tool_map.get(tool, tool)
            copilot_tools.add(mapped)

        if copilot_tools:
            new_fm["tools"] = sorted(copilot_tools)

    # Build output
    if new_fm:
        yaml_str = yaml.dump(new_fm, default_flow_style=False, sort_keys=False).strip()
        return f"---\n{yaml_str}\n---\n\n{body}"
    else:
        return body


def _derive_description(frontmatter: dict[str, Any], body: str, resource_name: str) -> str:
    """Best-effort description for a generated Copilot skill.

    Copilot requires a non-empty ``description`` (it drives skill
    auto-selection). Preference order: frontmatter ``description``,
    first Markdown heading, first non-empty prose sentence, and as a
    last resort a name-derived fallback. Never returns an empty string.
    """
    desc = frontmatter.get("description")
    if isinstance(desc, str) and desc.strip():
        return desc.strip()

    for line in body.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        if stripped.startswith("#"):
            heading = stripped.lstrip("#").strip()
            if heading:
                return heading
            continue
        # First prose line: take up to the first sentence break.
        sentence = re.split(r"(?<=[.!?])\s", stripped, maxsplit=1)[0].strip()
        if sentence:
            return sentence

    return f"KITT command {resource_name}"


def _skill_wrapper_body(resource_name: str, original_body: str) -> str:
    """Rewrite a Skill-tool wrapper command body to native /skill-name form.

    The Claude originals are one-liners like ``Invoke the
    create-agent-skills skill for: $ARGUMENTS`` executed via the Skill
    tool (``allowed-tools: Skill(...)``). Copilot has no Skill tool, but
    the wrapped skill itself is installed natively under
    ``~/.copilot/skills/``, so the generated body points straight at it.
    """
    skill_name = SKILL_WRAPPER_COMMANDS[resource_name]["skill"]
    takes_args = "$ARGUMENTS" in original_body
    lines = [
        f"Load and follow the `/{skill_name}` Agent Skill "
        f"(installed at `~/.copilot/skills/{skill_name}/`).",
    ]
    if takes_args:
        lines.append(
            f"Apply it to {COPILOT_ARGUMENTS_PHRASE}."
        )
    return "\n".join(lines)


def to_copilot_skill(content: str, resource_name: str) -> str:
    """
    Convert a Claude slash command to a Copilot Agent Skill (SKILL.md).

    Copilot CLI has no native markdown slash commands
    (``.github/prompts/*.prompt.md`` is IDE-only), so command parity is
    achieved by installing each convertible command as a generated skill
    under ``~/.copilot/skills/<command-name>/SKILL.md``, invocable as
    ``/<command-name>``.

    Conversions:
    - ``name``: the command name (already lowercase-with-hyphens)
    - ``description``: from frontmatter, else derived (never empty)
    - ``argument-hint``: carried over when the command declares one
    - ``disable-model-invocation: true`` for explicit-invocation-only
      commands (see EXPLICIT_INVOCATION_ONLY_COMMANDS for the rule)
    - body: ``$ARGUMENTS`` -> prose phrase; Copilot path replacements;
      Skill-tool wrapper bodies rewritten to native ``/skill-name`` form
    - ``allowed-tools`` is intentionally dropped: the Claude values
      (``Skill(...)``, ``SlashCommand``) do not map to Copilot's tool
      set, and an over-restrictive allowlist would break the skill.
    """
    parsed = parse_claude(content)
    frontmatter = parsed.frontmatter
    body = parsed.body

    if resource_name in SKILL_WRAPPER_COMMANDS:
        body = _skill_wrapper_body(resource_name, body)
        # Wrapper descriptions are overridden (the originals name
        # Claude Code and must not leak into Copilot skills).
        description = SKILL_WRAPPER_COMMANDS[resource_name]["description"]
    else:
        body = body.replace("$ARGUMENTS", COPILOT_ARGUMENTS_PHRASE)
        body = apply_path_replacements(body, "copilot")
        description = apply_path_replacements(
            _derive_description(frontmatter, body, resource_name), "copilot"
        )

    new_fm: dict[str, Any] = {
        "name": resource_name,
        "description": description,
    }

    # ``argument-hint: [topic]`` is written as prose in the catalog but
    # parses as a YAML flow sequence; rebuild the bracketed string so
    # the generated skill carries the same operator-facing hint.
    argument_hint = frontmatter.get("argument-hint")
    if isinstance(argument_hint, list) and argument_hint:
        argument_hint = f"[{', '.join(str(item) for item in argument_hint)}]"
    if isinstance(argument_hint, str) and argument_hint.strip():
        new_fm["argument-hint"] = argument_hint.strip()

    if resource_name in EXPLICIT_INVOCATION_ONLY_COMMANDS:
        new_fm["disable-model-invocation"] = True

    yaml_str = yaml.dump(new_fm, default_flow_style=False, sort_keys=False).strip()
    return f"---\n{yaml_str}\n---\n\n{body}\n"


def is_convertible(
    resource_name: str,
    resource_type: Literal["command", "agent"],
    cli: str | None = None,
) -> bool:
    """
    Check if a resource should be converted (tier 1 or 2).

    Args:
        resource_name: Name of the resource
        resource_type: 'command' or 'agent'
        cli: Target CLI. When given, tier-3 commands listed in
            ``CLI_EXTRA_CONVERTIBLE_COMMANDS[cli]`` are also
            convertible (Copilot's Skill-tool wrapper rewrite). The
            default (``None``) preserves the original tier-only
            behavior (Gemini).

    Returns:
        True if convertible, False if skip
    """
    tier = get_tier(resource_name, resource_type)
    if tier in (1, 2):
        return True
    if cli is not None and resource_type == "command":
        return resource_name in CLI_EXTRA_CONVERTIBLE_COMMANDS.get(cli, frozenset())
    return False
