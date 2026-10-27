"""Structural routing-eval harness: does each skill's description still win?

Ported idea from gbrain's ``skills/brain-taxonomist/routing-eval.jsonl`` +
``src/core/routing-eval.ts`` (Check 5 of its "skillify checklist"): a JSONL
fixture of ``intent -> expected_skill`` pairs asserting that, given a user's
natural-language request, the skill whose description should fire is the
one that actually would. This is WOPR's first efficacy measurement of any
kind — everything else in the test suite checks that WOPR's *mechanics*
work (files land in the right place, conversions round-trip); nothing
until now checked whether the *content* WOPR ships routes correctly.

CRITICAL SCOPE — read this before trusting a "pass" from this module
----------------------------------------------------------------------
There is no model in the loop here, in CI or anywhere else in this
module. Real routing — whether Claude Code, Copilot CLI, or Gemini CLI
actually invokes a skill for a given user message — is decided by each
CLI's own model reading the skill's frontmatter ``description`` (and,
for some CLIs, the whole catalog of installed descriptions at once).
This module cannot observe or reproduce that decision offline.

What this module CAN honestly assert, and does:

- **Structural/lexical match** (``structural_route_match``): does the
  intent's text lexically overlap with trigger phrases pulled out of the
  skill's own description? This is "Layer A" in gbrain's own framing —
  a no-model substring check — ported directly, not reinvented.
- **Description uniqueness** (``find_duplicate_descriptions``): do any two
  skills in the catalog have the literal same (normalized) description?
  If so, no model — however good — can prefer one over the other on
  content alone.
- **Ambiguity/collision detection**: does an intent's trigger phrases
  collide across more than one skill's description, absent an explicit
  ``ambiguous_with`` allow-list entry?
- **Fixture hygiene** (``lint_routing_fixtures``): is a fixture actually
  testing something, or did the author copy-paste the skill's own
  trigger phrase into the intent (a tautology that would "pass" no
  matter how bad routing actually is)?

None of this proves a model will route correctly. It proves the
lexical surface a model would have to read is unambiguous and that the
fixture claiming to test it isn't a tautology. That is a real, useful,
and MUCH weaker guarantee than "routing is verified" — this module and
its tests are named and documented to avoid implying otherwise.

Layer B (model-in-the-loop tie-break) is intentionally NOT built here,
same as upstream gbrain (its own ``--llm`` flag is accepted but not yet
wired to a model). ``run_routing_eval`` takes a ``matcher`` callable
defaulting to :func:`structural_route_match` specifically so a future
model-backed matcher can be substituted without changing the fixture
format, the report shape, or any call site — the seam gbrain's own
docstring says its CLI is "ready" for but hasn't built either.

Trigger-phrase extraction, adapted for prose
---------------------------------------------
gbrain has a dedicated ``RESOLVER.md`` table: one row per skill, an
explicit trigger-phrase cell. WOPR has no such table — the routing
signal a real CLI reads is the ``description:`` field in each skill's
own frontmatter, written as prose. :func:`extract_trigger_phrases`
adapts gbrain's algorithm (normalize, split on quoted phrases or commas)
to that prose: it looks for an explicit "use when / use for / activate
when / ..." cue phrase (a convention already followed by most of the
catalog — see the module-level ``_POSITIVE_CUES`` list) and splits the
clause that follows on commas/" or ". Sentences containing a negative
cue ("do not use for", "not for", ...) are skipped entirely rather than
mined for triggers, so a skill's own disambiguation notes about a
*different* skill don't get attributed to it.

A skill whose description has no recognizable cue phrase yields an
empty trigger list — it simply doesn't participate in structural
matching, the same way a skill missing from gbrain's resolver table
doesn't participate in its structural layer. That is a real, disclosed
coverage gap (see ``docs/llms.txt`` and the WOPR test suite for the
current count), not silently-total coverage.

Within a trigger clause, gbrain's own dual-mode extraction is kept
intact: if the clause contains double-quoted substrings (as in "Use
when ... to "make a skill for this", or ..." — an actual phrase from
the catalog), those quoted phrases are used verbatim as the atomic
triggers and any surrounding prose in that clause is ignored; otherwise
the whole clause is split on commas/" or " the same way a RESOLVER cell
would be.
"""

