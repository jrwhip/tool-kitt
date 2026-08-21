"""Tests for ``wopr.tools._curator`` — pure staleness-classification logic.

No file I/O here; the file I/O + dry-run gating lives in
``learnings.curate_learnings``, covered separately in
``TestCurateLearnings`` (tests/test_learnings.py).
"""

from __future__ import annotations

from datetime import date
from pathlib import Path

from wopr.tools._curator import DEFAULT_STALE_AFTER_DAYS, plan_curation, render_entries
from wopr.tools._learnings_format import LearningEntry


def _entry(
    *,
    entry_id: str,
    entry_date: date | None,
    seed: bool = False,
    raw: str | None = None,
) -> LearningEntry:
    return LearningEntry(
        id=entry_id,
        raw=raw or f"## {entry_id}: Sample\n\nbody\n",
        source_path=Path("LEARNINGS.md"),
        entry_date=entry_date,
        project="test-project",
        stack=["spring-boot"],
        req_ids=[],
        seed=seed,
    )


class TestPlanCuration:
    def test_recent_entry_is_kept(self):
        entries = [_entry(entry_id="LRN-2026-07-01-a", entry_date=date(2026, 7, 1))]
        plan = plan_curation(entries, today=date(2026, 7, 15))
        assert plan.keep == entries
        assert plan.archive == []

    def test_old_entry_is_archived(self):
        old = _entry(entry_id="LRN-2024-01-01-a", entry_date=date(2024, 1, 1))
        plan = plan_curation([old], today=date(2026, 7, 15))
        assert plan.archive == [old]
        assert plan.keep == []

    def test_entry_exactly_at_cutoff_is_kept(self):
        today = date(2026, 7, 15)
        cutoff_date = today.fromordinal(today.toordinal() - DEFAULT_STALE_AFTER_DAYS)
        entry = _entry(entry_id="LRN-boundary-a", entry_date=cutoff_date)
        plan = plan_curation([entry], today=today)
        # cutoff = today - stale_after_days; entry_date == cutoff is NOT < cutoff.
        assert entry in plan.keep

    def test_seed_entry_never_archived_regardless_of_age(self):
        ancient_seed = _entry(entry_id="LRN-2020-01-01-a", entry_date=date(2020, 1, 1), seed=True)
        plan = plan_curation([ancient_seed], today=date(2026, 7, 15))
        assert plan.keep == [ancient_seed]
        assert plan.archive == []

    def test_entry_with_no_date_is_kept_and_flagged(self):
        undated = _entry(entry_id="LRN-undated-a", entry_date=None)
        plan = plan_curation([undated], today=date(2026, 7, 15))
        assert plan.keep == [undated]
        assert plan.skipped_no_date == [undated]
        assert plan.archive == []

    def test_custom_stale_after_days(self):
        entry = _entry(entry_id="LRN-2026-06-01-a", entry_date=date(2026, 6, 1))
        # 45 days before "today" -- stale at a 30-day threshold, not at 365.
        plan_30 = plan_curation([entry], today=date(2026, 7, 15), stale_after_days=30)
        plan_365 = plan_curation([entry], today=date(2026, 7, 15), stale_after_days=365)
        assert plan_30.archive == [entry]
        assert plan_365.keep == [entry]

    def test_mixed_batch_classifies_each_independently(self):
        recent = _entry(entry_id="LRN-2026-07-01-a", entry_date=date(2026, 7, 1))
        old = _entry(entry_id="LRN-2020-01-01-b", entry_date=date(2020, 1, 1))
        seed = _entry(entry_id="LRN-2019-01-01-c", entry_date=date(2019, 1, 1), seed=True)
        undated = _entry(entry_id="LRN-undated-d", entry_date=None)
        plan = plan_curation([recent, old, seed, undated], today=date(2026, 7, 15))
        assert plan.archive == [old]
        assert {e.id for e in plan.keep} == {
            "LRN-2026-07-01-a",
            "LRN-2019-01-01-c",
            "LRN-undated-d",
        }


class TestRenderEntries:
    def test_empty_list_renders_empty_string(self):
        assert render_entries([]) == ""

    def test_single_entry_renders_its_raw_content(self):
        entry = _entry(
            entry_id="LRN-2026-07-01-a",
            entry_date=date(2026, 7, 1),
            raw="## LRN-2026-07-01-a: Title\n\nbody\n",
        )
        assert render_entries([entry]) == "## LRN-2026-07-01-a: Title\n\nbody\n"

    def test_multiple_entries_blank_line_separated(self):
        a = _entry(entry_id="a", entry_date=date(2026, 1, 1), raw="## a: A\n\nbody-a\n")
        b = _entry(entry_id="b", entry_date=date(2026, 1, 1), raw="## b: B\n\nbody-b\n")
        rendered = render_entries([a, b])
        idx = rendered.index("## b:")
        assert rendered[idx - 2:idx] == "\n\n"
