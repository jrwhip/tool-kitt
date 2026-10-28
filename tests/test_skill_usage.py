"""Tests for the skill usage telemetry sidecar and its MCP tools.

Covers the store (:mod:`kitt.tools._skill_usage`), the ``kitt
skill-usage`` CLI, and the two MCP tools. The coverage-boundary metadata
is asserted explicitly: it is the part of this feature most likely to be
quietly dropped in a future refactor, and without it the numbers read as
a census.
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from kitt import skill_usage_cli
from kitt.tools import _skill_usage, skill_usage

NOW = datetime(2026, 8, 2, 12, 0, tzinfo=timezone.utc)


@pytest.fixture
def home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Isolated ``KITT_HOME`` so the sidecar never touches the operator's."""
    kitt_home = tmp_path / "kitt-home"
    kitt_home.mkdir()
    monkeypatch.setenv("KITT_HOME", str(kitt_home))
    return kitt_home


def _make_skill(skills_dir: Path, name: str, description: str = "Does a thing") -> Path:
    d = skills_dir / name
    d.mkdir(parents=True, exist_ok=True)
    (d / "SKILL.md").write_text(
        f"---\nname: {name}\ndescription: {description}\n---\nbody",
        encoding="utf-8",
    )
    return d


# ---------------------------------------------------------------------------
# Store: recording
# ---------------------------------------------------------------------------


class TestRecordInvocation:
    def test_first_record_creates_the_sidecar(self, home: Path):
        assert _skill_usage.record_invocation("kitt-debug", _skill_usage.SOURCE_MCP)
        data = json.loads((home / "skill-usage.json").read_text(encoding="utf-8"))
        assert data["version"] == _skill_usage.USAGE_VERSION
        record = data["skills"]["kitt-debug"]
        assert record["count"] == 1
        assert record["sources"] == {"mcp": 1}
        assert record["state"] == "active"

    def test_counts_accumulate_per_source(self, home: Path):
        _skill_usage.record_invocation("kitt-debug", _skill_usage.SOURCE_MCP)
        _skill_usage.record_invocation("kitt-debug", _skill_usage.SOURCE_MCP)
        _skill_usage.record_invocation(
            "kitt-debug", _skill_usage.SOURCE_HOOK_CLAUDE, count=3
        )
        record = _skill_usage.load_usage()["kitt-debug"]
        assert record["count"] == 5
        assert record["sources"] == {"mcp": 2, "hook:claude": 3}

    def test_unknown_source_is_refused(self, home: Path):
        assert not _skill_usage.record_invocation("kitt-debug", "telepathy")
        assert _skill_usage.load_usage() == {}

    @pytest.mark.parametrize(
        "name", ["", "  ", "../escape", "a/b", "a\\b", ".", "..", "x" * 200]
    )
    def test_unsafe_names_are_refused(self, home: Path, name: str):
        assert not _skill_usage.record_invocation(name, _skill_usage.SOURCE_MCP)
        assert _skill_usage.load_usage() == {}

    def test_non_positive_count_is_refused(self, home: Path):
        assert not _skill_usage.record_invocation(
            "kitt-debug", _skill_usage.SOURCE_MCP, count=0
        )

    def test_use_resets_a_stale_label(self, home: Path):
        _skill_usage.record_invocation(
            "kitt-debug", _skill_usage.SOURCE_MCP, now=NOW - timedelta(days=300)
        )
        records, _ = _skill_usage.refresh(
            _skill_usage.load_usage(), [], now=NOW
        )
        _skill_usage.save_usage(records)
        assert _skill_usage.load_usage()["kitt-debug"]["state"] == "stale"

        _skill_usage.record_invocation("kitt-debug", _skill_usage.SOURCE_MCP, now=NOW)
        assert _skill_usage.load_usage()["kitt-debug"]["state"] == "active"

    def test_privacy_no_free_text_reaches_the_file(self, home: Path):
        _skill_usage.record_invocation("kitt-debug", _skill_usage.SOURCE_MCP)
        text = (home / "skill-usage.json").read_text(encoding="utf-8")
        record = json.loads(text)["skills"]["kitt-debug"]
        assert set(record) == {
            "count",
            "sources",
            "first_seen_at",
            "last_used_at",
            "state",
            "state_changed_at",
            "pinned",
        }


