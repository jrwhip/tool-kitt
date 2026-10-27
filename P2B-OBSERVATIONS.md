# P2B Observations: routing-eval fixture authoring

Findings recorded during the routing-eval fixture pass. Nothing in this
file has been acted on: per the task constraints, only
`catalog/**/routing-eval.jsonl` files were created or modified. Every
item below is a candidate for the content-slimming pass, not a change
already made.

## How the gate actually works (context for everything below)

`src/kitt/tools/_routing_eval.py` runs a no-model, lexical Layer A check:

1. `extract_trigger_phrases` reads each skill's frontmatter
   `description`, finds a sentence containing a recognized positive cue
   (`use when`, `use for`, `used for`, `use before`, `use after`,
   `use to`, `use this`, `use in`, `use during`, `activate when`,
   `activates when`, `invoke when`, `invoke this`, `triggers on`,
   `trigger:`), and splits the clause after the cue on commas and the
   word "or".
2. `structural_route_match` normalizes an intent (lowercase, all
   non-alphanumerics collapsed to spaces) and matches a skill if any of
   its trigger phrases is a **substring** of the normalized intent.
3. A positive fixture passes only if the expected skill matched and no
   other skill matched (unless allow-listed via `ambiguous_with`).
   A negative fixture (`expected_skill: null`) passes only if nothing
   in the whole catalog matched.

Two consequences that shape every fixture in this pass:

- A positive fixture must literally contain one of the skill's own
  trigger phrases. Paraphrase alone cannot pass. Positives are therefore
  natural sentences wrapped around the description's own wording.
- A skill whose description has no recognized cue phrase yields zero
  trigger phrases and can never match anything. It is invisible to the
  gate in the positive direction.

## 1. Six skills have zero trigger phrases and cannot be gated

These skills produce an empty trigger list, so no positive fixture for
them can pass today:

| Skill | Why it extracts nothing |
| --- | --- |
| `kitt-create-agent-instructions` | Description is all declarative prose ("Scaffold a project's agent-instructions files ..."); no cue phrase. |
| `kitt-create-yml` | Same: "Scaffold a `kitt.yml` at a specified path ..."; no cue phrase. |
| `kitt-init-project` | Same: "One-shot umbrella skill that takes a project from ..."; no cue phrase. |
| `kitt-angular-developer` | Says "**Trigger when** creating projects, components, or services, ...". The cue list recognizes `triggers on` and `trigger:` but **not** `trigger when`. One word away from working. |
| `kitt-build-angular-apps` | Declarative feature list; no cue phrase. |
| `build-python-services` | Declarative feature list; no cue phrase. |

Evidence that this is a real blind spot, not a theoretical one: blanking
each skill's description one at a time and re-running the full fixture
set gives 0 newly-missed cases for all six, versus 5 to 8 newly-missed
cases for each of the eleven cue-bearing skills. The gate has teeth for
eleven skills and none for six.

What was authored for those six instead: a fixture file per skill with
six genuinely-out-of-domain negative cases (which do have value, since
they catch a slimming pass that over-broadens some other description),
plus four **parked** positive cases written as `//` comment lines. The
loader skips comment lines, so they do not run. They are the intents
that should route to the skill, ready to uncomment the moment the
description gains a cue clause.

**Recommended for the slimming pass:** add a "Use when ..." clause to
each of these six descriptions and uncomment the parked positives. For
`kitt-angular-developer`, the cheapest possible fix is changing
"Trigger when" to "Use when" (or adding `trigger when` to
`_POSITIVE_CUES`, which is a source change and therefore out of scope
here).

## 2. `kitt-create-plans` has a dangerously broad single-word trigger

The description clause "Use when planning projects, phases, or tasks
that the AI agent will execute" splits into three phrases, one of which
is the bare word `phases`. Six characters is exactly the
`_MIN_SINGLE_WORD_PHRASE_LEN` threshold, so it survives filtering.

Verified false positives against the live catalog:

- `explain the moon phases to my kid` matches `kitt-create-plans`
- `the disease progresses in phases` matches `kitt-create-plans`
- `skip the intro phases of onboarding` matches `kitt-create-plans`

