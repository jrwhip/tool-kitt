"""Pack-template read tools for the WOPR MCP server.

Crew-role agents (and any future pack consumer) need access to
shipped templates at runtime: ``implementation-tracking.template.md``,
``extracted-requirements.template.md``, ``frontend-handoff-contract
.template.md``, the per-stack spec stubs under ``templates/by-stack/``.

Before this module, agents that needed a template would brute-force
the filesystem with ``find`` because the role-agent definitions never
told them where pack content lived. The fallback search ran ``find /``
in extreme cases. Hundreds of thousands of stat calls per crew run
in the worst case, all to locate a file at a path the MCP server
already knows.

This module exposes pack templates the way the rest of WOPR exposes
shared resources. ``get_shared_skill`` / ``get_shared_command`` /
``get_shared_context`` already follow this pattern for the workspace-
visible catalog; ``get_pack_template`` mirrors it for the catalog's
``templates/`` subdirectories.

Two MCP tools:

* ``get_pack_template(pack, name)`` returns template contents. Resolves
  paths server-side via :func:`resolve_data_path`, which checks the
  repo's ``catalog/<pack>/templates/`` first and the installed
  package's ``resources/<pack>/templates/`` as fallback. The agent
  never needs to know the WOPR install root.
* ``list_pack_templates(pack)`` returns the inventory of template
  files each pack ships. Useful for diagnostics and for agents that
  want to enumerate before reading.

Read-only by design. The write-side stub generators live alongside
``write_spec_stubs`` in :mod:`.wopr_yml` because they need the same
detection-aware path resolution.
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING

from ._data_paths import candidate_data_paths, resolve_data_path

if TYPE_CHECKING:
    from mcp.server.fastmcp import FastMCP


# ---------------------------------------------------------------------------
# Public: get_pack_template
# ---------------------------------------------------------------------------


def _validate_pack_and_name(pack: str, name: str) -> str | None:
    """Return an ``Error:`` string if the inputs are unsafe, else None.

    Pack and template names must be plain identifiers. Path separators
    and ``..`` segments are rejected so a caller cannot escape the
    pack's templates directory.
    """
    if not pack:
        return "Error: pack is required."
    if not name:
        return "Error: name is required."
    for label, value in (("pack", pack), ("name", name)):
        if "/" in value or "\\" in value or ".." in value:
            return (
                f"Error: {label} {value!r} must be a plain name, no path "
                "separators or `..` segments."
            )
    return None


def get_pack_template(pack: str, name: str) -> str:
    """Return the contents of ``<pack>/templates/<name>``.

    Args:
        pack: Pack name (e.g., ``"crew"``, ``"legacy-migration"``).
        name: Template filename (e.g., ``"implementation-tracking
            .template.md"``). Must include the file extension.

    Returns:
        Template contents as a UTF-8 string on success. On any failure
        (unknown pack, missing template, read error, traversal attempt)
        returns a string beginning with ``Error:``. Read-only; no
        filesystem writes.

    Agents that need a pack template should call this tool rather than
    filesystem-walking for the file. The MCP server already knows the
    install root; agents do not.
    """
    err = _validate_pack_and_name(pack, name)
    if err is not None:
        return err

    resolved = resolve_data_path(pack, "templates", name)
    if resolved is None:
        return (
            f"Error: template {name!r} not found in pack {pack!r}. "
            "Use `list_pack_templates` to enumerate available templates."
        )
    if not resolved.is_file():
        return (
            f"Error: {resolved} exists but is not a regular file."
        )

    try:
        return resolved.read_text(encoding="utf-8")
    except OSError as e:
        return f"Error: failed to read {resolved}: {e}"


# ---------------------------------------------------------------------------
# Public: list_pack_templates
# ---------------------------------------------------------------------------


def list_pack_templates(pack: str) -> str:
    """Enumerate the templates a pack ships.

    Args:
        pack: Pack name (e.g., ``"crew"``, ``"legacy-migration"``).

    Returns:
        JSON-encoded object:

            {
              "pack": str,
              "templates_dir": str,
              "templates": [
                {"name": str, "path": str},
                ...
              ]
            }

        On failure (unknown pack, missing templates dir) returns a
        string beginning with ``Error:``. Read-only.

    The ``path`` field is the resolved absolute path. Useful for the
    caller's audit log; agents that want the contents should call
    :func:`get_pack_template` instead of opening the file directly.

    Sub-directories under ``templates/`` (e.g., ``templates/by-stack/``)
    are NOT recursed into. The flat top-level template files are what
    crew-pack consumers actually need; per-stack stubs are
    discovered via :func:`write_spec_stubs` not by listing.
    """
    if not pack:
        return "Error: pack is required."
    if "/" in pack or "\\" in pack or ".." in pack:
        return (
            f"Error: pack {pack!r} must be a plain name, no path "
            "separators or `..` segments."
        )

    templates_dir = resolve_data_path(pack, "templates")
    if templates_dir is None or not templates_dir.is_dir():
        candidates = candidate_data_paths(pack, "templates")
        return (
            f"Error: templates directory not found for pack {pack!r}. "
            f"Checked: {[str(c) for c in candidates]}"
        )

    templates: list[dict[str, str]] = []
    for entry in sorted(templates_dir.iterdir()):
        if entry.is_file():
            templates.append({"name": entry.name, "path": str(entry)})

    return json.dumps(
        {
            "pack": pack,
            "templates_dir": str(templates_dir),
            "templates": templates,
        },
        indent=2,
    )


# ---------------------------------------------------------------------------
# Registration
# ---------------------------------------------------------------------------


def register(mcp: FastMCP) -> None:
    """Register the pack-template MCP tools with the WOPR server."""
    mcp.tool()(get_pack_template)
    mcp.tool()(list_pack_templates)
