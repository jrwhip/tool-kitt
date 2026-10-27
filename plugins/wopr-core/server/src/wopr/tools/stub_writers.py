"""Stub writers for pack-shipped templates.

Each writer copies a single pack template into a project at a path
declared by the project's ``wopr.yml``, with a sensible default when
the yml does not declare one. Same atomic-write + refuse-overwrite
semantics as :func:`tools.wopr_yml.write_spec_stubs`. Crew agents
that need these documents should never need to filesystem-search;
``/wopr-init-project`` calls these writers, and the orchestrator can
call them mid-crew if a project surfaces a missing-stub blocker.

Split out of :mod:`tools.wopr_yml` so the ``wopr.yml`` generator
module stops carrying three unrelated concerns (yml generation, spec
stubs, pack-template stubs). The generator is the authority for the
yml format; the spec stubs are the per-stack spec-templating tool;
the pack-template stubs (this module) are general-purpose template
landers that read the project's existing yml to decide where each
template should land. The three are operationally distinct.

A third writer, ``write_extracted_requirements_stub``, landed the
legacy-migration pack's template. That pack does not cross over, so
neither did the writer.
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Any

import yaml

from .._atomic_write import atomic_write_text
from ._data_paths import resolve_data_path

if TYPE_CHECKING:
    from mcp.server.fastmcp import FastMCP


def _read_project_wopr_yml(target_dir: Path) -> dict[str, Any] | str:
    """Read `<target_dir>/wopr.yml`. Returns the parsed mapping or an error string.

    Success returns the parsed mapping (a ``dict``). Failure returns a
    string beginning with ``Error:``. Callers narrow with ``isinstance``;
    no ``assert`` is required because the return type is a discriminated
    union, not a pair of optionals smuggling a "exactly one is set"
    invariant the type checker cannot see.
    """
    yml_path = target_dir / "wopr.yml"
    if not yml_path.is_file():
        return (
            f"Error: project wopr.yml not found at {yml_path}. "
            "Run /wopr-create-yml first."
        )
    try:
        data = yaml.safe_load(yml_path.read_text(encoding="utf-8")) or {}
    except (OSError, yaml.YAMLError) as e:
        return f"Error: failed to read or parse {yml_path}: {e}"
    if not isinstance(data, dict):
        return f"Error: {yml_path} must contain a YAML mapping at the root."
    return data


def _legacy_field(wopr_yml: dict[str, Any], key: str) -> str | None:
    """Return `legacy-migration.<key>` from the yml if present, else None."""
    section = wopr_yml.get("legacy-migration")
    if not isinstance(section, dict):
        return None
    value = section.get(key)
    return value if isinstance(value, str) and value.strip() else None


def _write_pack_template(
    target_dir: str,
    pack: str,
    template_name: str,
    destination: str,
    overwrite: bool,
) -> str:
    """Shared stub-writer body. Reads ``<pack>/templates/<template_name>``
    from the pack catalog and writes it to ``<target_dir>/<destination>``
    atomically. Refuses to overwrite by default.

    Unlike :func:`tools.wopr_yml.write_wopr_yml`, this function DOES
    create intermediate directories for ``destination``. The contrast
    is intentional: ``write_wopr_yml`` writes a file at the project
    root (which must already exist; missing project root means the
    operator typo'd the path), while the stub writers write files at
    operator-declared sub-paths inside the project (where the leaf
    directory may not exist by design, e.g. ``docs/`` for projects
    that keep tracking documents under ``docs/``).
    """
    if not target_dir:
        return "Error: target_dir is required."
    dest_dir = Path(target_dir).expanduser()
    if not dest_dir.is_absolute():
        return f"Error: target_dir {target_dir!r} is not absolute."
    dest_dir = dest_dir.resolve()
    if not dest_dir.is_dir():
        return f"Error: target directory does not exist: {dest_dir}"

    src = resolve_data_path(pack, "templates", template_name)
    if src is None or not src.is_file():
        return (
            f"Error: pack template {pack}/{template_name} not found. "
            "Use list_pack_templates(pack) to enumerate."
        )
    try:
        content = src.read_text(encoding="utf-8")
    except OSError as e:
        return f"Error: failed to read {src}: {e}"

    dst = dest_dir / destination
    if dst.exists() and not overwrite:
        return (
            f"Error: {dst} already exists. Pass overwrite=True to replace it "
            "(or delete it and re-run)."
        )
    try:
        dst.parent.mkdir(parents=True, exist_ok=True)
    except OSError as e:
        return f"Error: failed to create {dst.parent}: {e}"
    try:
        atomic_write_text(dst, content)
    except OSError as e:
        return f"Error: failed to write {dst}: {e}"

    return f"Wrote {dst}"


def write_tracking_doc_stub(target_dir: str, overwrite: bool = False) -> str:
    """Drop the crew pack's implementation-tracking template into the project.

    Destination path comes from the project's
    ``legacy-migration.tracking_doc`` (when declared in ``wopr.yml``);
    otherwise falls back to ``implementation-tracking.md`` at the
    target root. Atomic write; refuses to overwrite by default.

    Args:
        target_dir: Absolute path of the project directory (the one
            containing ``wopr.yml``).
        overwrite: When ``False`` (default), refuses to overwrite an
            existing destination file.

    Returns:
        ``Wrote <path>`` on success, ``Error: ...`` on failure.
    """
    if not target_dir:
        return "Error: target_dir is required."
    target = Path(target_dir).expanduser()
    if not target.is_absolute():
        return f"Error: target_dir {target_dir!r} is not absolute."
    target = target.resolve()
    result = _read_project_wopr_yml(target)
    if isinstance(result, str):
        return result
    destination = _legacy_field(result, "tracking_doc") or "implementation-tracking.md"
    return _write_pack_template(
        target_dir=str(target),
        pack="crew",
        template_name="implementation-tracking.template.md",
        destination=destination,
        overwrite=overwrite,
    )


def write_handoff_contract_stub(target_dir: str, overwrite: bool = False) -> str:
    """Drop the crew pack's frontend-handoff-contract template into the project.

    Destination path comes from the project's
    ``legacy-migration.handoff_contract`` (when declared in
    ``wopr.yml``); otherwise falls back to
    ``frontend-handoff-contract.md`` at the target root.

    Use this for backend-producer projects that drive a frontend track.
    Pure-frontend projects consume the handoff contract from the
    backend side; they do not get their own.

    Args:
        target_dir: Absolute path of the project directory.
        overwrite: When ``False`` (default), refuses to overwrite.

    Returns:
        ``Wrote <path>`` on success, ``Error: ...`` on failure.
    """
    if not target_dir:
        return "Error: target_dir is required."
    target = Path(target_dir).expanduser()
    if not target.is_absolute():
        return f"Error: target_dir {target_dir!r} is not absolute."
    target = target.resolve()
    result = _read_project_wopr_yml(target)
    if isinstance(result, str):
        return result
    destination = (
        _legacy_field(result, "handoff_contract") or "frontend-handoff-contract.md"
    )
    return _write_pack_template(
        target_dir=str(target),
        pack="crew",
        template_name="frontend-handoff-contract.template.md",
        destination=destination,
        overwrite=overwrite,
    )


def register(mcp: FastMCP) -> None:
    """Register stub-writer tools with the WOPR MCP server."""
    mcp.tool()(write_tracking_doc_stub)
    mcp.tool()(write_handoff_contract_stub)