# ---------------------------------------------------------------------------
# Store: robustness
# ---------------------------------------------------------------------------


class TestLoadRobustness:
    def test_missing_file_is_empty(self, home: Path):
        assert _skill_usage.load_usage() == {}

    @pytest.mark.parametrize("body", ["not json", "[]", '{"skills": 5}', "null"])
    def test_corrupt_file_degrades_to_empty(self, home: Path, body: str):
        (home / "skill-usage.json").write_text(body, encoding="utf-8")
        assert _skill_usage.load_usage() == {}

    def test_partial_record_is_repaired_field_by_field(self, home: Path):
        (home / "skill-usage.json").write_text(
            json.dumps(
                {
                    "version": 1,
                    "skills": {
                        "kitt-debug": {
                            "count": "seven",
                            "sources": {"mcp": 2, "hacked": 99, "bad": "x"},
                            "state": "banana",
                            "pinned": True,
                            "last_used_at": "not-a-date",
                        }
                    },
                }
            ),
            encoding="utf-8",
        )
        record = _skill_usage.load_usage()["kitt-debug"]
        assert record["count"] == 0
        assert record["sources"] == {"mcp": 2}
        assert record["state"] == "active"
        # The operator's pin survives its neighbours being garbage.
        assert record["pinned"] is True
        assert record["last_used_at"] is None

    def test_unsafe_key_is_dropped(self, home: Path):
        (home / "skill-usage.json").write_text(
            json.dumps({"version": 1, "skills": {"../evil": {"count": 1}}}),
            encoding="utf-8",
        )
        assert _skill_usage.load_usage() == {}


# ---------------------------------------------------------------------------
# Lifecycle
# ---------------------------------------------------------------------------


class TestClassify:
    def _record(self, **kw: object) -> dict[str, object]:
        base = {
            "count": 0,
            "sources": {},
            "first_seen_at": (NOW - timedelta(days=1)).isoformat(),
            "last_used_at": None,
            "state": "active",
            "state_changed_at": None,
            "pinned": False,
        }
        base.update(kw)
        return base

    def test_recent_use_is_active(self):
        record = self._record(last_used_at=(NOW - timedelta(days=3)).isoformat())
        assert _skill_usage.classify(record, now=NOW) == "active"

    def test_idle_past_stale_threshold(self):
        record = self._record(last_used_at=(NOW - timedelta(days=200)).isoformat())
        assert _skill_usage.classify(record, now=NOW) == "stale"

    def test_idle_past_archive_threshold(self):
        record = self._record(last_used_at=(NOW - timedelta(days=400)).isoformat())
        assert _skill_usage.classify(record, now=NOW) == "archived"

    def test_never_used_ages_from_first_seen_not_epoch(self):
        fresh = self._record(first_seen_at=(NOW - timedelta(days=2)).isoformat())
        assert _skill_usage.classify(fresh, now=NOW) == "active"
        old = self._record(first_seen_at=(NOW - timedelta(days=200)).isoformat())
        assert _skill_usage.classify(old, now=NOW) == "stale"

    def test_pinned_is_never_stale(self):
        record = self._record(
            last_used_at=(NOW - timedelta(days=5000)).isoformat(), pinned=True
        )
        assert _skill_usage.classify(record, now=NOW) == "active"

    def test_unparseable_anchor_stays_active(self):
        record = self._record(first_seen_at="whenever", last_used_at=None)
        assert _skill_usage.classify(record, now=NOW) == "active"

    def test_naive_timestamp_does_not_raise(self):
        record = self._record(last_used_at="2020-01-01T00:00:00")
        assert _skill_usage.classify(record, now=NOW) == "archived"


