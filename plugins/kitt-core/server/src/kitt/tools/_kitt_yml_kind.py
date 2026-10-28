"""Which kind of ``kitt.yml`` a file is: a project or a workspace.

Two shapes share the one filename:

- A **project** ``kitt.yml`` declares a top-level ``project`` block. It
  sits at the root of a single codebase and is what every crew agent,
  stub writer, and spec generator reads.
- A **workspace** ``kitt.yml`` declares a top-level ``workspace`` block
  and no ``project`` block. It sits at the root of a container directory
  whose children are each their own project (often each its own git
  repository) and names those children as members.

Readers tell the two apart by content, never by location, so one
classifier owns the rules and every reader (``write_kitt_yml``, the
stub writers, ``detect_stack``, ``_workspace_root``, ``server``) calls
it rather than re-deriving them. This module deliberately imports
nothing from :mod:`.stack_detect`: ``_workspace_root`` is on the
learnings import path and must stay light.

Private import name (leading underscore) because this is not part of
KITT's MCP-tool surface.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path, PurePosixPath, PureWindowsPath
from typing import Any, Final, Literal

import yaml

from ..product import CONFIG_FILENAME, LOGGER_NAME
from ._learnings_format import LEARNINGS_FILENAME
from ._target_paths import slug_from_target

logger = logging.getLogger(LOGGER_NAME)

__all__ = [
    "KIND_INVALID",
    "KIND_PROJECT",
    "KIND_WORKSPACE",
    "WORKSPACE_ROLES",
    "DescribedMember",
    "KittYmlInfo",
    "KittYmlKind",
    "WorkspaceMember",
    "WorkspaceSection",
    "classify_kitt_yml_data",
    "describe_members",
    "find_enclosing_workspace",
    "kitt_yml_kind",
    "load_kitt_yml",
]

#: The three answers the classifier can give. Every reader branches on
#: this, so it is a ``Literal`` rather than a bare ``str``.
KittYmlKind = Literal["project", "workspace", "invalid"]

KIND_PROJECT: Final = "project"
KIND_WORKSPACE: Final = "workspace"
KIND_INVALID: Final = "invalid"

#: The roles a workspace member may declare. Extend by appending here
#: and in the schema document; the server only validates and passes
#: the value through, the catalog is what gives each role meaning.
WORKSPACE_ROLES: tuple[str, ...] = ("backend", "frontend", "tests", "other")

DEFAULT_ROLE = "other"

#: Sections that only mean something in a project file. Beside a
#: ``workspace`` block they are ignored with a warning rather than
#: rejected, so a hand-edited root file degrades to "noisy" instead of
#: "bricks every tool".
_PROJECT_ONLY_SECTIONS: tuple[str, ...] = (
    "specs",
    "api_contract",
    "openapi",
    "legacy-migration",
    "requirements",
)


@dataclass(frozen=True)
class WorkspaceMember:
    """One entry of ``workspace.projects``."""

    #: Normalized path relative to the workspace root (POSIX separators).
    path: str
    #: Kebab-case identifier; defaults to the path's basename.
    slug: str
    #: One of :data:`WORKSPACE_ROLES`.
    role: str


@dataclass(frozen=True)
class WorkspaceSection:
    """The validated ``workspace`` block of a workspace ``kitt.yml``."""

    slug: str
    name: str | None
    members: tuple[WorkspaceMember, ...]

    def member_dirs(self, root: Path) -> list[tuple[WorkspaceMember, Path]]:
        """Each member paired with its absolute directory under ``root``.

        No existence or escape filtering here; callers that need those
        checks use :func:`describe_members`, which reports them.
        """
        return [(member, root / member.path) for member in self.members]


@dataclass(frozen=True)
class KittYmlInfo:
    """What a ``kitt.yml`` turned out to be."""

    #: :data:`KIND_PROJECT`, :data:`KIND_WORKSPACE`, or :data:`KIND_INVALID`.
    kind: KittYmlKind
    #: The parsed mapping, or ``None`` when the content was not a mapping.
    data: dict[str, Any] | None
    #: Why the file is invalid; ``None`` for the two valid kinds.
    error: str | None
    #: The validated workspace block; set only for :data:`KIND_WORKSPACE`.
    workspace: WorkspaceSection | None
    #: Non-fatal problems the operator should see.
    warnings: tuple[str, ...] = field(default=())

    @property
    def is_workspace(self) -> bool:
        return self.kind == KIND_WORKSPACE

    @property
    def is_project(self) -> bool:
        return self.kind == KIND_PROJECT


def _invalid(data: dict[str, Any] | None, error: str) -> KittYmlInfo:
    return KittYmlInfo(kind=KIND_INVALID, data=data, error=error, workspace=None)


def _validate_member(
    raw: Any, index: int, seen_paths: set[str]
) -> WorkspaceMember | str:
    """Return a :class:`WorkspaceMember` or an error string."""
    where = f"workspace.projects[{index}]"
    if not isinstance(raw, dict):
        return f"{where} must be a mapping with a `path` key."

    path_value = raw.get("path")
    if not isinstance(path_value, str) or not path_value.strip():
        return f"{where}.path is required and must be a non-empty string."
    # Normalize BEFORE judging. A Windows-style ``\\foo`` or ``C:\\foo`` is
    # absolute whichever host parses it, and ``././x``, ``x//y``, ``x/``
    # all name the same directory as ``x``/``x/y``; pathlib collapses
    # those so the duplicate check compares one spelling.
    posix_spelling = path_value.strip().replace("\\", "/")
    if (
        PurePosixPath(posix_spelling).is_absolute()
        or PureWindowsPath(path_value.strip()).is_absolute()
    ):
        return f"{where}.path `{path_value}` is absolute; member paths are relative."
    normalized = PurePosixPath(posix_spelling).as_posix()
    if normalized in (".", ""):
        return f"{where}.path `{path_value}` names the workspace root itself."
    if ".." in PurePosixPath(normalized).parts:
        return f"{where}.path `{path_value}` contains `..`; members live under the root."
    if normalized in seen_paths:
        return f"{where}.path `{path_value}` is declared more than once."
    seen_paths.add(normalized)

    slug_value = raw.get("slug")
    if slug_value is None:
        slug = slug_from_target(normalized, "")
    elif isinstance(slug_value, str) and slug_value.strip():
        slug = slug_value.strip()
    else:
        return f"{where}.slug must be a non-empty string when present."

    role_value = raw.get("role")
    if role_value is None:
        role = DEFAULT_ROLE
    elif isinstance(role_value, str) and role_value in WORKSPACE_ROLES:
        role = role_value
    else:
        allowed = ", ".join(WORKSPACE_ROLES)
        return f"{where}.role `{role_value}` is not one of: {allowed}."

    return WorkspaceMember(path=normalized, slug=slug, role=role)


def _validate_workspace_block(raw: Any) -> WorkspaceSection | str:
    """Return a :class:`WorkspaceSection` or an error string."""
    if not isinstance(raw, dict):
        return "`workspace` must be a mapping."

    slug_value = raw.get("slug")
    if not isinstance(slug_value, str) or not slug_value.strip():
        return "workspace.slug is required and must be a non-empty string."

    name_value = raw.get("name")
    if name_value is not None and not isinstance(name_value, str):
        return "workspace.name must be a string when present."

    projects = raw.get("projects")
    if not isinstance(projects, list) or not projects:
        return "workspace.projects is required and must be a non-empty list."

    members: list[WorkspaceMember] = []
    seen: set[str] = set()
    for index, entry in enumerate(projects):
        outcome = _validate_member(entry, index, seen)
        if isinstance(outcome, str):
            return outcome
        members.append(outcome)

    return WorkspaceSection(
        slug=slug_value.strip(),
        name=name_value.strip() if isinstance(name_value, str) else None,
        members=tuple(members),
    )


def classify_kitt_yml_data(data: Any) -> KittYmlInfo:
    """Classify already-parsed ``kitt.yml`` content.

    Pure: every rule about what makes a file a project, a workspace, or
    neither lives here, and nothing here touches the filesystem.
    """
    if not isinstance(data, dict):
        got = type(data).__name__
        return _invalid(None, f"kitt.yml must be a YAML mapping at the root (got {got}).")

    has_project = "project" in data
    has_workspace = "workspace" in data

    if has_project and has_workspace:
        return _invalid(
            data,
            "kitt.yml declares both `project` and `workspace`; a file is one "
            "or the other.",
        )

    if has_workspace:
        outcome = _validate_workspace_block(data["workspace"])
        if isinstance(outcome, str):
            return _invalid(data, outcome)
        ignored = [key for key in _PROJECT_ONLY_SECTIONS if key in data]
        warnings = tuple(
            f"`{key}` is a project-only section and is ignored in a workspace kitt.yml."
            for key in ignored
        )
        return KittYmlInfo(
            kind=KIND_WORKSPACE,
            data=data,
            error=None,
            workspace=outcome,
            warnings=warnings,
        )

    if has_project:
        return KittYmlInfo(kind=KIND_PROJECT, data=data, error=None, workspace=None)

    return _invalid(
        data,
        "kitt.yml is missing the required `project` block (or a `workspace` "
        "block for a container root).",
    )


def load_kitt_yml(path: Path) -> KittYmlInfo | None:
    """Read and classify the ``kitt.yml`` at ``path``.

    Returns ``None`` when there is no file. A file that cannot be read
    or parsed is :data:`KIND_INVALID` with the reason in ``error``, so a
    caller can distinguish "absent" from "present but broken".
    """
    if not path.is_file():
        return None
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as e:
        return _invalid(None, f"cannot read {path}: {e}")
    try:
        data = yaml.safe_load(text)
    except yaml.YAMLError as e:
        return _invalid(None, f"cannot parse {path}: {e}")
    return classify_kitt_yml_data(data)


def kitt_yml_kind(directory: Path) -> KittYmlKind | None:
    """The kind of ``<directory>/kitt.yml``, or ``None`` when absent."""
    info = load_kitt_yml(directory / CONFIG_FILENAME)
    return None if info is None else info.kind


def find_enclosing_workspace(start: Path) -> tuple[Path, WorkspaceSection] | None:
    """The nearest ancestor of ``start`` carrying a workspace ``kitt.yml``.

    Walks ``start``'s parents (not ``start`` itself) up to the filesystem
    root and returns ``(directory, section)`` for the first one whose
    ``kitt.yml`` is workspace kind, or ``None``. Ancestors carrying a
    project-kind or invalid file are passed over. This deliberately
    ignores git boundaries: a member is its own repository, and the
    question here is precisely "which container above me declares me?".
    """
    for candidate in start.parents:
        info = load_kitt_yml(candidate / CONFIG_FILENAME)
        if info is not None and info.workspace is not None:
            return candidate, info.workspace
    return None


@dataclass(frozen=True)
class DescribedMember:
    """One declared member, cross-checked with disk.

    The one shape every tool reports a member in; ``detect_stack`` and
    ``get_workspace_info`` both serialize it through :meth:`to_json` so
    an agent reads an identical dict in either place.
    """

    path: str
    abs_path: Path
    slug: str
    role: str
    exists: bool
    has_kitt_yml: bool
    kitt_yml_kind: KittYmlKind | None
    has_learnings: bool

    def to_json(self) -> dict[str, Any]:
        return {
            "path": self.path,
            "abs_path": str(self.abs_path),
            "slug": self.slug,
            "role": self.role,
            "exists": self.exists,
            "has_kitt_yml": self.has_kitt_yml,
            "kitt_yml_kind": self.kitt_yml_kind,
            "has_learnings": self.has_learnings,
        }


def describe_members(root: Path, section: WorkspaceSection) -> list[DescribedMember]:
    """Every declared member with what disk says about it, in declared order.

    A member whose directory resolves outside ``root`` (a symlink
    pointing elsewhere) is skipped and logged; a workspace file must not
    be able to point tools at an unrelated directory.
    """
    try:
        resolved_root = root.resolve()
    except OSError:
        resolved_root = root

    described: list[DescribedMember] = []
    for member, member_dir in section.member_dirs(root):
        exists = member_dir.is_dir()
        if exists:
            try:
                resolved = member_dir.resolve()
            except OSError:
                resolved = member_dir
            if not resolved.is_relative_to(resolved_root):
                logger.warning(
                    "Workspace member %s resolves to %s, outside %s; skipped.",
                    member.path,
                    resolved,
                    resolved_root,
                )
                continue
        member_info = load_kitt_yml(member_dir / CONFIG_FILENAME) if exists else None
        described.append(
            DescribedMember(
                path=member.path,
                abs_path=member_dir,
                slug=member.slug,
                role=member.role,
                exists=exists,
                has_kitt_yml=member_info is not None,
                kitt_yml_kind=None if member_info is None else member_info.kind,
                has_learnings=exists and (member_dir / LEARNINGS_FILENAME).is_file(),
            )
        )
    return described