from __future__ import annotations

import json
import re
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal

from ..converters import parse_claude

# ---------------------------------------------------------------------------
# Normalization + trigger extraction
# ---------------------------------------------------------------------------

_NON_ALNUM = re.compile(r"[^a-z0-9]+")
_SENTENCE_SPLIT = re.compile(r"(?<=[.!?])\s+")
_OR_SPLIT = re.compile(r"\bor\b")
_QUOTED = re.compile(r'"([^"]+)"')

# Cue phrases that introduce a positive trigger clause in a skill
# description, drawn from the conventions actually in use across the
# catalog today ("Use when...", "Use for...", "Use before the first crew
# run...", "USE FOR: ...", "Activate when...").
_POSITIVE_CUES: tuple[str, ...] = (
    "use when",
    "use for",
    "used for",
    "use before",
    "use after",
    "use to",
    "use this",
    "use in",
    "use during",
    "activate when",
    "activates when",
    "invoke when",
    "invoke this",
    "triggers on",
    "trigger:",
)

# Markers that mean a sentence is disambiguation prose about NOT firing
# (often pointing at a different skill entirely: "DO NOT USE FOR: X (use
# other-skill instead)"). Sentences containing one of these are excluded
# from trigger extraction rather than mined — see module docstring.
_NEGATIVE_MARKERS: tuple[str, ...] = (
    "do not use",
    "don't use",
    "not for",
    "avoid using",
    "never use",
    "only activate",
)

_MIN_PHRASE_LEN = 3  # mirrors gbrain's extractTriggerPhrases threshold

# A comma-separated list inside a sentence isn't always a list of
# independent trigger phrases — "adding /bl to any dotnet build, test,
# pack, publish, or restore command" is grammatically one clause whose
# commas separate VERBS, not standalone triggers. Splitting it naively
# yields single common words ("test", "pack") that would false-positive
# against nearly anything. Multi-word fragments (the common case, e.g.
# "working with subagents") keep the lower threshold; a single-word
# fragment must be long enough to be a distinctive term rather than an
# ordinary short word (this is a coarse proxy, not a stopword list, and
# it's a real limitation of no-model lexical extraction — see module
# docstring).
_MIN_SINGLE_WORD_PHRASE_LEN = 6


def normalize_text(s: str) -> str:
    """Lowercase, collapse non-alphanumerics to single spaces, trim.

    Direct port of gbrain's ``normalizeText``: aggressive punctuation
    stripping so quote/dash/question-mark variants compare equal.
    """
    if not s:
        return ""
    return _NON_ALNUM.sub(" ", s.lower()).strip()


def extract_trigger_phrases(description: str) -> list[str]:
    """Pull candidate trigger phrases out of a skill's prose description.

    Returns an empty list if no recognized positive cue phrase is found —
    see the module docstring for why that's a disclosed gap, not a bug.
    """
    if not description:
        return []

    phrases: list[str] = []
    for sentence in _SENTENCE_SPLIT.split(description):
        lowered = sentence.lower()
        if any(marker in lowered for marker in _NEGATIVE_MARKERS):
            continue
        for cue in _POSITIVE_CUES:
            idx = lowered.find(cue)
            if idx == -1:
                continue
            clause = sentence[idx + len(cue):]
            quoted = _QUOTED.findall(clause)
            sources = quoted if quoted else _OR_SPLIT.split(clause)
            fragments = sources if quoted else [
                part for fragment in sources for part in fragment.split(",")
            ]
            for fragment in fragments:
                normalized = normalize_text(fragment)
                threshold = (
                    _MIN_PHRASE_LEN if " " in normalized else _MIN_SINGLE_WORD_PHRASE_LEN
                )
                if len(normalized) >= threshold:
                    phrases.append(normalized)
            break  # one cue per sentence is enough
    return phrases