class TestRefresh:
    def test_seeds_installed_skills_with_a_first_seen_anchor(self):
        records, changed = _skill_usage.refresh({}, ["kitt-a", "kitt-b"], now=NOW)
        assert changed is True
        assert set(records) == {"kitt-a", "kitt-b"}
        assert records["kitt-a"]["first_seen_at"] == NOW.isoformat()
        assert records["kitt-a"]["count"] == 0

    def test_no_change_is_reported_as_no_change(self):
        records, _ = _skill_usage.refresh({}, ["kitt-a"], now=NOW)
        _, changed = _skill_usage.refresh(records, ["kitt-a"], now=NOW)
        assert changed is False

    def test_uninstalled_records_are_kept(self):
        records, _ = _skill_usage.refresh({}, ["kitt-a"], now=NOW)
        records, _ = _skill_usage.refresh(records, [], now=NOW)
        assert "kitt-a" in records


class TestPinning:
    def test_pin_creates_a_record_before_first_use(self, home: Path):
        assert _skill_usage.set_pinned("kitt-rare", True)
        assert _skill_usage.load_usage()["kitt-rare"]["pinned"] is True

    def test_pin_survives_refresh_and_blocks_staleness(self, home: Path):
        _skill_usage.record_invocation(
            "kitt-rare", _skill_usage.SOURCE_MCP, now=NOW - timedelta(days=900)
        )
        _skill_usage.set_pinned("kitt-rare", True)
        records, _ = _skill_usage.refresh(
            _skill_usage.load_usage(), ["kitt-rare"], now=NOW
        )
        assert records["kitt-rare"]["state"] == "active"

    def test_unpin_lets_the_clock_apply_again(self, home: Path):
        _skill_usage.record_invocation(
            "kitt-rare", _skill_usage.SOURCE_MCP, now=NOW - timedelta(days=900)
        )
        _skill_usage.set_pinned("kitt-rare", True)
        _skill_usage.set_pinned("kitt-rare", False)
        records, _ = _skill_usage.refresh(
            _skill_usage.load_usage(), ["kitt-rare"], now=NOW
        )
        assert records["kitt-rare"]["state"] == "archived"

    def test_forget_drops_the_record(self, home: Path):
        _skill_usage.record_invocation("kitt-debug", _skill_usage.SOURCE_MCP)
        assert _skill_usage.forget("kitt-debug") is True
        assert _skill_usage.load_usage() == {}
        assert _skill_usage.forget("kitt-debug") is False


# ---------------------------------------------------------------------------
# Report
# ---------------------------------------------------------------------------


class TestReport:
    def test_report_seeds_persists_and_labels(self, home: Path):
        _skill_usage.record_invocation("kitt-used", _skill_usage.SOURCE_MCP, now=NOW)
        payload = _skill_usage.report(["kitt-used", "kitt-never"], now=NOW)
        assert payload["persisted"] is True
        assert payload["totals"] == {
            "skills": 2,
            "observed": 1,
            "unobserved": 1,
            "pinned": 0,
        }
        rows = {row["name"]: row for row in payload["skills"]}
        assert rows["kitt-used"]["count"] == 1
        assert rows["kitt-never"]["count"] == 0
        assert rows["kitt-never"]["installed"] is True
        # Seeding persisted, so a second report sees the same anchor.
        assert _skill_usage.load_usage()["kitt-never"]["first_seen_at"]

    def test_uninstalled_records_are_flagged(self, home: Path):
        _skill_usage.record_invocation("kitt-gone", _skill_usage.SOURCE_MCP)
        payload = _skill_usage.report([], now=NOW)
        assert payload["skills"][0]["installed"] is False

    def test_coverage_boundary_ships_with_the_numbers(self, home: Path):
        payload = _skill_usage.report(["kitt-a"], now=NOW)
        coverage = payload["coverage"]
        assert coverage["counts_are"] == "lower bound"
        assert set(coverage["observed_sources"]) == _skill_usage.KNOWN_SOURCES
        gaps = " ".join(coverage["uncovered"]).lower()
        assert "copilot" in gaps and "gemini" in gaps
        assert "unobserved" in coverage["reading_zero"].lower()


# ---------------------------------------------------------------------------
# Write-failure containment
# ---------------------------------------------------------------------------


class TestWriteFailureContainment:
    """Telemetry must degrade to a no-op, never raise at a call site.

    The prior toolset asserted this through the ``run_skill`` MCP tool,
    which counted its own invocations. That tool does not cross over, so
    the property is asserted directly against the store.
    """

    def test_unwritable_sidecar_reports_failure_without_raising(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ):
        blocked = tmp_path / "not-a-directory"
        blocked.write_text("i am a file", encoding="utf-8")
        monkeypatch.setenv("KITT_HOME", str(blocked))

        assert not _skill_usage.record_invocation(
            "kitt-create-plans", _skill_usage.SOURCE_MCP
        )


