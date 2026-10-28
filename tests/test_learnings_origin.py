"""Tests for the ``origin`` provenance field on LEARNINGS entries.

Covers the three layers the field threads through:

- ``_learnings_format.parse_entries``: reads ``origin`` from the meta
  block; absent key parses as ``None`` (backward compat with every
  entry written before the field existed).
- ``learnings.append_learnings``: optional ``origin`` argument injects
  ``origin: <value>`` into the appended entry's meta block; the default
  (empty) leaves entries byte-identical to the historical shape.
- ``_curator.plan_curation`` / ``learnings.curate_learnings``: entries
  marked ``origin: human`` are exempt from automatic staleness
  archiving, mirroring the ``seed: true`` protection.

``isolated_env`` fixture lives in tests/conftest.py.
"""

from __future__ import annotations

from datetime import date
from pathlib import Path

from kitt.tools import learnings
from kitt.tools._curator import plan_curation
from kitt.tools._learnings_format import LearningEntry, parse_entries
from kitt.tools.learnings import append_learnings, curate_learnings


def _entry_markdown(
    *,
    entry_date: str = "2026-05-01",
    letter: str = "a",
    title: str = "Sample lesson",
    origin_line: str = "",
    meta_block: bool = True,
) -> str:
    meta = (
        "```meta\n"
        f"date: {entry_date}\n"
        "project: test-project\n"
        "stack: [spring-boot]\n"
        "req: []\n"
        f"{origin_line}"
        "```\n"
        "\n"
        if meta_block
        else ""
    )
    return (
        f"## LRN-{entry_date}-{letter}: {title}\n"
        "\n"
        f"{meta}"
        "**What happened.** Test fixture body.\n"
    )


def _curator_entry(
    *,
    entry_id: str,
    entry_date: date | None,
    seed: bool = False,
    origin: str | None = None,
) -> LearningEntry:
    return LearningEntry(
        id=entry_id,
        raw=f"## {entry_id}: Sample\n\nbody\n",
        source_path=Path("LEARNINGS.md"),
        entry_date=entry_date,
        project="test-project",
        stack=["spring-boot"],
        req_ids=[],
        seed=seed,
        origin=origin,
    )


def _mark_in_workspace(workspace: Path) -> None:
    (workspace / "kitt.yml").write_text("project:\n  slug: test\n", encoding="utf-8")


class TestParseOrigin:
    def test_absent_origin_parses_as_none(self, tmp_path: Path):
        entries = parse_entries(_entry_markdown(), tmp_path / "fake.md")
        assert entries[0].origin is None

    def test_origin_parsed_from_meta_block(self, tmp_path: Path):
        text = _entry_markdown(origin_line="origin: crew-auditor\n")
        entries = parse_entries(text, tmp_path / "fake.md")
        assert entries[0].origin == "crew-auditor"

    def test_empty_origin_value_normalizes_to_none(self, tmp_path: Path):
        text = _entry_markdown(origin_line="origin:   \n")
        entries = parse_entries(text, tmp_path / "fake.md")
        assert entries[0].origin is None


