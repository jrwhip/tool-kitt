"""Shared helpers for resolving a target path against a ``detect_stack`` profile.

Two tool modules (``wopr_yml`` and ``claude_md``) take ``(detection,
target_path)`` and need to:

1. Normalize the operator-supplied path (``./apps/example-app`` and
   ``apps/example-app/`` both mean the same thing).
2. Locate the matching :class:`StackProfile` inside the detection.
3. Derive a kebab-case ASCII slug and a human-readable title from the
   target's basename.

Both modules previously carried identical copies of these helpers,
which is the duplication finding the [TICKET-ID] audit flagged. Pulled
into this private shared module so future edits land in one place.

Private import name (leading underscore) because this is not part of
WOPR's MCP-tool surface; only the generator modules call it.
"""

from __future__ import annotations

import re
import unicodedata
from pathlib import Path
from typing import Any


def normalize_target_path(target_path: str) -> str:
    """Collapse ``.``, ``./``, and trailing slashes to a canonical form.

    Returns ``"."`` for the workspace root (any of ``""``, ``"."``,
    ``"./"`` map to it). Strips a leading ``"./"`` and trailing ``/``
    so ``"./apps/example-app/"`` and ``"apps/example-app"`` produce the
    same key. Whitespace at either end is also stripped.

    No path-traversal validation: that is the caller's job at the
    workspace-resolution boundary. This helper is the spelling
    normalizer only.
    """
    stripped = target_path.strip().rstrip("/")
    if stripped in ("", ".", "./"):
        return "."
    if stripped.startswith("./"):
        stripped = stripped[2:]
    return stripped


def find_profile(
    detection: dict[str, Any], target_path: str
) -> dict[str, Any] | None:
    """Locate the StackProfile dict inside ``detection`` matching ``target_path``.

    Returns ``None`` when no target matches, or when every matching
    entry is malformed (not a dict). The detection JSON's ``targets``
    field may be missing, empty, or contain non-dict entries (a
    corrupt or hand-edited detection file). The isinstance check
    runs BEFORE ``.get()`` so a string or null entry no longer
    crashes the lookup.
    """
    norm = normalize_target_path(target_path)
    for profile in detection.get("targets") or []:
        if not isinstance(profile, dict):
            continue
        if normalize_target_path(profile.get("target_path") or "") == norm:
            return profile
    return None


def slug_from_target(target_path: str, workspace_path: str) -> str:
    """Derive a kebab-case ASCII slug from the target's basename.

    The wopr.yml schema defines ``project.slug`` as a kebab-case ASCII
    identifier; Unicode characters in directory names are normalized
    to their closest ASCII equivalents via NFKD before non-alphanumerics
    are collapsed to hyphens. ``apps/café`` becomes ``cafe``, not
    ``caf`` (a prior regex-only strip silently dropped the accented
    glyph and shortened the slug).

    Falls back to the workspace root's basename when ``target_path``
    refers to the workspace root itself. Falls back to ``"project"``
    when both produce an empty slug.
    """
    norm = normalize_target_path(target_path)
    candidate = Path(workspace_path).name if norm == "." else Path(norm).name
    ascii_folded = (
        unicodedata.normalize("NFKD", candidate)
        .encode("ascii", "ignore")
        .decode("ascii")
    )
    slug = re.sub(r"[^a-zA-Z0-9]+", "-", ascii_folded).strip("-").lower()
    return slug or "project"


def name_from_slug(slug: str) -> str:
    """Title-case a kebab slug for the human-readable project name."""
    return " ".join(part.capitalize() for part in slug.split("-")) or "Project"