# ---------------------------------------------------------------------------
# MCP tools
# ---------------------------------------------------------------------------


class TestMcpTools:
    def test_register(self, fake_mcp):
        skill_usage.register(fake_mcp)
        assert sorted(fake_mcp.registered) == ["pin_skill", "skill_usage_report"]

    async def test_report_tool_returns_json_with_coverage(self, workspace: Path):
        skills = workspace / ".ai-cli" / "shared" / "skills"
        skills.mkdir(parents=True)
        _make_skill(skills, "kitt-a")
        payload = json.loads(
            await skill_usage.skill_usage_report(
                target_workspace_path=str(workspace)
            )
        )
        assert [row["name"] for row in payload["skills"]] == ["kitt-a"]
        assert payload["coverage"]["counts_are"] == "lower bound"

    async def test_pin_tool_round_trip(self, workspace: Path):
        skills = workspace / ".ai-cli" / "shared" / "skills"
        skills.mkdir(parents=True)
        _make_skill(skills, "kitt-a")
        payload = json.loads(
            await skill_usage.pin_skill("kitt-a", True, str(workspace))
        )
        assert payload["pinned"] is True
        assert payload["installed"] is True
        payload = json.loads(
            await skill_usage.pin_skill("kitt-a", False, str(workspace))
        )
        assert payload["pinned"] is False

    async def test_pin_tool_rejects_a_path_traversal_name(self, workspace: Path):
        out = await skill_usage.pin_skill("../../etc", True, str(workspace))
        assert out.startswith("Error:")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


class TestCli:
    def test_record_counts_repeated_names_once_per_write(self, home: Path):
        rc = skill_usage_cli.cmd_skill_usage(
            ["record", "hook:claude", "kitt-a", "kitt-a", "kitt-b"]
        )
        assert rc == 0
        records = _skill_usage.load_usage()
        assert records["kitt-a"]["count"] == 2
        assert records["kitt-b"]["count"] == 1

    def test_record_rejects_unknown_source(self, home: Path):
        assert skill_usage_cli.cmd_skill_usage(["record", "nope", "kitt-a"]) == 1
        assert _skill_usage.load_usage() == {}

    def test_record_needs_a_source_and_a_name(self, home: Path):
        assert skill_usage_cli.cmd_skill_usage(["record"]) == 1
        assert skill_usage_cli.cmd_skill_usage(["record", "hook:claude"]) == 1

    def test_pin_and_unpin(self, home: Path):
        assert skill_usage_cli.cmd_skill_usage(["pin", "kitt-a"]) == 0
        assert _skill_usage.load_usage()["kitt-a"]["pinned"] is True
        assert skill_usage_cli.cmd_skill_usage(["unpin", "kitt-a"]) == 0
        assert _skill_usage.load_usage()["kitt-a"]["pinned"] is False

    def test_pin_needs_a_name(self, home: Path):
        assert skill_usage_cli.cmd_skill_usage(["pin"]) == 1

    def test_unknown_action(self, home: Path):
        assert skill_usage_cli.cmd_skill_usage(["frobnicate"]) == 1
        assert skill_usage_cli.cmd_skill_usage([]) == 1

    def test_report_runs_against_a_workspace(self, workspace: Path):
        skills = workspace / ".ai-cli" / "shared" / "skills"
        skills.mkdir(parents=True)
        _make_skill(skills, "kitt-a")
        assert skill_usage_cli.cmd_skill_usage(["report"], workspace) == 0
        assert "kitt-a" in _skill_usage.load_usage()

    def test_installed_skill_names_reads_the_shared_dir(self, workspace: Path):
        skills = workspace / ".ai-cli" / "shared" / "skills"
        skills.mkdir(parents=True)
        _make_skill(skills, "kitt-a")
        (skills / "not-a-skill").mkdir()
        assert skill_usage_cli.installed_skill_names(workspace) == ["kitt-a"]