These were deliberately **not** committed as fixtures, because they
would fail. They are recorded here as a real routing defect. Rewording
the clause (for example "Use when planning projects, mapping delivery
phases, or breaking work into tasks that the AI agent will execute")
would eliminate the bare `phases` token while keeping the meaning.

## 3. `kitt-run-crew`'s first trigger phrase is unusable in practice

The description reads:

> Use for any disciplined dev work on a project configured with
> `kitt.yml`: net-new feature implementation, ongoing iteration ...

Because the colon is normalized to a space rather than treated as a
clause boundary, the first extracted phrase is the 100-plus character
run-on `any disciplined dev work on a project configured with kitt yml
net new feature implementation`. No developer types that, so no honest
fixture can embed it. The other four phrases from that description
(`ongoing iteration on an existing project`, `addressing auditor
blockers`, `handing off a backend change to a frontend track`, `running
a legacy migration`) are usable and carry all six positives.

Splitting that sentence so "net-new feature implementation" is its own
list item would recover a fifth usable trigger.

## 4. Descriptions that force stilted positives

Three skills have trigger phrases that are single long clauses rather
than short handles, which makes natural-sounding positives hard:

- `kitt-create-meta-prompts`: only two phrases, both long
  (`building prompts that produce outputs for other prompts to consume`
  and `when running multi stage workflows research plan implement`).
  Every positive is a sentence built around one of them.
- `kitt-doctor`: `any time the agent wants to confirm a project is
  correctly wired for kitt` is a whole sentence, not a trigger.
- `kitt-debug-like-expert`: `when issues require systematic root cause
  analysis` includes the leading "when", which forces awkward
  constructions like "one of those when issues require ... moments".

Not defects exactly, but a signal: descriptions written as prose
explanations route worse than descriptions written as short trigger
handles. Worth considering during slimming.

## 5. Two Angular skills overlap and neither is routable

`kitt-angular-developer` and `kitt-build-angular-apps` cover
substantially the same ground (Angular architecture, signals, component
patterns). Neither has a cue phrase, so the gate cannot detect the
collision today. `find_duplicate_descriptions` also will not flag them,
since it only catches byte-identical descriptions. If both get cue
clauses during slimming without also being made mutually distinct, they
will collide and produce `ambiguous` outcomes. They need explicit
division of labor in their descriptions ("generating new Angular code"
versus "reviewing or migrating an existing Angular app", or similar).

## 6. Naming inconsistency

`build-python-services` is the only skill in the catalog without the
`kitt-` prefix. `kitt-build-angular-apps` is the direct analogue and
does carry the prefix. Cosmetic, but it affects the fixture
`expected_skill` values and anything else keyed by skill name, so it is
cheaper to fix before more references accumulate than after.

## 7. `catalog/auditors` ships no skills

That pack contains only `agents/` and `commands/`. `scan_catalog_skills`
walks for `SKILL.md`, so the pack contributes nothing to routing and
needs no fixtures. Noted so a future reader does not go looking for a
missing seventh fixture file there.

## 8. Unrelated pre-existing test failure in `tests/test_converters.py`

Running the full suite during verification surfaced one failure that has
nothing to do with routing fixtures, reported here rather than fixed
because source and test files were out of scope:

```
FAILED tests/test_converters.py::TestToCopilotSkill::test_consider_command_gets_disable_model_invocation
KeyError: 'disable-model-invocation'
```

The test calls `to_copilot_skill(content, "kitt-consider-pareto")` and
expects the `disable-model-invocation` flag. `to_copilot_skill` sets that
flag only when the resource name is in
`EXPLICIT_INVOCATION_ONLY_COMMANDS`, which is
`frozenset({"kitt-consider", "kitt-realign"})` in
`src/kitt/conversion_manifest.py`. A comment right above that frozenset
says the `kitt-consider-*` commands were collapsed into a single
`kitt-consider`, so the test is asserting against the pre-collapse name.
The fix is almost certainly to update the test to use `kitt-consider`,
but that is a judgment call for whoever owns that consolidation.

`tests/test_routing_eval.py` passes fully (45 passed), as does the rest
of the suite (547 passed, 1 skipped, this 1 failure).

## 9. Pre-existing fixtures were thin, not wrong

The ten fixture files that crossed over from the quarry each had exactly
three cases (typically two positive, one negative) and their negatives
were all far-field ("check the color contrast on this hero banner",
"deploy this branch to staging"). Every pre-existing case was kept
verbatim; none needed correction. What they lacked was near-miss
negatives and cross-skill discrimination, which this pass added.
