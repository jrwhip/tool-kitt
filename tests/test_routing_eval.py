"""Tests for ``wopr.tools._routing_eval``.

Two tiers, matching gbrain's own ``routing-eval.test.ts`` structure:

- Algorithm-level tests against synthetic skills/fixtures (this file's
  bulk) — covers normalization, trigger extraction, structural match,
  fixture linting, fixture loading, and the end-to-end scorer.
- A real-catalog integration tier (``TestRealCatalogIntegration``) that
  scans the actual ``catalog/`` directory in this repo: no duplicate
  descriptions catalog-wide, and every authored ``routing-eval.jsonl``
  fixture lints clean and scores 100% under Layer A structural matching.
  This is the "first efficacy measurement" gate item 4 asks for — see
  ``_routing_eval.py``'s module docstring for exactly what a pass here
  does and doesn't prove (no model is in the loop).
"""

from __future__ import annotations

from pathlib import Path

from wopr.tools._routing_eval import (
    CatalogSkill,
    RoutingFixture,
    build_trigger_index,
    extract_trigger_phrases,
    find_duplicate_descriptions,
    format_routing_report,
    lint_routing_fixtures,
    load_routing_fixtures,
    normalize_text,
    run_routing_eval,
    scan_catalog_skills,
    structural_route_match,
)

REPO_CATALOG_ROOT = Path(__file__).resolve().parent.parent / "catalog"


def _skill(name: str, description: str) -> CatalogSkill:
    return CatalogSkill(name=name, description=description, path=Path(f"{name}/SKILL.md"))


class TestNormalizeText:
    def test_lowercases_and_strips_punctuation(self):
        assert normalize_text("What's up?") == "what s up"

    def test_collapses_whitespace(self):
        assert normalize_text("  foo   bar\n\tbaz  ") == "foo bar baz"

    def test_empty_input(self):
        assert normalize_text("") == ""
        assert normalize_text("   !!  ") == ""


class TestExtractTriggerPhrases:
    def test_extracts_use_when_clause_split_on_commas(self):
        desc = (
            "Does the thing. Use when working with subagents, setting up configs, "
            "or launching agents."
        )
        phrases = extract_trigger_phrases(desc)
        assert "working with subagents" in phrases
        assert "setting up configs" in phrases
        assert "launching agents" in phrases

    def test_extracts_use_for_clause(self):
        desc = "Analyzes builds. USE FOR: diagnosing failures, tracing execution order."
        phrases = extract_trigger_phrases(desc)
        assert "diagnosing failures" in phrases
        assert "tracing execution order" in phrases

    def test_no_cue_phrase_yields_empty_list(self):
        desc = "Audit, fix, and design code against the OWASP Top 10."
        assert extract_trigger_phrases(desc) == []

    def test_skips_do_not_use_for_sentence(self):
        desc = (
            "Detects duplicate boilerplate. Use when reducing test duplication. "
            "DO NOT USE FOR: writing new tests, reviewing quality."
        )
        phrases = extract_trigger_phrases(desc)
        assert "reducing test duplication" in phrases
        assert not any("writing new tests" in p for p in phrases)
        assert not any("reviewing quality" in p for p in phrases)

    def test_filters_short_fragments(self):
        desc = "Does a thing. Use when x, doing something real."
        phrases = extract_trigger_phrases(desc)
        assert "x" not in phrases
        assert "doing something real" in phrases

    def test_empty_description(self):
        assert extract_trigger_phrases("") == []