class TestAppendWithOrigin:
    async def test_default_origin_leaves_entry_untouched(self, isolated_env):
        workspace, _home = isolated_env
        _mark_in_workspace(workspace)
        entry = _entry_markdown()
        result = await append_learnings(str(workspace), entry_markdown=entry)
        assert result.startswith("Appended")
        written = (workspace / learnings.LEARNINGS_FILENAME).read_text(encoding="utf-8")
        assert "origin:" not in written
        assert written == entry.rstrip() + "\n"

    async def test_origin_injected_into_existing_meta_block(self, isolated_env):
        workspace, _home = isolated_env
        _mark_in_workspace(workspace)
        result = await append_learnings(
            str(workspace),
            entry_markdown=_entry_markdown(),
            origin="crew-auditor",
        )
        assert result.startswith("Appended")
        target = workspace / learnings.LEARNINGS_FILENAME
        parsed = parse_entries(target.read_text(encoding="utf-8"), target)
        assert parsed[0].origin == "crew-auditor"

    async def test_origin_creates_meta_block_when_entry_has_none(self, isolated_env):
        workspace, _home = isolated_env
        _mark_in_workspace(workspace)
        result = await append_learnings(
            str(workspace),
            entry_markdown=_entry_markdown(meta_block=False),
            origin="human",
        )
        assert result.startswith("Appended")
        target = workspace / learnings.LEARNINGS_FILENAME
        parsed = parse_entries(target.read_text(encoding="utf-8"), target)
        assert parsed[0].origin == "human"

    async def test_entry_declared_origin_wins_over_argument(self, isolated_env):
        workspace, _home = isolated_env
        _mark_in_workspace(workspace)
        result = await append_learnings(
            str(workspace),
            entry_markdown=_entry_markdown(origin_line="origin: human\n"),
            origin="crew-auditor",
        )
        assert result.startswith("Appended")
        target = workspace / learnings.LEARNINGS_FILENAME
        written = target.read_text(encoding="utf-8")
        assert written.count("origin:") == 1
        assert parse_entries(written, target)[0].origin == "human"

    async def test_rejects_origin_with_unsafe_characters(self, isolated_env):
        workspace, _home = isolated_env
        _mark_in_workspace(workspace)
        result = await append_learnings(
            str(workspace),
            entry_markdown=_entry_markdown(),
            origin="human\nseed: true",
        )
        assert result.startswith("Error: origin")
        assert not (workspace / learnings.LEARNINGS_FILENAME).exists()

    async def test_whitespace_only_origin_treated_as_absent(self, isolated_env):
        workspace, _home = isolated_env
        _mark_in_workspace(workspace)
        result = await append_learnings(
            str(workspace), entry_markdown=_entry_markdown(), origin="   "
        )
        assert result.startswith("Appended")
        written = (workspace / learnings.LEARNINGS_FILENAME).read_text(encoding="utf-8")
        assert "origin:" not in written


class TestCuratorHumanOriginProtection:
    TODAY = date(2026, 7, 15)
    ANCIENT = date(2020, 1, 1)

    def test_old_human_entry_is_never_archived(self):
        human = _curator_entry(
            entry_id="LRN-2020-01-01-a", entry_date=self.ANCIENT, origin="human"
        )
        plan = plan_curation([human], today=self.TODAY)
        assert plan.keep == [human]
        assert plan.archive == []

    def test_human_protection_is_case_insensitive(self):
        human = _curator_entry(
            entry_id="LRN-2020-01-01-a", entry_date=self.ANCIENT, origin="Human"
        )
        plan = plan_curation([human], today=self.TODAY)
        assert plan.archive == []

    def test_old_non_human_origin_still_archives(self):
        auditor = _curator_entry(
            entry_id="LRN-2020-01-01-a", entry_date=self.ANCIENT, origin="crew-auditor"
        )
        plan = plan_curation([auditor], today=self.TODAY)
        assert plan.archive == [auditor]

    def test_old_originless_entry_still_archives(self):
        legacy = _curator_entry(
            entry_id="LRN-2020-01-01-a", entry_date=self.ANCIENT, origin=None
        )
        plan = plan_curation([legacy], today=self.TODAY)
        assert plan.archive == [legacy]

    def test_recent_human_entry_kept_like_any_other(self):
        recent = _curator_entry(
            entry_id="LRN-2026-07-01-a", entry_date=date(2026, 7, 1), origin="human"
        )
        plan = plan_curation([recent], today=self.TODAY)
        assert plan.keep == [recent]


class TestCurateLearningsEndToEnd:
    async def test_human_entry_survives_apply_while_auditor_entry_archives(
        self, isolated_env
    ):
        workspace, _home = isolated_env
        _mark_in_workspace(workspace)
        human = _entry_markdown(
            entry_date="2020-01-01", letter="a", origin_line="origin: human\n"
        )
        auditor = _entry_markdown(
            entry_date="2020-01-02", letter="a", origin_line="origin: crew-auditor\n"
        )
        target = workspace / learnings.LEARNINGS_FILENAME
        target.write_text(human + "\n" + auditor, encoding="utf-8")

        result = await curate_learnings(str(workspace), dry_run=False)

        assert "Archived 1 of 2" in result
        live = target.read_text(encoding="utf-8")
        assert "LRN-2020-01-01-a" in live
        assert "LRN-2020-01-02-a" not in live
        archive = (
            workspace / learnings.LEARNINGS_ARCHIVE_FILENAME
        ).read_text(encoding="utf-8")
        assert "LRN-2020-01-02-a" in archive
        assert "LRN-2020-01-01-a" not in archive
