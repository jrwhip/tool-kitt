"""Resolve catalog data files across the dev-tree and bundled installs.

Tool modules that ship curated content (recommendation tables, seed
LEARNINGS entries, per-stack spec templates) need to find that content
in two layouts:

1. The repo's ``catalog/`` directory, used during dev when the package
   is installed editable (``uv pip install -e .`` or ``pipx install
   --editable``). Edits to ``catalog/...`` show up without reinstall.
2. The bundled ``resources/`` directory inside the installed package,
   used when the package is installed normally (the build step copies
   ``catalog/`` into ``src/wopr/resources/``).

The path arithmetic to walk from ``__file__`` up to the repo root and
then into either ``catalog/`` or ``resources/`` was duplicated across
``doctor._candidate_recommendation_paths``,
``learnings._candidate_seed_paths``, and
``wopr_yml._select_stack_template_dir``. The [TICKET-ID] audit flagged
the duplication as a fragility risk: if the module layout ever
changes, all three modules need parallel surgery.

Single source of truth here. Callers describe the file or directory
they want as a sequence of path parts; this module checks the repo
location first, then the bundled location, returning whichever exists.
"""

from __future__ import annotations

from pathlib import Path

# Anchored once at module import; the math is exactly what the three
# tool modules previously inlined:
#
# * ``parent.parent.parent.parent`` walks from
#   ``.../src/wopr/tools/_data_paths.py`` up to the repo root.
# * ``parent.parent`` walks from the same file up to
#   ``.../src/wopr/``, where the bundled ``resources/`` tree
#   lives.
#
# Both are computed once. ``Path.resolve()`` is on ``__file__`` so a
# symlinked install (pipx) still points at the canonical source layout.
_HERE = Path(__file__).resolve()
_REPO_ROOT = _HERE.parent.parent.parent.parent
_PACKAGE_ROOT = _HERE.parent.parent


def candidate_data_paths(
    *parts: str,
    repo_subtree: str = "catalog",
    bundled_subtree: str = "resources",
) -> list[Path]:
    """Return the dev and bundled candidate paths for a data file.

    Always returns both candidates in order (repo first, bundled
    second), without filtering by existence. Callers that want only
    the first existing path should use :func:`resolve_data_path`.

    Args:
        *parts: Path components joined under the chosen subtree (e.g.
            ``"crew", "data", "doctor-recommendations.yaml"``).
        repo_subtree: Top-level dir under the repo root that holds
            the dev copy. Defaults to ``"catalog"``.
        bundled_subtree: Top-level dir under the package root that
            holds the install-time copy. Defaults to ``"resources"``.

    Returns:
        A list of two :class:`Path` objects: ``[repo_path,
        bundled_path]``. Neither is guaranteed to exist.
    """
    return [
        _REPO_ROOT.joinpath(repo_subtree, *parts),
        _PACKAGE_ROOT.joinpath(bundled_subtree, *parts),
    ]


def resolve_data_path(
    *parts: str,
    repo_subtree: str = "catalog",
    bundled_subtree: str = "resources",
) -> Path | None:
    """Return the first existing candidate path, or ``None`` if neither exists.

    Useful when the caller wants the file/dir directly without
    iterating over candidates themselves. When both candidates exist
    the repo one wins (the dev iteration story).

    Args:
        *parts: See :func:`candidate_data_paths`.
        repo_subtree: See :func:`candidate_data_paths`.
        bundled_subtree: See :func:`candidate_data_paths`.

    Returns:
        The first existing :class:`Path`, or ``None`` if neither
        candidate exists on disk.
    """
    for candidate in candidate_data_paths(
        *parts,
        repo_subtree=repo_subtree,
        bundled_subtree=bundled_subtree,
    ):
        if candidate.exists():
            return candidate
    return None
