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

import yaml
from .conversion_manifest import apply_path_replacements, get_tier


def parse_claude(content: str) -> dict:
    """
    Parse Claude format file (YAML frontmatter + body).

    Returns:
        dict with 'frontmatter' (parsed YAML dict) and 'body' (remaining content)
    """
    content = content.strip()

    # No frontmatter
    if not content.startswith('---'):
        return {'frontmatter': {}, 'body': content}

    # Find end of frontmatter
    rest = content[3:]  # Skip opening ---
    end_idx = rest.find('\n---')

    if end_idx == -1:
        # Malformed - no closing ---, treat as no frontmatter
        return {'frontmatter': {}, 'body': content}

    yaml_content = rest[:end_idx].strip()
    body = rest[end_idx + 4:].strip()  # Skip \n---

    # Parse YAML
    try:
        frontmatter = yaml.safe_load(yaml_content) or {}
    except yaml.YAMLError:
        frontmatter = {}

    return {'frontmatter': frontmatter, 'body': body}


def to_gemini_toml(content: str, resource_name: str = '') -> str:
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
    frontmatter = parsed['frontmatter']
    body = parsed['body']

    # Apply path replacements for tier 2 content
    tier = get_tier(resource_name, 'command') if resource_name else 1
    if tier == 2:
        body = apply_path_replacements(body, 'gemini')

    # Replace argument placeholder
    body = body.replace('$ARGUMENTS', '{{args}}')

    # Escape triple single quotes in body if present (for TOML literal strings)
    body = body.replace("'''", "\\'\\'\\'")

    # Build TOML
    lines = []

    if 'description' in frontmatter:
        desc = frontmatter['description']
        # Apply path replacements to description too
        if tier == 2:
            desc = apply_path_replacements(desc, 'gemini')
        # Escape quotes in description
        desc = desc.replace('"', '\\"')
        lines.append(f'description = "{desc}"')

    # Use literal strings (''') to avoid escape processing for backslashes
    lines.append(f"prompt = '''\n{body}\n'''")

    return '\n'.join(lines)


def to_copilot_agent(content: str, resource_name: str = '') -> str:
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
    frontmatter = parsed['frontmatter']
    body = parsed['body']

    # Apply path replacements for tier 2 content
    tier = get_tier(resource_name, 'agent') if resource_name else 1
    if tier == 2:
        body = apply_path_replacements(body, 'copilot')

    # Tool mapping: Claude → Copilot
    tool_map = {
        'Read': 'read',
        'Write': 'edit',
        'Edit': 'edit',
        'Grep': 'search',
        'Glob': 'search',
        'Bash': 'shell',
        'Task': 'custom-agent',
    }

    # Build new frontmatter
    new_fm = {}

    if 'name' in frontmatter:
        new_fm['name'] = frontmatter['name']

    if 'description' in frontmatter:
        desc = frontmatter['description']
        # Apply path replacements to description too
        if tier == 2:
            desc = apply_path_replacements(desc, 'copilot')
        new_fm['description'] = desc

    # Map tools if present
    if 'tools' in frontmatter:
        claude_tools = frontmatter['tools']
        if isinstance(claude_tools, str):
            claude_tools = [t.strip() for t in claude_tools.split(',')]

        copilot_tools = set()
        for tool in claude_tools:
            mapped = tool_map.get(tool, tool.lower())
            copilot_tools.add(mapped)

        if copilot_tools:
            new_fm['tools'] = sorted(list(copilot_tools))

    # Build output
    if new_fm:
        yaml_str = yaml.dump(new_fm, default_flow_style=False, sort_keys=False).strip()
        return f"---\n{yaml_str}\n---\n\n{body}"
    else:
        return body


def is_convertible(resource_name: str, resource_type: str) -> bool:
    """
    Check if a resource should be converted (tier 1 or 2).

    Args:
        resource_name: Name of the resource
        resource_type: 'command' or 'agent'

    Returns:
        True if convertible (tier 1 or 2), False if skip (tier 3)
    """
    tier = get_tier(resource_name, resource_type)
    return tier in (1, 2)
