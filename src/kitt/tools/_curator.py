"""Deterministic staleness pruning for a ``LEARNINGS.md`` corpus.

Named after Hermes Agent's curator (``agent/curator.py`` in
NousResearch/hermes-agent), but scoped to only the part of that design
worth porting here: the **deterministic, no-LLM inactivity pass**
(``apply_automatic_transitions``), which runs by default. Hermes's LLM
"umbrella-building" consolidation pass is opt-in and off by default there
(``DEFAULT_CONSOLIDATE = False``) — deliberately not ported at all. That
pass rewrites/merges entry *content*, which needs a working agent in the
loop to judge semantic overlap; a pure Python module can't do that
responsibly, and bolting an ungated LLM rewrite onto a corpus meant to
stay human/auditor-authored would trade one problem for a worse one.

What this module does, matching Hermes's safety invariants:
  - Never deletes. Stale entries are archived (moved to a sibling file),
    never destroyed. Archiving is the maximum action.
  - Seed entries (``seed: true``) are never touched, same as pinned
    skills bypass all auto-transitions in Hermes's curator.
  - Entries with no parseable date are left alone — absence of a
    judgeable signal is not evidence of staleness.
  - Pure functions here; the caller (``learnings.curate_learnings``)
    owns all file I/O, dry-run gating, and the atomic write.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta

from ._learnings_format import LearningEntry

DEFAULT_STALE_AFTER_DAYS = 365


@dataclass(frozen=True)
class CurationPlan:
    keep: list[LearningEntry]
    archive: list[LearningEntry]
    skipped_no_date: list[LearningEntry]


def plan_curation(
    entries: list[LearningEntry],
    *,
    today: date,
    stale_after_days: int = DEFAULT_STALE_AFTER_DAYS,
) -> CurationPlan:
    """Classify entries into keep / archive / skipped-no-date. Pure, no I/O.

    An entry archives only when all of:
      - ``seed`` is False (seed entries never age out — they're curated,
        maintainer-authored, exempt from the recency cutoff elsewhere too).
      - ``origin`` is not ``human`` (a person wrote it down deliberately;
        automatic pruning must not decide it stopped mattering — same
        protection seed entries get, for the same reason).
      - ``entry_date`` is present (unparseable/missing date -> keep,
        conservative default rather than guessing).
      - ``today - entry_date > stale_after_days``.
    """
    cutoff = today - timedelta(days=stale_after_days)
    keep: list[LearningEntry] = []
    archive: list[LearningEntry] = []
    skipped_no_date: list[LearningEntry] = []

    for entry in entries:
        if entry.seed:
            keep.append(entry)
            continue
        # Human-authored entries are exempt from automatic transitions,
        # mirroring the seed protection above. Comparison is
        # case-insensitive so `origin: Human` isn't silently unprotected.
        if entry.origin is not None and entry.origin.strip().lower() == "human":
            keep.append(entry)
            continue
        if entry.entry_date is None:
            skipped_no_date.append(entry)
            keep.append(entry)
            continue
        if entry.entry_date < cutoff:
            archive.append(entry)
        else:
            keep.append(entry)

    return CurationPlan(keep=keep, archive=archive, skipped_no_date=skipped_no_date)


def render_entries(entries: list[LearningEntry]) -> str:
    """Join entries' raw markdown back into a file body, blank-line separated."""
    pieces = [e.raw.rstrip() for e in entries]
    if not pieces:
        return ""
    return "\n\n".join(pieces).rstrip() + "\n"
