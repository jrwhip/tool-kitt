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
``learnings._candidate_seed_paths``, ``wopr_yml._select_stack_template_sources``,
and (at the time) a third copy in ``tools/doctor.py``, since cut along
with the rest of that module. The DEMO-123 audit flagged the
duplication as a fragility risk: if the module layout ever changes,
every copy needs parallel surgery.

3. The ``resources/`` directory of a Claude Code plugin install, at
   ``$WOPR_PLUGIN_ROOT/server/resources/``. ``wopr build-plugins``
   copies the runtime-relevant catalog subtrees there, and the
   generated ``.mcp.json`` sets ``WOPR_PLUGIN_ROOT`` for the server
   process. Neither of the two path-arithmetic candidates can find
   that layout: the bundled server lives at ``<plugin>/server/src/
   wopr/`` with its resources one level up and outside the package.

Single source of truth here. Callers describe the file or directory
they want as a sequence of path parts; this module checks the plugin
location (only when the env var says there is one), then the repo
location, then the bundled location, returning whichever exists.
"""

from __future__ import annotations

from pathlib import Path

from ..config import plugin_resources_root

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
    """Return the candidate paths for a data file, in resolution order.

    Returns the dev (repo) and bundled candidates always, without
    filtering by existence, and prepends the plugin-install candidate
    when ``WOPR_PLUGIN_ROOT`` is set. Callers that want only the first
    existing path should use :func:`resolve_data_path`.

    The plugin candidate goes first because it is the only one set
    explicitly by the environment: if a process was told where its
    plugin lives, that beats path arithmetic derived from
    ``__file__``. It costs nothing outside a plugin install, where the
    env var is unset and the list is exactly the historical two.

    Args:
        *parts: Path components joined under the chosen subtree (e.g.
            ``"crew", "data", "doctor-recommendations.yaml"``).
        repo_subtree: Top-level dir under the repo root that holds
            the dev copy. Defaults to ``"catalog"``.
        bundled_subtree: Top-level dir under the package root that
            holds the install-time copy. Defaults to ``"resources"``.

    Returns:
        ``[plugin_path?, repo_path, bundled_path]``. None is
        guaranteed to exist.
    """
    candidates: list[Path] = []
    plugin_resources = plugin_resources_root()
    if plugin_resources is not None:
        candidates.append(plugin_resources.joinpath(*parts))
    candidates.append(_REPO_ROOT.joinpath(repo_subtree, *parts))
    candidates.append(_PACKAGE_ROOT.joinpath(bundled_subtree, *parts))
    return candidates


def resolve_data_path(
    *parts: str,
    repo_subtree: str = "catalog",
    bundled_subtree: str = "resources",
) -> Path | None:
    """Return the first existing candidate path, or ``None`` if neither exists.

    Useful when the caller wants the file/dir directly without
    iterating over candidates themselves. When several candidates
    exist the explicit plugin one wins, then the repo one (the dev
    iteration story), then the bundled one.

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
