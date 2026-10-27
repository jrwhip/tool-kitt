"""Idempotent ``.gitignore`` maintenance for WOPR-managed sidecar files.

The embeddings sidecar (``LEARNINGS.embeddings.npz``) is a machine-
specific binary that must NOT land in source control: the file is
~130KB to several MB of dense vectors keyed by the local embedding
model's version, and committing it produces noisy diffs and merge
conflicts on something every developer regenerates locally anyway.

WOPR generates the sidecar transparently whenever a search runs and
the markdown corpus has changed. The operator should never have to
think about it. This module makes sure the file is `.gitignore`-d
without the operator having to know it exists.

Idempotent: a fresh project gets a ``.gitignore`` with the entry; a
project that already gitignores the file is a no-op; a project that
already has a ``.gitignore`` for other reasons gets the entry
appended under a labelled WOPR section so the operator can see what
WOPR added and why.

Failures here are logged at WARNING and swallowed. The auditor's
append to LEARNINGS.md already succeeded; the gitignore not being
updated is recoverable on the next call and not worth bubbling an
error up to the caller.
"""

from __future__ import annotations

import logging
from pathlib import Path

from ..product import LOGGER_NAME
from ._embeddings import EMBEDDINGS_SIDECAR_FILENAME

logger = logging.getLogger(LOGGER_NAME)

# Section header used when WOPR creates a new ``.gitignore`` or appends
# entries to an existing one. Matched on read to detect whether a
# previous WOPR run already wrote the section, so the second call is
# a no-op rather than a duplicate append.
_WOPR_GITIGNORE_HEADER = "# WOPR (do not edit between markers)"
_WOPR_GITIGNORE_FOOTER = "# /WOPR"


def _gitignore_has_entry(text: str, entry: str) -> bool:
    """Return True if ``entry`` already appears as a stand-alone line in *text*.

    Tolerates leading ``/`` (anchored paths), trailing whitespace, and
    comment lines. Does NOT do glob matching; an entry like ``*.npz``
    in the gitignore would not be detected as covering
    ``LEARNINGS.embeddings.npz``, so WOPR would append the literal entry
    redundantly. The current corpus is too small for that to matter;
    revisit if a project actually carries an ``*.npz`` glob.
    """
    target = entry.strip().lstrip("/")
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if line.lstrip("/") == target:
            return True
    return False


def ensure_sidecar_gitignored(workspace: Path) -> None:
    """Make sure the workspace's ``.gitignore`` lists the embeddings sidecar.

    Workspace mode only. Called from
    :func:`learnings.append_learnings` and
    :func:`learnings.seed_learnings` after the first write to the
    workspace's LEARNINGS.md. Outside-workspace mode skips this
    helper entirely because there is no project repo to gitignore in
    (the global LEARNINGS.md and sidecar live under ``~/.wopr/``).

    Behavior:
    - If ``<workspace>/.gitignore`` does not exist, create it with a
      WOPR-labelled section containing the sidecar entry.
    - If the file exists but does not list the sidecar, append the
      WOPR-labelled section.
    - If the file already lists the sidecar (literal entry), no-op.

    All filesystem errors are logged at WARNING and swallowed.
    """
    gitignore = workspace / ".gitignore"
    entry = EMBEDDINGS_SIDECAR_FILENAME

    try:
        existing = gitignore.read_text(encoding="utf-8") if gitignore.exists() else ""
    except OSError as e:
        logger.warning(
            "Cannot read %s to check for embeddings-sidecar entry (%s); "
            "skipping .gitignore update. The sidecar may end up tracked "
            "by git if the operator commits without noticing.",
            gitignore,
            e,
        )
        return

    if _gitignore_has_entry(existing, entry):
        return

    section = (
        f"{_WOPR_GITIGNORE_HEADER}\n"
        f"{entry}\n"
        f"{_WOPR_GITIGNORE_FOOTER}\n"
    )

    if existing:
        # File exists; append the WOPR section with a leading blank
        # line so it sits visibly apart from the operator's content.
        new_text = existing
        if not new_text.endswith("\n"):
            new_text += "\n"
        new_text += "\n" + section
    else:
        # Fresh ``.gitignore``; the WOPR section is the entire file.
        new_text = section

    try:
        gitignore.write_text(new_text, encoding="utf-8")
    except OSError as e:
        logger.warning(
            "Cannot write %s to add embeddings-sidecar entry (%s); the "
            "sidecar may end up tracked by git if the operator commits "
            "without noticing.",
            gitignore,
            e,
        )
        return

    logger.info(
        "Added `%s` to %s. The embeddings sidecar is machine-specific "
        "and should not be committed.",
        entry,
        gitignore,
    )