class TestScanCatalogSkills:
    def _write_skill(self, tmp_path: Path, pack: str, slug: str, frontmatter_name: str, desc: str):
        skill_dir = tmp_path / pack / "skills" / slug
        skill_dir.mkdir(parents=True)
        (skill_dir / "SKILL.md").write_text(
            f"---\nname: {frontmatter_name}\ndescription: {desc}\n---\n\nBody.\n",
            encoding="utf-8",
        )

    def test_scans_nested_pack_skill_structure(self, tmp_path: Path):
        self._write_skill(tmp_path, "core", "foo", "foo", "Use when doing foo things.")
        self._write_skill(tmp_path, "core", "bar", "bar", "Use when doing bar things.")
        skills = scan_catalog_skills(tmp_path)
        assert {s.name for s in skills} == {"foo", "bar"}

    def test_falls_back_to_directory_name_without_frontmatter_name(self, tmp_path: Path):
        skill_dir = tmp_path / "core" / "skills" / "no-name-field"
        skill_dir.mkdir(parents=True)
        (skill_dir / "SKILL.md").write_text(
            "---\ndescription: something.\n---\nBody.\n", encoding="utf-8"
        )
        skills = scan_catalog_skills(tmp_path)
        assert skills[0].name == "no-name-field"

    def test_missing_catalog_root_returns_empty(self, tmp_path: Path):
        assert scan_catalog_skills(tmp_path / "nope") == []

    def test_only_reads_real_frontmatter_not_body_text(self, tmp_path: Path):
        # A skill whose BODY happens to contain an example "name: other"
        # block (e.g. a meta-authoring tutorial) must not be misread as
        # that other skill's identity — only the actual frontmatter counts.
        skill_dir = tmp_path / "core" / "skills" / "real-skill"
        skill_dir.mkdir(parents=True)
        (skill_dir / "SKILL.md").write_text(
            "---\nname: real-skill\ndescription: teaches examples.\n---\n\n"
            "Example frontmatter:\n```\nname: example-only\n```\n",
            encoding="utf-8",
        )
        skills = scan_catalog_skills(tmp_path)
        assert [s.name for s in skills] == ["real-skill"]


class TestFindDuplicateDescriptions:
    def test_no_duplicates(self):
        skills = [_skill("a", "does a things"), _skill("b", "does b things")]
        assert find_duplicate_descriptions(skills) == []

    def test_flags_exact_duplicate_after_normalization(self):
        skills = [
            _skill("a", "Does the same thing!"),
            _skill("b", "does the same thing"),
        ]
        dupes = find_duplicate_descriptions(skills)
        assert len(dupes) == 1
        assert {dupes[0][0], dupes[0][1]} == {"a", "b"}

    def test_ignores_empty_descriptions(self):
        skills = [_skill("a", ""), _skill("b", "")]
        assert find_duplicate_descriptions(skills) == []


class TestStructuralRouteMatch:
    def _index(self):
        skills = [
            _skill(
                "query",
                'Look things up. Use when you need to "search for" or "look up" a fact.',
            ),
            _skill(
                "citation-fixer",
                'Use when the user wants to "fix citations" in a doc.',
            ),
        ]
        return build_trigger_index(skills)

    def test_matches_unambiguous_intent(self):
        r = structural_route_match("please look up that person", self._index())
        assert r.matched == ["query"]
        assert r.ambiguous is False

    def test_out_of_scope_intent_matches_nothing(self):
        r = structural_route_match("deploy the app to prod", self._index())
        assert r.matched == []
        assert r.ambiguous is False

    def test_flags_ambiguity_when_two_skills_match(self):
        r = structural_route_match("search for and fix citations please", self._index())
        assert "query" in r.matched
        assert "citation-fixer" in r.matched
        assert r.ambiguous is True


