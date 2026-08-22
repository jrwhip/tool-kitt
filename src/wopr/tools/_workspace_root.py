"""Which directory owns a LEARNINGS corpus.

Distinct from :mod:`._workspace_target`, and the two are easy to
confuse:

- ``_workspace_target`` answers *what did the caller name, and is it
  usable?* It validates a caller-supplied ``target_workspace_path``
  (present, absolute, an existing directory) or derives one from the
  session.
- This module answers the next question: *given that directory, which
  enclosing directory owns the learnings corpus?* The answer is not
  always the directory the caller named.

The distinction exists because a repository is not required to put its
package root and its corpus in the same place.

Resolution algorithm
--------------------

One function, :func:`find_workspace_root`, is the single authority.
``seed_learnings``, ``append_learnings``, ``curate_learnings`` and the
read path all go through it, so a corpus that one tool can write is a
corpus every other tool can find.

Starting at ``start`` and walking UP parent by parent:

1. A directory is accepted as the workspace root when it contains
   **either** ``wopr.yml`` **or** ``LEARNINGS.md``. Two markers, not
   one: ``wopr.yml`` identifies a WOPR-configured package, and
   ``LEARNINGS.md`` identifies a directory that already owns a corpus.
2. **Nearest match wins.** The walk stops at the first directory that
   carries a marker, not the outermost one.
3. The walk stops at (and includes) the **git toplevel** when ``start``
   is inside a git repository, else at the filesystem root. A learnings
   corpus never belongs to a directory outside the repository being
   worked on.
4. When no marker is found before the boundary, resolution **fails**.
   It does not guess. Callers decide what a failure means; the learnings
   tools refuse to write rather than silently retargeting
   ``~/.wopr/LEARNINGS.md``.

The multi-package loop
----------------------

The rule that needs spelling out is what happens to a repository whose
``wopr.yml`` files live in subdirectories while the corpus lives at the
repo root::

    arcade/                 <- .git, LEARNINGS.md
      backend/wopr.yml
      frontend/wopr.yml

Before anything is seeded, ``arcade/`` carries no marker of its own:
``wopr.yml`` is one level down in each package, and there is no
``LEARNINGS.md`` yet. Resolution from ``arcade/`` therefore fails, and
``append_learnings`` says so instead of writing somewhere else.

``seed_learnings`` is what closes the loop. It writes
``<target>/LEARNINGS.md`` unconditionally, which *is* a marker, so after
seeding ``arcade/`` resolves to itself and every later append, search and
curate call agrees. Seeding a repo root is the supported way to declare
"the corpus lives here" for a multi-package repository.

Nearest-match-wins still applies inside that repo: a call targeting
``arcade/backend`` resolves to ``arcade/backend`` (it has its own
``wopr.yml``) and gets its own ``LEARNINGS.md``. Two packages that each
carry ``wopr.yml`` are two workspaces. To keep one shared corpus for the
whole repository, target the repo root.
"""

from __future__ import annotations

import contextlib
from dataclasses import dataclass
from pathlib import Path

from ._learnings_format import LEARNINGS_FILENAME

__all__ = [
    "GIT_DIR_NAME",
    "MARKER_FILENAMES",
    "WOPR_YML_FILENAME",
    "WorkspaceRoot",
    "find_git_toplevel",
    "find_workspace_root",
    "has_marker",
]

WOPR_YML_FILENAME = "wopr.yml"

#: A directory carrying either of these is a workspace root. Order is
#: presentation order in error messages only; neither marker outranks
#: the other during resolution.
MARKER_FILENAMES: tuple[str, ...] = (WOPR_YML_FILENAME, LEARNINGS_FILENAME)

GIT_DIR_NAME = ".git"


@dataclass(frozen=True)
class WorkspaceRoot:
    """The outcome of one :func:`find_workspace_root` walk.

    Carries the whole search, not just the answer, so a caller that has
    to report a failure can name every directory that was checked
    instead of emitting an unactionable "not found".
    """

    #: The resolved workspace root, or ``None`` when the walk found no
    #: marker before its boundary.
    root: Path | None

    #: Every directory examined, nearest first, including the one that
    #: matched (when there was a match).
    searched: tuple[Path, ...]

    #: The git toplevel that bounded the walk, or ``None`` when the
    #: start path is not inside a git repository.
    git_toplevel: Path | None

    @property
    def found(self) -> bool:
        """True when a workspace root was resolved."""
        return self.root is not None

    def explain(self) -> str:
        """One sentence naming the searched paths and the boundary.

        Written to be appended to an ``Error:`` string an agent reads,
        so it states where the search looked and where it stopped.
        """
        markers = " or ".join(MARKER_FILENAMES)
        looked = ", ".join(str(path) for path in self.searched)
        if self.git_toplevel is not None:
            boundary = f"the git toplevel {self.git_toplevel}"
        else:
            boundary = "the filesystem root"
        return (
            f"No {markers} was found in any of: {looked} "
            f"(the search walked up from the target and stopped at {boundary})."
        )


def has_marker(directory: Path) -> bool:
    """True when ``directory`` carries a workspace-root marker."""
    return any((directory / name).exists() for name in MARKER_FILENAMES)


def find_git_toplevel(start: Path) -> Path | None:
    """Return the nearest ancestor of ``start`` containing ``.git``.

    Detected by walking for the ``.git`` entry rather than shelling out
    to ``git rev-parse --show-toplevel``: no subprocess on a path that
    runs on every append, no dependency on a ``git`` binary being
    installed, and the same answer for the shapes WOPR cares about.
    ``.git`` is matched as either a directory (an ordinary clone) or a
    file (a linked worktree or a submodule), which is why the check is
    ``exists()`` rather than ``is_dir()``.
    """
    for candidate in (start, *start.parents):
        if (candidate / GIT_DIR_NAME).exists():
            return candidate
    return None


def find_workspace_root(start: Path) -> WorkspaceRoot:
    """Resolve the workspace root that owns ``start``'s learnings corpus.

    See the module docstring for the algorithm and for the
    multi-package repository loop this implements.

    Args:
        start: The directory to resolve from. Expanded and resolved;
            it does not have to exist (a non-existent path simply has
            no markers and the walk continues into its parents).

    Returns:
        A :class:`WorkspaceRoot`. Check ``.found`` before using
        ``.root``; on failure ``.explain()`` names every path searched.
    """
    start = Path(start).expanduser()
    # Resolution can fail on a broken symlink chain or a permission error
    # mid-path. An unresolved path still walks correctly; it just may not
    # be normalized, so the failure is not worth propagating.
    with contextlib.suppress(OSError):
        start = start.resolve()

    boundary = find_git_toplevel(start)

    searched: list[Path] = []
    for candidate in (start, *start.parents):
        searched.append(candidate)
        if has_marker(candidate):
            return WorkspaceRoot(
                root=candidate, searched=tuple(searched), git_toplevel=boundary
            )
        if boundary is not None and candidate == boundary:
            break

    return WorkspaceRoot(root=None, searched=tuple(searched), git_toplevel=boundary)