# ---------------------------------------------------------------------------
# Catalog scanning
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class CatalogSkill:
    """One skill discovered in the catalog: identity + routing surface."""

    name: str
    description: str
    path: Path


def scan_catalog_skills(catalog_root: Path) -> list[CatalogSkill]:
    """Walk ``catalog_root`` for every ``SKILL.md`` and parse its frontmatter.

    Identity is the frontmatter ``name`` field (falling back to the
    parent directory name), matching how the rest of WOPR treats skill
    identity (``resources.list_shared_skills`` keys by directory name;
    fixtures written against this harness should use the same value).
    """
    if not catalog_root.exists():
        return []
    skills: list[CatalogSkill] = []
    for skill_file in sorted(catalog_root.rglob("SKILL.md")):
        try:
            content = skill_file.read_text(encoding="utf-8")
        except OSError:
            continue
        doc = parse_claude(content)
        name = doc.frontmatter.get("name") or skill_file.parent.name
        description = doc.frontmatter.get("description") or ""
        skills.append(CatalogSkill(name=name, description=description, path=skill_file))
    return skills


def find_duplicate_descriptions(
    skills: list[CatalogSkill],
) -> list[tuple[str, str, str]]:
    """Return ``(skill_a, skill_b, normalized_description)`` for exact dupes.

    Only catches byte-for-byte (post-normalization) duplicates —
    deliberately not fuzzy/paraphrase similarity, which would need an
    embedding model or LLM judge to do honestly (see module docstring).
    An exact duplicate is still a real, serious finding: no routing
    mechanism, model or otherwise, can prefer one skill over another on
    content alone if their descriptions are identical.
    """
    seen: dict[str, str] = {}
    dupes: list[tuple[str, str, str]] = []
    for skill in skills:
        normalized = normalize_text(skill.description)
        if not normalized:
            continue
        if normalized in seen:
            dupes.append((seen[normalized], skill.name, normalized))
        else:
            seen[normalized] = skill.name
    return dupes


# ---------------------------------------------------------------------------
# Trigger index + structural match
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class TriggerIndex:
    """Skill name -> extracted trigger phrases, plus the full skill set."""

    skill_phrases: dict[str, list[str]]
    known_skills: frozenset[str]


def build_trigger_index(skills: list[CatalogSkill]) -> TriggerIndex:
    skill_phrases = {
        skill.name: extract_trigger_phrases(skill.description) for skill in skills
    }
    return TriggerIndex(
        skill_phrases=skill_phrases,
        known_skills=frozenset(skill.name for skill in skills),
    )


@dataclass(frozen=True)
class StructuralMatchResult:
    matched: list[str]
    ambiguous: bool


def structural_route_match(intent: str, index: TriggerIndex) -> StructuralMatchResult:
    """Layer A: which skills' trigger phrases are substrings of the intent.

    No model. Direct port of gbrain's ``structuralRouteMatch``, minus the
    hardcoded "always-on skills" exemption — WOPR has no equivalent
    concept baked into the catalog, so legitimate co-firing is declared
    per-fixture via ``ambiguous_with`` instead (see :func:`run_routing_eval`).
    """
    normalized_intent = normalize_text(intent)
    matched = [
        slug
        for slug, phrases in index.skill_phrases.items()
        if any(phrase and phrase in normalized_intent for phrase in phrases)
    ]
    return StructuralMatchResult(matched=matched, ambiguous=len(matched) > 1)


# ---------------------------------------------------------------------------
# Fixtures: shape, loading, linting
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class RoutingFixture:
    """One ``intent -> expected_skill`` case from a ``routing-eval.jsonl``.

    ``expected_skill=None`` is a negative case: nothing should fire.
    ``ambiguous_with`` allow-lists other skills this intent may
    legitimately also match without being flagged ambiguous.
    """

    intent: str
    expected_skill: str | None
    ambiguous_with: tuple[str, ...] = ()
    source: str | None = None