class TestLintRoutingFixtures:
    def _index(self):
        skills = [
            _skill("query", 'Use when you want to "find me" something or "search for" a fact.'),
            _skill("citation-fixer", "Use when fixing broken citations."),
        ]
        return build_trigger_index(skills)

    def test_rejects_verbatim_copy_of_trigger(self):
        fixtures = [RoutingFixture(intent="find me", expected_skill="query")]
        issues = lint_routing_fixtures(fixtures, self._index())
        assert len(issues) == 1
        assert issues[0].reason == "intent_copies_trigger"

    def test_accepts_natural_sentence_embedding_trigger(self):
        fixtures = [RoutingFixture(intent="please find me that paper", expected_skill="query")]
        assert lint_routing_fixtures(fixtures, self._index()) == []

    def test_accepts_fully_paraphrased_fixture(self):
        fixtures = [
            RoutingFixture(intent="pull up what we know about paul", expected_skill="query")
        ]
        assert lint_routing_fixtures(fixtures, self._index()) == []

    def test_flags_unknown_expected_skill(self):
        fixtures = [RoutingFixture(intent="something", expected_skill="not-a-skill")]
        issues = lint_routing_fixtures(fixtures, self._index())
        assert len(issues) == 1
        assert issues[0].reason == "unknown_expected_skill"

    def test_skips_verbatim_check_for_negative_cases(self):
        fixtures = [RoutingFixture(intent="fixing broken citations", expected_skill=None)]
        assert lint_routing_fixtures(fixtures, self._index()) == []

    def test_flags_empty_intent(self):
        fixtures = [RoutingFixture(intent="", expected_skill="query")]
        issues = lint_routing_fixtures(fixtures, self._index())
        assert len(issues) == 1
        assert issues[0].reason == "invalid_shape"


class TestLoadRoutingFixtures:
    def _seed(self, root: Path, pack: str, slug: str, lines: list[str]):
        skill_dir = root / pack / "skills" / slug
        skill_dir.mkdir(parents=True)
        (skill_dir / "SKILL.md").write_text(f"---\nname: {slug}\n---\n", encoding="utf-8")
        (skill_dir / "routing-eval.jsonl").write_text("\n".join(lines), encoding="utf-8")

    def test_walks_and_parses_jsonl(self, tmp_path: Path):
        self._seed(
            tmp_path,
            "core",
            "query",
            [
                '{"intent":"lookup paul","expected_skill":"query"}',
                '{"intent":"find that doc","expected_skill":"query"}',
            ],
        )
        r = load_routing_fixtures(tmp_path)
        assert len(r.fixtures) == 2
        assert r.malformed == []
        assert all(f.source is not None for f in r.fixtures)

    def test_skips_comments_and_blank_lines(self, tmp_path: Path):
        self._seed(
            tmp_path,
            "core",
            "query",
            ["// comment", "", "# also comment", '{"intent":"lookup","expected_skill":"query"}'],
        )
        r = load_routing_fixtures(tmp_path)
        assert len(r.fixtures) == 1

    def test_collects_malformed_lines_without_crashing(self, tmp_path: Path):
        self._seed(
            tmp_path,
            "core",
            "query",
            [
                '{"intent":"ok","expected_skill":"query"}',
                "{ bad json",
                '{"intent":"also ok","expected_skill":"query"}',
            ],
        )
        r = load_routing_fixtures(tmp_path)
        assert len(r.fixtures) == 2
        assert len(r.malformed) == 1
        assert r.malformed[0].line == 2

    def test_missing_dir_returns_empty(self, tmp_path: Path):
        r = load_routing_fixtures(tmp_path / "never-exists")
        assert r.fixtures == []
        assert r.malformed == []

    def test_missing_intent_field_is_malformed(self, tmp_path: Path):
        self._seed(tmp_path, "core", "query", ['{"expected_skill":"query"}'])
        r = load_routing_fixtures(tmp_path)
        assert r.fixtures == []
        assert len(r.malformed) == 1


