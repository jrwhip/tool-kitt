"""Tests for the per-role crew model resolver.

The resolver is the one place that decides which model each crew role
runs on for a requirement. These tests pin the contract the
orchestrator skill relies on:

* With no ``crew`` section every role gets the default from the agent
  files, and nothing moves.
* Complexity is read in precedence order: operator argument, then the
  requirement's frontmatter, then the scout contract's file count,
  then ``medium``.
* ``high`` moves only the escalation roles up one tier; ``low`` moves
  them down one tier; the ladder is clamped at both ends; roles
  outside the list never move.
* ``inherit`` and unknown roles are errors, because a role that copies
  another role's model is exactly what this tool exists to prevent.
* A value off the ladder (a pinned model id) is honored as given and
  never escalated.
"""

from __future__ import annotations

import json
from pathlib import Path

from kitt.tools import crew_models
from kitt.tools.crew_models import resolve_crew_models

# ``fake_mcp`` fixture lives in tests/conftest.py.


def _write(path: Path, text: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


def _kitt_yml(tmp_path: Path, crew_block: str = "") -> Path:
    body = (
        "project:\n  slug: demo\n  name: Demo\n  target_source_root: src\n"
        "  test_root: tests\n  build_file: package.json\n"
    )
    return _write(tmp_path / "kitt.yml", body + crew_block)


def _req(tmp_path: Path, complexity: str | None = None, *, frontmatter: bool = True) -> Path:
    lines = ["---", "id: REQ-X-1", "title: Do a thing", "status: pending"]
    if complexity is not None:
        lines.append(f"complexity: {complexity}")
    lines.append("---")
    text = ("\n".join(lines) + "\n" if frontmatter else "") + "## Requirement\n\nA thing.\n"
    return _write(tmp_path / "requirements" / "REQ-X-1.md", text)


def _contract(tmp_path: Path, files: int) -> Path:
    entries = "\n".join(f"  - src/file{i}.ts" for i in range(files)) or "  []"
    text = (
        "---\nreq_id: REQ-X-1\ngenerated_at: 2026-10-28T00:00:00Z\n"
        f"files_touched:\n{entries}\nclass_inventory: []\n"
        "package_structure: src/\n---\n\n## Notes\n"
    )
    return _write(tmp_path / "crew-contracts" / "REQ-X-1" / "scout.md", text)


def _resolve(**kwargs: str) -> dict:
    return json.loads(resolve_crew_models(**kwargs))


class TestDefaults:
    def test_no_crew_section_uses_the_agent_file_defaults(self, tmp_path: Path):
        result = _resolve(kitt_yml_path=str(_kitt_yml(tmp_path)))
        assert result["ok"] is True
        assert result["complexity"] == "medium"
        assert result["complexity_source"] == "default"
        assert result["models"] == crew_models.DEFAULT_MODELS
        assert result["adjusted_roles"] == []

    def test_defaults_mirror_the_agent_frontmatter(self):
        agents = Path(__file__).resolve().parents[1] / "catalog" / "crew" / "agents"
        for role, model in crew_models.DEFAULT_MODELS.items():
            text = (agents / f"kitt-crew-{role}.md").read_text(encoding="utf-8")
            assert f"\nmodel: {model}\n" in text, f"{role}: agent file and DEFAULT_MODELS disagree"

    def test_configured_models_override_the_defaults(self, tmp_path: Path):
        yml = _kitt_yml(tmp_path, "crew:\n  models:\n    scout: sonnet\n    coder: opus\n")
        result = _resolve(kitt_yml_path=str(yml))
        assert result["ok"] is True
        assert result["models"]["scout"] == "sonnet"
        assert result["models"]["coder"] == "opus"
        assert result["models"]["tester"] == "sonnet"


class TestComplexitySources:
    def test_operator_argument_wins_over_everything(self, tmp_path: Path):
        yml = _kitt_yml(tmp_path)
        result = _resolve(
            kitt_yml_path=str(yml),
            req_path=str(_req(tmp_path, "low")),
            scout_contract_path=str(_contract(tmp_path, 12)),
            complexity="high",
        )
        assert result["complexity"] == "high"
        assert result["complexity_source"] == "operator"
        assert result["files_touched"] == 12

    def test_req_frontmatter_wins_over_the_contract_count(self, tmp_path: Path):
        yml = _kitt_yml(tmp_path)
        result = _resolve(
            kitt_yml_path=str(yml),
            req_path=str(_req(tmp_path, "low")),
            scout_contract_path=str(_contract(tmp_path, 12)),
        )
        assert result["complexity"] == "low"
        assert result["complexity_source"] == "req_frontmatter"

    def test_contract_count_at_or_above_threshold_is_high(self, tmp_path: Path):
        yml = _kitt_yml(tmp_path)
        result = _resolve(
            kitt_yml_path=str(yml),
            req_path=str(_req(tmp_path)),
            scout_contract_path=str(_contract(tmp_path, crew_models.DEFAULT_HIGH_AT_FILES)),
        )
        assert result["complexity"] == "high"
        assert result["complexity_source"] == "scout_contract"
        assert result["files_touched"] == crew_models.DEFAULT_HIGH_AT_FILES

    def test_contract_count_below_threshold_stays_medium(self, tmp_path: Path):
        yml = _kitt_yml(tmp_path)
        result = _resolve(kitt_yml_path=str(yml), scout_contract_path=str(_contract(tmp_path, 2)))
        assert result["complexity"] == "medium"
        assert result["complexity_source"] == "default"
        assert result["adjusted_roles"] == []

    def test_low_threshold_is_off_unless_configured(self, tmp_path: Path):
        yml = _kitt_yml(tmp_path)
        result = _resolve(kitt_yml_path=str(yml), scout_contract_path=str(_contract(tmp_path, 1)))
        assert result["complexity"] == "medium"

        yml = _kitt_yml(tmp_path, "crew:\n  escalation:\n    low_at_files: 1\n")
        result = _resolve(kitt_yml_path=str(yml), scout_contract_path=str(_contract(tmp_path, 1)))
        assert result["complexity"] == "low"
        assert result["complexity_source"] == "scout_contract"

    def test_req_without_frontmatter_or_field_is_ignored(self, tmp_path: Path):
        yml = _kitt_yml(tmp_path)
        assert _resolve(kitt_yml_path=str(yml), req_path=str(_req(tmp_path, frontmatter=False)))[
            "ok"
        ]
        assert (
            _resolve(kitt_yml_path=str(yml), req_path=str(_req(tmp_path)))["complexity"] == "medium"
        )

    def test_bad_complexity_values_are_errors(self, tmp_path: Path):
        yml = _kitt_yml(tmp_path)
        result = _resolve(kitt_yml_path=str(yml), complexity="extreme")
        assert result["ok"] is False
        assert any("complexity must be one of" in e for e in result["errors"])
        result = _resolve(kitt_yml_path=str(yml), req_path=str(_req(tmp_path, "huge")))
        assert result["ok"] is False
        assert any("`complexity` must be one of" in e for e in result["errors"])


class TestEscalation:
    def test_high_moves_only_the_escalation_roles_up_one_tier(self, tmp_path: Path):
        result = _resolve(kitt_yml_path=str(_kitt_yml(tmp_path)), complexity="high")
        assert result["models"]["coder"] == "opus"
        assert result["models"]["auditor"] == "opus"
        assert result["models"]["tester"] == "sonnet"
        assert result["models"]["scout"] == "haiku"
        assert sorted(result["adjusted_roles"]) == ["auditor", "coder"]

    def test_low_moves_the_escalation_roles_down_one_tier(self, tmp_path: Path):
        result = _resolve(kitt_yml_path=str(_kitt_yml(tmp_path)), complexity="low")
        assert result["models"]["coder"] == "haiku"
        assert result["models"]["auditor"] == "haiku"
        assert result["models"]["scout"] == "haiku"

    def test_the_ladder_is_clamped_at_both_ends(self, tmp_path: Path):
        yml = _kitt_yml(tmp_path, "crew:\n  models:\n    coder: opus\n    auditor: haiku\n")
        high = _resolve(kitt_yml_path=str(yml), complexity="high")
        assert high["models"]["coder"] == "opus"
        assert "coder" not in high["adjusted_roles"]
        low = _resolve(kitt_yml_path=str(yml), complexity="low")
        assert low["models"]["auditor"] == "haiku"
        assert "auditor" not in low["adjusted_roles"]

    def test_configured_roles_replace_the_default_list(self, tmp_path: Path):
        yml = _kitt_yml(tmp_path, "crew:\n  escalation:\n    roles: [tester]\n")
        result = _resolve(kitt_yml_path=str(yml), complexity="high")
        assert result["models"]["tester"] == "opus"
        assert result["models"]["coder"] == "sonnet"
        assert result["adjusted_roles"] == ["tester"]

    def test_the_scout_escalates_only_when_listed(self, tmp_path: Path):
        yml = _kitt_yml(tmp_path, "crew:\n  escalation:\n    roles: [scout, coder]\n")
        result = _resolve(kitt_yml_path=str(yml), complexity="high")
        assert result["models"]["scout"] == "sonnet"

    def test_a_pinned_model_id_is_used_as_given_and_never_escalated(self, tmp_path: Path):
        yml = _kitt_yml(tmp_path, "crew:\n  models:\n    coder: claude-sonnet-4-5-20250929\n")
        result = _resolve(kitt_yml_path=str(yml), complexity="high")
        assert result["ok"] is True
        assert result["models"]["coder"] == "claude-sonnet-4-5-20250929"
        assert "coder" not in result["adjusted_roles"]
        assert any("not on the ladder" in w for w in result["warnings"])


class TestConfigErrors:
    def test_inherit_is_refused(self, tmp_path: Path):
        yml = _kitt_yml(tmp_path, "crew:\n  models:\n    scout: inherit\n")
        result = _resolve(kitt_yml_path=str(yml))
        assert result["ok"] is False
        assert any("`inherit` is not allowed" in e for e in result["errors"])
        assert result["models"]["scout"] == "haiku"

    def test_unknown_role_is_an_error(self, tmp_path: Path):
        yml = _kitt_yml(tmp_path, "crew:\n  models:\n    reviewer: opus\n")
        result = _resolve(kitt_yml_path=str(yml))
        assert result["ok"] is False
        assert any("unknown role" in e for e in result["errors"])

    def test_bad_thresholds_are_errors(self, tmp_path: Path):
        yml = _kitt_yml(tmp_path, "crew:\n  escalation:\n    high_at_files: three\n")
        assert _resolve(kitt_yml_path=str(yml))["ok"] is False
        yml = _kitt_yml(
            tmp_path, "crew:\n  escalation:\n    high_at_files: 2\n    low_at_files: 2\n"
        )
        result = _resolve(kitt_yml_path=str(yml))
        assert result["ok"] is False
        assert any("must be less than" in e for e in result["errors"])

    def test_missing_or_relative_kitt_yml_is_an_error(self, tmp_path: Path):
        assert _resolve(kitt_yml_path=str(tmp_path / "nope" / "kitt.yml"))["ok"] is False
        assert _resolve(kitt_yml_path="kitt.yml")["ok"] is False

    def test_missing_contract_is_an_error_but_models_still_resolve(self, tmp_path: Path):
        yml = _kitt_yml(tmp_path)
        result = _resolve(kitt_yml_path=str(yml), scout_contract_path=str(tmp_path / "missing.md"))
        assert result["ok"] is False
        assert result["models"] == crew_models.DEFAULT_MODELS


class TestRegistration:
    def test_registers_the_resolver(self, fake_mcp):
        crew_models.register(fake_mcp)
        assert fake_mcp.registered == ["resolve_crew_models"]