@dataclass(frozen=True)
class MalformedFixtureLine:
    file: str
    line: int
    raw: str
    error: str


@dataclass(frozen=True)
class LoadResult:
    fixtures: list[RoutingFixture]
    malformed: list[MalformedFixtureLine]


def load_routing_fixtures(catalog_root: Path) -> LoadResult:
    """Walk ``catalog_root`` for every ``routing-eval.jsonl`` and parse it.

    JSONL: one JSON object per non-empty, non-comment (``//`` or ``#``)
    line. Malformed lines are collected rather than raising, so one bad
    line doesn't hide every other fixture in the file — mirrors gbrain's
    ``loadRoutingFixtures``.
    """
    fixtures: list[RoutingFixture] = []
    malformed: list[MalformedFixtureLine] = []
    if not catalog_root.exists():
        return LoadResult(fixtures=fixtures, malformed=malformed)

    for fixture_path in sorted(catalog_root.rglob("routing-eval.jsonl")):
        try:
            content = fixture_path.read_text(encoding="utf-8")
        except OSError:
            continue
        for i, raw_line in enumerate(content.splitlines(), start=1):
            raw = raw_line.strip()
            if not raw or raw.startswith("//") or raw.startswith("#"):
                continue
            try:
                obj = json.loads(raw)
            except json.JSONDecodeError as e:
                malformed.append(
                    MalformedFixtureLine(file=str(fixture_path), line=i, raw=raw, error=str(e))
                )
                continue
            if not isinstance(obj, dict) or not isinstance(obj.get("intent"), str):
                keys = ", ".join(obj.keys()) if isinstance(obj, dict) else type(obj).__name__
                malformed.append(
                    MalformedFixtureLine(
                        file=str(fixture_path),
                        line=i,
                        raw=raw,
                        error=f"missing required field 'intent' (found keys: {keys})",
                    )
                )
                continue
            fixtures.append(
                RoutingFixture(
                    intent=obj["intent"],
                    expected_skill=obj.get("expected_skill"),
                    ambiguous_with=tuple(obj.get("ambiguous_with", []) or []),
                    source=str(fixture_path),
                )
            )
    return LoadResult(fixtures=fixtures, malformed=malformed)


@dataclass(frozen=True)
class FixtureLintIssue:
    fixture: RoutingFixture
    reason: Literal["intent_copies_trigger", "unknown_expected_skill", "invalid_shape"]
    detail: str


def lint_routing_fixtures(
    fixtures: list[RoutingFixture], index: TriggerIndex
) -> list[FixtureLintIssue]:
    """D-CX-6 equivalent: reject fixtures that can't actually fail.

    - ``invalid_shape``: empty/blank intent.
    - ``unknown_expected_skill``: ``expected_skill`` isn't a real skill in
      the index (typo, renamed/removed skill, dead fixture).
    - ``intent_copies_trigger``: the normalized intent is VERBATIM one of
      the expected skill's own trigger phrases — a copy-paste tautology
      that would pass regardless of whether routing actually works.
      Fixtures embedding trigger words in a natural sentence are fine and
      NOT flagged; only exact equality is a tautology (mirrors gbrain's
      own linter, which draws the identical line for the identical
      reason — Layer A's whole mechanism is substring match, so a
      fixture merely containing a trigger word is exactly what it's
      supposed to detect).
    """
    issues: list[FixtureLintIssue] = []
    for fixture in fixtures:
        if not fixture.intent or not fixture.intent.strip():
            issues.append(
                FixtureLintIssue(
                    fixture=fixture,
                    reason="invalid_shape",
                    detail="intent must be a non-empty string",
                )
            )
            continue
        if fixture.expected_skill is None:
            continue  # negative case: no trigger to copy
        if fixture.expected_skill not in index.known_skills:
            issues.append(
                FixtureLintIssue(
                    fixture=fixture,
                    reason="unknown_expected_skill",
                    detail=f"expected_skill '{fixture.expected_skill}' is not in the catalog",
                )
            )
            continue
        normalized_intent = normalize_text(fixture.intent)
        for phrase in index.skill_phrases.get(fixture.expected_skill, []):
            if phrase and normalized_intent == phrase:
                issues.append(
                    FixtureLintIssue(
                        fixture=fixture,
                        reason="intent_copies_trigger",
                        detail=f"intent is verbatim-identical to trigger phrase '{phrase}'",
                    )
                )
                break
    return issues