class TestRunRoutingEval:
    def _index(self):
        skills = [
            _skill(
                "query",
                'Use when you want to "find me" something, "search for" a fact, '
                'or "look up" a person.',
            ),
            _skill(
                "citation-fixer",
                'Use when you need "broken citations" fixed or "fix citations" in a doc.',
            ),
        ]
        return build_trigger_index(skills)

    def test_scores_a_passing_fixture(self):
        fixtures = [RoutingFixture(intent="please look up that person", expected_skill="query")]
        r = run_routing_eval(self._index(), fixtures)
        assert r.passed == 1
        assert r.top1_accuracy == 1
        assert r.details[0].outcome == "pass"

    def test_detects_a_missed_fixture(self):
        fixtures = [RoutingFixture(intent="deploy to prod", expected_skill="query")]
        r = run_routing_eval(self._index(), fixtures)
        assert r.missed == 1
        assert r.details[0].outcome == "missed"

    def test_detects_ambiguity(self):
        fixtures = [
            RoutingFixture(intent="search for broken citations", expected_skill="query")
        ]
        r = run_routing_eval(self._index(), fixtures)
        assert r.ambiguous == 1
        assert r.details[0].outcome == "ambiguous"
        assert "citation-fixer" in r.details[0].note

    def test_honors_ambiguous_with_allow_list(self):
        fixtures = [
            RoutingFixture(
                intent="search for broken citations",
                expected_skill="query",
                ambiguous_with=("citation-fixer",),
            )
        ]
        r = run_routing_eval(self._index(), fixtures)
        assert r.passed == 1
        assert r.ambiguous == 0

    def test_passes_a_negative_case(self):
        fixtures = [RoutingFixture(intent="deploy the app tonight", expected_skill=None)]
        r = run_routing_eval(self._index(), fixtures)
        assert r.passed == 1

    def test_fails_negative_case_on_false_positive(self):
        fixtures = [RoutingFixture(intent="please look up this fact", expected_skill=None)]
        r = run_routing_eval(self._index(), fixtures)
        assert r.false_positives == 1
        assert r.details[0].outcome == "false_positive"

    def test_empty_fixtures_is_vacuous_pass(self):
        r = run_routing_eval(self._index(), [])
        assert r.top1_accuracy == 1
        assert r.total_cases == 0

    def test_mixed_case_totals_add_up(self):
        fixtures = [
            RoutingFixture(intent="pull up paul graham", expected_skill=None),  # pass
            RoutingFixture(intent="deploy prod", expected_skill="query"),  # missed
            RoutingFixture(intent="fix broken citations", expected_skill=None),  # false pos
        ]
        r = run_routing_eval(self._index(), fixtures)
        assert r.total_cases == 3
        assert r.passed + r.missed + r.ambiguous + r.false_positives == 3


class TestFormatRoutingReport:
    def test_summarizes_totals(self):
        r = run_routing_eval(build_trigger_index([]), [])
        report = format_routing_report(r)
        assert "0/0 passed" in report

    def test_lists_non_passing_cases(self):
        index = build_trigger_index([_skill("query", "Use when searching for facts.")])
        fixtures = [RoutingFixture(intent="deploy to prod", expected_skill="query")]
        report = format_routing_report(run_routing_eval(index, fixtures))
        assert "MISSED" in report
        assert "deploy to prod" in report


class TestRealCatalogIntegration:
    """The actual CI gate: run the harness over this repo's real catalog."""

    def test_catalog_root_exists(self):
        assert REPO_CATALOG_ROOT.is_dir()

    def test_no_duplicate_descriptions_across_the_whole_catalog(self):
        skills = scan_catalog_skills(REPO_CATALOG_ROOT)
        assert skills, "expected to find skills under catalog/"
        dupes = find_duplicate_descriptions(skills)
        assert dupes == [], f"skills with identical descriptions: {dupes}"

    def test_authored_fixtures_load_without_malformed_lines(self):
        result = load_routing_fixtures(REPO_CATALOG_ROOT)
        assert result.malformed == []

    def test_authored_fixtures_lint_clean(self):
        skills = scan_catalog_skills(REPO_CATALOG_ROOT)
        index = build_trigger_index(skills)
        result = load_routing_fixtures(REPO_CATALOG_ROOT)
        issues = lint_routing_fixtures(result.fixtures, index)
        assert issues == [], f"fixture lint issues: {issues}"

    def test_authored_fixtures_score_perfectly_under_structural_match(self):
        skills = scan_catalog_skills(REPO_CATALOG_ROOT)
        index = build_trigger_index(skills)
        result = load_routing_fixtures(REPO_CATALOG_ROOT)
        assert result.fixtures, (
            "expected at least one routing-eval.jsonl fixture in the catalog"
        )
        report = run_routing_eval(index, result.fixtures)
        assert report.top1_accuracy == 1.0, format_routing_report(report)
