"""Tests for the LEARNINGS retrieval and append module.

Covers entry parsing, the deterministic pre-filter, workspace vs system
write paths, and the workspaces.txt registry. The crew-evaluator agent
is out of scope here; these tests verify the deterministic plumbing the
evaluator sits on top of.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from pathlib import Path

from wopr.tools import learnings
from wopr.tools.learnings import (
    LEARNINGS_ARCHIVE_FILENAME,
    LearningEntry,
    _parse_entries,
    _prefilter,
    _score_entry,
    append_learnings,
    curate_learnings,
    learnings_path,
    learnings_search,
)

# ``isolated_env`` and ``fake_mcp`` fixtures live in tests/conftest.py.


def _make_entry(
    *,
    entry_date: str = "2026-05-01",
    letter: str = "a",
    title: str = "Sample lesson",
    project: str = "[client-project-b]-api-poc-v2",
    stack: list[str] | None = None,
    req: list[str] | None = None,
    seed: bool = False,
) -> str:
    """Build a LEARNINGS.md entry string for fixture use.

    The ``seed`` parameter emits ``seed: true`` in the meta block,
    which the production prefilter uses to bypass the recency cutoff.
    Tests that exercise seed semantics pass ``seed=True`` instead of
    inlining a near-duplicate raw-string body.
    """
    stack = stack or ["spring-boot"]
    req = req or []
    stack_str = "[" + ", ".join(stack) + "]"
    req_str = "[" + ", ".join(req) + "]"
    seed_line = "seed: true\n" if seed else ""
    body = (
        f"## LRN-{entry_date}-{letter}: {title}\n"
        "\n"
        "```meta\n"
        f"date: {entry_date}\n"
        f"project: {project}\n"
        f"stack: {stack_str}\n"
        f"req: {req_str}\n"
        f"auditor_run: AUDIT_REPORT.md@{entry_date}T14:22Z\n"
        "severity: warning\n"
        f"{seed_line}"
        "```\n"
        "\n"
        "**What happened.** Test fixture body.\n"
        "\n"
        "**Why it matters.** Test fixture body.\n"
        "\n"
        "**Pattern to encode.** Test fixture body.\n"
    )
    return body


def _mark_in_workspace(workspace: Path) -> None:
    (workspace / "wopr.yml").write_text("project:\n  slug: test\n", encoding="utf-8")


class TestEntryParsing:
    def test_parses_single_entry(self, tmp_path: Path):
        text = _make_entry(letter="a", title="Generator drift bypassed lockstep")
        entries = _parse_entries(text, tmp_path / "fake.md")
        assert len(entries) == 1
        e = entries[0]
        assert e.id == "LRN-2026-05-01-a"
        assert e.entry_date == date(2026, 5, 1)
        assert e.project == "[client-project-b]-api-poc-v2"
        assert e.stack == ["spring-boot"]
        assert e.req_ids == []
        assert "Generator drift bypassed lockstep" in e.raw

    def test_parses_multiple_entries(self, tmp_path: Path):
        a = _make_entry(letter="a", title="First")
        b = _make_entry(entry_date="2026-05-02", letter="a", title="Second")
        entries = _parse_entries(a + "\n\n" + b, tmp_path / "fake.md")
        assert len(entries) == 2
        assert entries[0].id == "LRN-2026-05-01-a"
        assert entries[1].id == "LRN-2026-05-02-a"

    def test_ignores_unrelated_h2_headers(self, tmp_path: Path):
        text = "## Audit Report - foo\n\nbody\n\n" + _make_entry(letter="a")
        entries = _parse_entries(text, tmp_path / "fake.md")
        assert len(entries) == 1
        assert entries[0].id == "LRN-2026-05-01-a"

    def test_parses_meta_with_req_list(self, tmp_path: Path):
        text = _make_entry(req=["REQ-CASE-1", "REQ-CASE-2"])
        entries = _parse_entries(text, tmp_path / "fake.md")
        assert entries[0].req_ids == ["REQ-CASE-1", "REQ-CASE-2"]

    def test_returns_empty_for_no_matches(self, tmp_path: Path):
        assert _parse_entries("# Some doc\n\nrandom prose\n", tmp_path / "fake.md") == []

    def test_rejects_em_dash_separator(self, tmp_path: Path):
        text = "## LRN-2026-05-01-a — Title\n\nbody\n"
        assert _parse_entries(text, tmp_path / "fake.md") == []


class TestScoreEntry:
    def _entry(
        self,
        *,
        entry_date: date | None = date(2026, 5, 1),
        stack: list[str] | None = None,
        req_ids: list[str] | None = None,
    ) -> LearningEntry:
        return LearningEntry(
            id="LRN-test",
            raw="raw",
            source_path=Path("/tmp/x.md"),
            entry_date=entry_date,
            project="proj",
            stack=stack or [],
            req_ids=req_ids or [],
        )

    def test_stack_match_only(self):
        entry = self._entry(stack=["spring-boot"])
        score = _score_entry(entry, "", ["spring-boot"], date(2026, 5, 7), 180)
        assert score is not None and score >= 1.0

    def test_req_match_boosts_score(self):
        same_stack = self._entry(stack=["spring-boot"], req_ids=["REQ-CASE-1"])
        only_stack = self._entry(stack=["spring-boot"], req_ids=[])
        s_req = _score_entry(same_stack, "REQ-CASE-1", ["spring-boot"], date(2026, 5, 7), 180)
        s_no = _score_entry(only_stack, "REQ-CASE-1", ["spring-boot"], date(2026, 5, 7), 180)
        assert s_req is not None and s_no is not None
        assert s_req > s_no

    def test_filters_when_neither_stack_nor_req(self):
        entry = self._entry(stack=["angular"], req_ids=[])
        score = _score_entry(entry, "REQ-CASE-1", ["spring-boot"], date(2026, 5, 7), 180)
        assert score is None

    def test_drops_stale_without_req_match(self):
        old = self._entry(entry_date=date(2025, 1, 1), stack=["spring-boot"])
        score = _score_entry(old, "", ["spring-boot"], date(2026, 5, 7), 180)
        assert score is None

    def test_keeps_stale_when_req_matches(self):
        old = self._entry(
            entry_date=date(2025, 1, 1),
            stack=["spring-boot"],
            req_ids=["REQ-CASE-1"],
        )
        score = _score_entry(old, "REQ-CASE-1", ["spring-boot"], date(2026, 5, 7), 180)
        assert score is not None
        assert score >= 2.0

    def test_recent_entries_outscore_older_ones(self):
        recent = self._entry(entry_date=date(2026, 5, 1), stack=["spring-boot"])
        older = self._entry(entry_date=date(2026, 1, 1), stack=["spring-boot"])
        s_recent = _score_entry(recent, "", ["spring-boot"], date(2026, 5, 7), 180)
        s_older = _score_entry(older, "", ["spring-boot"], date(2026, 5, 7), 180)
        assert s_recent is not None and s_older is not None
        assert s_recent > s_older

    def test_no_stack_filter_when_stack_tags_empty(self):
        entry = self._entry(stack=["angular"])
        score = _score_entry(entry, "", [], date(2026, 5, 7), 180)
        assert score is not None


class TestPrefilterIntegration:
    """Six hand-crafted entries exercise the full prefilter pipeline."""

    def _build_corpus(self) -> str:
        today = datetime.now(tz=timezone.utc).date()
        recent = (today - timedelta(days=10)).isoformat()
        old_reachable = (today - timedelta(days=170)).isoformat()
        stale = (today - timedelta(days=400)).isoformat()
        return "\n\n".join([
            _make_entry(entry_date=recent, letter="a", title="Spring REQ match",
                        stack=["spring-boot"], req=["REQ-CASE-1"]),
            _make_entry(entry_date=recent, letter="b", title="Angular noise",
                        stack=["angular"], req=[]),
            _make_entry(entry_date=old_reachable, letter="a", title="Old spring",
                        stack=["spring-boot"], req=[]),
            _make_entry(entry_date=stale, letter="a", title="Stale spring no req",
                        stack=["spring-boot"], req=[]),
            _make_entry(entry_date=stale, letter="b", title="Stale spring REQ match",
                        stack=["spring-boot"], req=["REQ-CASE-1"]),
            _make_entry(entry_date=recent, letter="c", title="Multi-stack",
                        stack=["openapi-generator"], req=[]),
        ])

    def test_prefilter_drops_wrong_stack_and_stale_no_req(self, tmp_path: Path):
        entries = _parse_entries(self._build_corpus(), tmp_path / "fake.md")
        result = _prefilter(entries, "REQ-CASE-1", ["spring-boot"], 180, 20)
        kept_titles = [e.raw.split("\n", 1)[0] for e in result]
        assert any("Spring REQ match" in t for t in kept_titles)
        assert any("Old spring" in t for t in kept_titles)
        assert any("Stale spring REQ match" in t for t in kept_titles)
        assert not any("Angular noise" in t for t in kept_titles)
        assert not any("Stale spring no req" in t for t in kept_titles)
        assert not any("Multi-stack" in t for t in kept_titles)

    def test_prefilter_orders_by_score_desc(self, tmp_path: Path):
        entries = _parse_entries(self._build_corpus(), tmp_path / "fake.md")
        result = _prefilter(entries, "REQ-CASE-1", ["spring-boot"], 180, 20)
        # REQ match + recent + stack should rank above old-no-req-stack.
        assert "Spring REQ match" in result[0].raw

    def test_prefilter_respects_limit(self, tmp_path: Path):
        entries = _parse_entries(self._build_corpus(), tmp_path / "fake.md")
        result = _prefilter(entries, "REQ-CASE-1", ["spring-boot"], 180, 1)
        assert len(result) == 1


class TestAppendLearnings:
    async def test_no_target_and_no_ambient_errors(self, isolated_env, monkeypatch):
        monkeypatch.delenv("CLAUDE_PROJECT_DIR", raising=False)
        result = await append_learnings(entry_markdown=_make_entry())
        assert result.startswith("Error")
        assert "target_workspace_path" in result

    async def test_rejects_empty_entry(self, isolated_env):
        workspace, _home = isolated_env
        result = await append_learnings(str(workspace), entry_markdown="")
        assert result.startswith("Error")

    async def test_rejects_invalid_header(self, isolated_env):
        workspace, _home = isolated_env
        result = await append_learnings(
            str(workspace), entry_markdown="## not a learnings header\n\nbody\n"
        )
        assert result.startswith("Error")

    async def test_rejects_em_dash_header(self, isolated_env):
        workspace, _home = isolated_env
        bad = "## LRN-2026-05-01-a — Title\n\nbody\n"
        result = await append_learnings(str(workspace), entry_markdown=bad)
        assert result.startswith("Error")

    async def test_rejects_entry_with_leaked_home_dir(self, isolated_env):
        workspace, _home = isolated_env
        bad = (
            "## LRN-2026-05-01-a: Bad path in lesson\n\n"
            "**What happened.** Fix landed in /Users/jsmith/Projects/foo.\n"
        )
        result = await append_learnings(str(workspace), entry_markdown=bad)
        assert result.startswith("Error")
        assert "macOS home directory path" in result
        assert not (workspace / "LEARNINGS.md").exists()

    async def test_rejects_entry_with_leaked_secret(self, isolated_env):
        workspace, _home = isolated_env
        bad = (
            "## LRN-2026-05-01-a: Bad secret in lesson\n\n"
            "**What happened.** Rotated the key AKIAIOSFODNN7EXAMPLE.\n"
        )
        result = await append_learnings(str(workspace), entry_markdown=bad)
        assert result.startswith("Error")
        assert "AWS access key" in result

    async def test_accepts_clean_entry_after_rejection(self, isolated_env):
        workspace, _home = isolated_env
        _mark_in_workspace(workspace)
        bad = (
            "## LRN-2026-05-01-a: Bad path in lesson\n\n"
            "**What happened.** Fix landed in /Users/jsmith/Projects/foo.\n"
        )
        await append_learnings(str(workspace), entry_markdown=bad)
        good = _make_entry()
        result = await append_learnings(str(workspace), entry_markdown=good)
        assert result.startswith("Appended")

    async def test_in_workspace_writes_to_workspace_file(self, isolated_env):
        workspace, _home = isolated_env
        _mark_in_workspace(workspace)
        result = await append_learnings(str(workspace), entry_markdown=_make_entry())
        assert "Appended" in result
        target = workspace / "LEARNINGS.md"
        assert target.exists()
        assert "LRN-2026-05-01-a" in target.read_text(encoding="utf-8")

    async def test_named_target_that_resolves_to_nothing_is_an_error(
        self, isolated_env
    ):
        """Was: silently wrote to ~/.wopr/LEARNINGS.md.

        The caller named a directory. If that directory belongs to no
        workspace, the honest answer is to say so and name the
        directories that were searched -- not to write the entry
        somewhere the caller will never look for it.
        """
        workspace, home = isolated_env
        # No wopr.yml and no LEARNINGS.md anywhere up the tree.
        result = await append_learnings(str(workspace), entry_markdown=_make_entry())
        assert result.startswith("Error")
        assert "no workspace root found" in result
        assert str(workspace) in result  # the searched paths are named
        assert not (home / "LEARNINGS.md").exists()  # nothing written elsewhere
        assert not (workspace / "LEARNINGS.md").exists()

    async def test_no_named_target_still_falls_back_to_the_system_file(
        self, isolated_env, monkeypatch
    ):
        """The one fallback that survives: the caller named nothing.

        With no target path there is no caller expectation to violate,
        so the system corpus is the right home for the entry.
        """
        workspace, home = isolated_env
        monkeypatch.setenv("CLAUDE_PROJECT_DIR", str(workspace))
        result = await append_learnings(entry_markdown=_make_entry())
        assert "Appended" in result
        target = home / "LEARNINGS.md"
        assert target.exists()
        assert "LRN-2026-05-01-a" in target.read_text(encoding="utf-8")

    async def test_appends_with_separator_when_file_nonempty(self, isolated_env):
        workspace, _home = isolated_env
        _mark_in_workspace(workspace)
        first = _make_entry(letter="a", title="First")
        second = _make_entry(letter="b", title="Second")
        await append_learnings(str(workspace), entry_markdown=first)
        await append_learnings(str(workspace), entry_markdown=second)
        text = (workspace / "LEARNINGS.md").read_text(encoding="utf-8")
        assert text.count("## LRN-") == 2
        # Ensure entries are separated by at least one blank line, not concatenated.
        marker = "## LRN-2026-05-01-b:"
        idx = text.index(marker)
        # The two characters immediately before the second entry must form a
        # blank line, i.e. a newline followed by another newline.
        assert text[idx - 2 : idx] == "\n\n"

    async def test_in_workspace_append_registers_workspace(self, isolated_env):
        workspace, home = isolated_env
        _mark_in_workspace(workspace)
        await append_learnings(str(workspace), entry_markdown=_make_entry())
        registry = home / "workspaces.txt"
        assert registry.exists()
        lines = registry.read_text(encoding="utf-8").splitlines()
        assert str(workspace.resolve()) in lines

    async def test_registry_append_is_idempotent(self, isolated_env):
        workspace, home = isolated_env
        _mark_in_workspace(workspace)
        await append_learnings(str(workspace), entry_markdown=_make_entry(letter="a"))
        await append_learnings(str(workspace), entry_markdown=_make_entry(letter="b"))
        lines = (home / "workspaces.txt").read_text(encoding="utf-8").splitlines()
        assert lines.count(str(workspace.resolve())) == 1


class TestLearningsSearch:
    async def test_in_workspace_reads_workspace_only(self, isolated_env):
        workspace, home = isolated_env
        _mark_in_workspace(workspace)
        today = datetime.now(tz=timezone.utc).date().isoformat()
        # Fresh-dated workspace entry the search should find.
        (workspace / "LEARNINGS.md").write_text(
            _make_entry(entry_date=today, letter="a", title="Workspace lesson"),
            encoding="utf-8",
        )
        # System entry that must NOT leak into in-workspace reads.
        home.mkdir(parents=True, exist_ok=True)
        (home / "LEARNINGS.md").write_text(
            _make_entry(entry_date=today, letter="b", title="System lesson"),
            encoding="utf-8",
        )
        result = await learnings_search(req_id="", stack_tags=["spring-boot"])
        assert "Workspace lesson" in result
        assert "System lesson" not in result

    async def test_outside_workspace_aggregates_system_and_registered(
        self, isolated_env, tmp_path: Path
    ):
        _workspace, home = isolated_env
        # No wopr.yml in workspace -> outside mode.
        today = datetime.now(tz=timezone.utc).date().isoformat()
        # System file.
        home.mkdir(parents=True, exist_ok=True)
        (home / "LEARNINGS.md").write_text(
            _make_entry(entry_date=today, letter="a", title="System"),
            encoding="utf-8",
        )
        # Registered foreign workspace.
        foreign = tmp_path / "foreign-workspace"
        foreign.mkdir()
        (foreign / "wopr.yml").write_text("project:\n  slug: f\n", encoding="utf-8")
        (foreign / "LEARNINGS.md").write_text(
            _make_entry(entry_date=today, letter="b", title="Foreign"),
            encoding="utf-8",
        )
        (home / "workspaces.txt").write_text(
            f"{foreign.resolve()}\n",
            encoding="utf-8",
        )
        result = await learnings_search(req_id="", stack_tags=["spring-boot"])
        assert "System" in result
        assert "Foreign" in result

    async def test_outside_workspace_skips_missing_registered_paths(
        self, isolated_env, tmp_path: Path
    ):
        _workspace, home = isolated_env
        today = datetime.now(tz=timezone.utc).date().isoformat()
        home.mkdir(parents=True, exist_ok=True)
        (home / "LEARNINGS.md").write_text(
            _make_entry(entry_date=today, letter="a", title="System"),
            encoding="utf-8",
        )
        # Registry points at a workspace that does not exist on disk.
        (home / "workspaces.txt").write_text(
            f"{tmp_path / 'gone'}\n",
            encoding="utf-8",
        )
        result = await learnings_search(req_id="", stack_tags=["spring-boot"])
        assert "System" in result

    async def test_empty_when_no_files_present(self, isolated_env):
        # No wopr.yml, no system file. Should return empty string, not crash.
        result = await learnings_search(req_id="", stack_tags=["spring-boot"])
        assert result == ""

    async def test_search_in_workspace_registers_workspace(self, isolated_env):
        workspace, home = isolated_env
        _mark_in_workspace(workspace)
        # No LEARNINGS.md yet; search should still register the workspace.
        await learnings_search(req_id="", stack_tags=["spring-boot"])
        registry = home / "workspaces.txt"
        assert registry.exists()
        assert str(workspace.resolve()) in registry.read_text(encoding="utf-8")


class TestLearningsPath:
    async def test_in_workspace_paths(self, isolated_env):
        workspace, _home = isolated_env
        _mark_in_workspace(workspace)
        result = await learnings_path()
        assert "in_workspace: True" in result
        assert str(workspace / "LEARNINGS.md") in result

    async def test_outside_workspace_paths(self, isolated_env):
        _workspace, home = isolated_env
        result = await learnings_path()
        assert "in_workspace: False" in result
        assert str(home / "LEARNINGS.md") in result


class TestSeedLearnings:
    def test_rejects_relative_path(self):
        result = learnings.seed_learnings("relative/path", ["angular"])
        assert result.startswith("Error")
        assert "not absolute" in result

    def test_rejects_empty_path(self):
        result = learnings.seed_learnings("", ["angular"])
        assert result.startswith("Error")
        assert "required" in result.lower()

    def test_rejects_empty_stack_tags(self, isolated_env):
        workspace, _ = isolated_env
        result = learnings.seed_learnings(str(workspace), [])
        assert result.startswith("Error")
        assert "stack_tags" in result

    def test_unknown_stack_returns_error(self, isolated_env):
        workspace, _ = isolated_env
        # Sentinel name that cannot collide with a real future stack
        # (the cute "cobol" placeholder rotted the moment someone
        # added a real cobol seed file, even hypothetically).
        result = learnings.seed_learnings(
            str(workspace), ["definitely-not-a-real-stack-xyz123"]
        )
        assert result.startswith("Error")
        assert "no seed files" in result.lower()

    def test_seeds_angular_stack(self, isolated_env):
        workspace, _ = isolated_env
        _mark_in_workspace(workspace)
        result = learnings.seed_learnings(str(workspace), ["angular"])
        assert result.startswith("Seeded")
        target = workspace / "LEARNINGS.md"
        assert target.is_file()
        content = target.read_text(encoding="utf-8")
        # All five Angular seeds landed.
        assert content.count("## LRN-2024-01-01-") == 5
        # Seed marker preserved so the prefilter recognizes them.
        assert "seed: true" in content

    def test_seeds_multiple_stacks(self, isolated_env):
        workspace, _ = isolated_env
        _mark_in_workspace(workspace)
        result = learnings.seed_learnings(
            str(workspace), ["angular", "spring-boot"]
        )
        assert result.startswith("Seeded ")
        content = (workspace / "LEARNINGS.md").read_text(encoding="utf-8")
        # Angular seeds (LRN-2024-01-01-*) land in full.
        assert content.count("## LRN-2024-01-01-") == 5
        # Spring Boot seeds: the original 2024-01-02-* batch plus any
        # later-dated entries the seed file has grown. Assert both
        # cohorts are present without hardcoding the total, so adding
        # more seeds is not a test-breaking change.
        assert content.count("## LRN-2024-01-02-") == 5
        # At least one entry from each requested stack landed.
        assert "spring-boot" in content
        assert "angular" in content

    def test_idempotent_when_seeds_already_present(self, isolated_env):
        workspace, _ = isolated_env
        _mark_in_workspace(workspace)
        # First call seeds.
        learnings.seed_learnings(str(workspace), ["angular"])
        original = (workspace / "LEARNINGS.md").read_text(encoding="utf-8")
        # Second call detects duplicates and does not append again.
        result = learnings.seed_learnings(str(workspace), ["angular"])
        assert result.startswith("Seeded 0 entries")
        after = (workspace / "LEARNINGS.md").read_text(encoding="utf-8")
        assert after == original

    def test_registers_workspace(self, isolated_env):
        workspace, home = isolated_env
        _mark_in_workspace(workspace)
        learnings.seed_learnings(str(workspace), ["angular"])
        registry = home / "workspaces.txt"
        assert registry.is_file()
        assert str(workspace.resolve()) in registry.read_text(encoding="utf-8")


class TestSeedEntriesBypassAgeFilter:
    """Seed entries (``seed: true`` in their meta block) must remain
    retrievable regardless of how old their entry_date is. The CRAG
    pre-filter would otherwise drop them as stale and the seeding
    operation would be pointless."""

    async def test_seed_entry_with_old_date_still_scores_when_stack_matches(
        self, isolated_env
    ):
        workspace, _ = isolated_env
        _mark_in_workspace(workspace)
        (workspace / "LEARNINGS.md").write_text(
            _make_entry(
                entry_date="2020-01-01",
                title="An old seed lesson",
                project="_seed",
                stack=["angular"],
                seed=True,
            ),
            encoding="utf-8",
        )
        result = await learnings.learnings_search(req_id="", stack_tags=["angular"])
        # Without the seed-bypass, this entry would be dropped (too old).
        assert "An old seed lesson" in result

    async def test_non_seed_entry_with_same_old_date_is_dropped(self, isolated_env):
        """Confirm the bypass only applies when seed: true is present."""
        workspace, _ = isolated_env
        _mark_in_workspace(workspace)
        (workspace / "LEARNINGS.md").write_text(
            _make_entry(
                entry_date="2020-01-01",
                title="An old non-seed lesson",
                project="someproj",
                stack=["angular"],
                seed=False,
            ),
            encoding="utf-8",
        )
        result = await learnings.learnings_search(req_id="", stack_tags=["angular"])
        # Age-based filter drops this one.
        assert "An old non-seed lesson" not in result


class TestRegister:
    def test_register_registers_expected_tools(self, fake_mcp):
        learnings.register(fake_mcp)
        assert sorted(fake_mcp.registered) == [
            "append_learnings",
            "curate_learnings",
            "learnings_path",
            "learnings_search",
            "seed_learnings",
        ]


class TestCurateLearnings:
    async def test_no_target_and_no_ambient_errors(self, monkeypatch):
        monkeypatch.delenv("CLAUDE_PROJECT_DIR", raising=False)
        result = await curate_learnings()
        assert result.startswith("Error")

    async def test_missing_file_reports_nothing_to_curate(self, isolated_env):
        workspace, _home = isolated_env
        _mark_in_workspace(workspace)
        result = await curate_learnings(str(workspace))
        assert result.startswith("Nothing to curate")

    async def test_named_target_that_resolves_to_nothing_is_an_error(
        self, isolated_env
    ):
        """Was: silently curated ~/.wopr/LEARNINGS.md.

        Curation rewrites a corpus. Rewriting the wrong one because the
        named target did not resolve is strictly worse than refusing.
        """
        workspace, _home = isolated_env
        result = await curate_learnings(str(workspace))
        assert result.startswith("Error")
        assert "no workspace root found" in result

    async def test_dry_run_default_does_not_mutate(self, isolated_env):
        workspace, _home = isolated_env
        _mark_in_workspace(workspace)
        old = _make_entry(entry_date="2020-01-01", letter="a")
        await append_learnings(str(workspace), entry_markdown=old)

        result = await curate_learnings(str(workspace))

        assert "Would archive" in result
        assert "LRN-2020-01-01-a" in result
        text = (workspace / "LEARNINGS.md").read_text(encoding="utf-8")
        assert "LRN-2020-01-01-a" in text  # still there -- dry run did not mutate
        assert not (workspace / LEARNINGS_ARCHIVE_FILENAME).exists()

    async def test_apply_moves_stale_entry_to_archive(self, isolated_env):
        workspace, _home = isolated_env
        _mark_in_workspace(workspace)
        old = _make_entry(entry_date="2020-01-01", letter="a", title="Old lesson")
        await append_learnings(str(workspace), entry_markdown=old)

        result = await curate_learnings(str(workspace), dry_run=False)

        assert "Archived" in result
        live_text = (workspace / "LEARNINGS.md").read_text(encoding="utf-8")
        assert "LRN-2020-01-01-a" not in live_text
        archive_path = workspace / LEARNINGS_ARCHIVE_FILENAME
        assert archive_path.is_file()
        assert "LRN-2020-01-01-a" in archive_path.read_text(encoding="utf-8")
        assert "Old lesson" in archive_path.read_text(encoding="utf-8")

    async def test_recent_entry_is_not_archived(self, isolated_env):
        workspace, _home = isolated_env
        _mark_in_workspace(workspace)
        recent = _make_entry(
            entry_date=date.today().isoformat(), letter="a"
        )
        await append_learnings(str(workspace), entry_markdown=recent)

        result = await curate_learnings(str(workspace), dry_run=False)

        assert "Nothing to archive" in result
        text = (workspace / "LEARNINGS.md").read_text(encoding="utf-8")
        assert f"LRN-{date.today().isoformat()}-a" in text

    async def test_seed_entry_survives_even_when_ancient(self, isolated_env):
        workspace, _home = isolated_env
        _mark_in_workspace(workspace)
        ancient_seed = _make_entry(entry_date="2015-01-01", letter="a", seed=True)
        await append_learnings(str(workspace), entry_markdown=ancient_seed)

        result = await curate_learnings(str(workspace), dry_run=False)

        assert "Nothing to archive" in result
        text = (workspace / "LEARNINGS.md").read_text(encoding="utf-8")
        assert "LRN-2015-01-01-a" in text

    async def test_second_archive_run_appends_not_overwrites(self, isolated_env):
        workspace, _home = isolated_env
        _mark_in_workspace(workspace)
        old_a = _make_entry(entry_date="2020-01-01", letter="a")
        await append_learnings(str(workspace), entry_markdown=old_a)
        await curate_learnings(str(workspace), dry_run=False)

        old_b = _make_entry(entry_date="2020-02-01", letter="b")
        await append_learnings(str(workspace), entry_markdown=old_b)
        await curate_learnings(str(workspace), dry_run=False)

        archive_text = (workspace / LEARNINGS_ARCHIVE_FILENAME).read_text(encoding="utf-8")
        assert "LRN-2020-01-01-a" in archive_text
        assert "LRN-2020-02-01-b" in archive_text

    async def test_custom_stale_after_days(self, isolated_env):
        workspace, _home = isolated_env
        _mark_in_workspace(workspace)
        forty_five_days_ago = (date.today() - timedelta(days=45)).isoformat()
        entry = _make_entry(entry_date=forty_five_days_ago, letter="a")
        await append_learnings(str(workspace), entry_markdown=entry)

        result = await curate_learnings(str(workspace), stale_after_days=30, dry_run=False)

        assert "Archived" in result
        text = (workspace / "LEARNINGS.md").read_text(encoding="utf-8")
        assert f"LRN-{forty_five_days_ago}-a" not in text