# ---------------------------------------------------------------------------
# Eval runner
# ---------------------------------------------------------------------------

RoutingOutcome = Literal["pass", "missed", "ambiguous", "false_positive"]

Matcher = Callable[[str, TriggerIndex], StructuralMatchResult]


@dataclass(frozen=True)
class RoutingCaseResult:
    fixture: RoutingFixture
    outcome: RoutingOutcome
    matched_skills: list[str]
    note: str = ""


@dataclass(frozen=True)
class RoutingReport:
    total_cases: int
    top1_accuracy: float  # 1.0 when total_cases == 0 (vacuous pass)
    passed: int
    missed: int
    ambiguous: int
    false_positives: int
    details: list[RoutingCaseResult] = field(default_factory=list)


def run_routing_eval(
    index: TriggerIndex,
    fixtures: list[RoutingFixture],
    matcher: Matcher = structural_route_match,
) -> RoutingReport:
    """Score every fixture against ``index`` using ``matcher``.

    ``matcher`` defaults to :func:`structural_route_match` (Layer A, no
    model). It exists as a parameter — not a hardcoded call — so a
    future Layer B (model-in-the-loop tie-break) can be plugged in
    without touching the fixture format, the report shape, or any of
    this scoring logic. No such matcher exists yet; see module docstring.
    """
    details: list[RoutingCaseResult] = []
    passed = missed = ambiguous = false_positives = 0

    for fixture in fixtures:
        result = matcher(fixture.intent, index)
        outcome: RoutingOutcome
        note = ""

        if fixture.expected_skill is None:
            if not result.matched:
                outcome = "pass"
                passed += 1
            else:
                outcome = "false_positive"
                false_positives += 1
                note = f"negative case unexpectedly matched: {', '.join(result.matched)}"
        elif fixture.expected_skill not in result.matched:
            outcome = "missed"
            missed += 1
            note = (
                f"matched instead: {', '.join(result.matched)}"
                if result.matched
                else "no matches"
            )
        else:
            allowed = {*fixture.ambiguous_with, fixture.expected_skill}
            unexpected = [s for s in result.matched if s not in allowed]
            if not unexpected:
                outcome = "pass"
                passed += 1
            else:
                outcome = "ambiguous"
                ambiguous += 1
                note = f"also matched: {', '.join(unexpected)}"

        details.append(
            RoutingCaseResult(
                fixture=fixture, outcome=outcome, matched_skills=result.matched, note=note
            )
        )

    total_cases = len(fixtures)
    top1_accuracy = 1.0 if total_cases == 0 else passed / total_cases

    return RoutingReport(
        total_cases=total_cases,
        top1_accuracy=top1_accuracy,
        passed=passed,
        missed=missed,
        ambiguous=ambiguous,
        false_positives=false_positives,
        details=details,
    )


def format_routing_report(report: RoutingReport) -> str:
    """Render a routing report as a compact, human-readable summary."""
    lines = [
        f"Routing eval (structural, no model): {report.passed}/{report.total_cases} passed "
        f"(top1={report.top1_accuracy:.2f}), {report.missed} missed, "
        f"{report.ambiguous} ambiguous, {report.false_positives} false positives",
    ]
    for case in report.details:
        if case.outcome == "pass":
            continue
        lines.append(
            f"  [{case.outcome.upper()}] {case.fixture.source or '(no source)'}: "
            f"{case.fixture.intent!r} expected={case.fixture.expected_skill!r} "
            f"— {case.note}"
        )
    return "\n".join(lines)
