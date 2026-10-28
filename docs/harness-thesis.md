# The harness shrinks as the models grow: measured

Evidence document. The presentation's thesis is larger than this file: what is possible with AI now, and a wake-up call that the developer's job is supervision (context engineering, defined goals, solid plans, executable gates), not writing code. This file carries the measured facts for three of its beats: a harness can lose to naked Claude, done right the AI's code is genuinely good, and tools have a shelf life that only eval-gated maintenance extends.

Presentation source data. Every number in this document is reproducible from this repository (`evals/golden-req/`) or cited to a published Anthropic source. No number is estimated.

## Terminology: KITT is not the harness

Strictly, the harness is the runtime that owns the agent loop: context management, tool execution, permissions, model calls. That is Claude Code (or Gemini CLI, or Copilot). KITT ships no loop of its own; it is skills, subagents, MCP tools, and specs, all executed by the host harness, which is exactly why it can be cross-CLI. The accurate label for KITT is an orchestration and methodology layer, a harness extension: the crew (scout, coder, tester, auditor) is orchestration expressed through the harness's subagent mechanism, not an independent runtime. The defensible framing for the talk is "KITT turns a general-purpose harness into a disciplined one," not "KITT is a harness." This document uses "harness" loosely for the harness-plus-KITT stack because the shrink measurements apply to the layered whole; when precision matters on a slide, use the strict sense.

## The thesis in three sentences

A quality toolset multiplies what a strong model can do: structure, verification, and memory produce outcomes a bare model cannot guarantee. But a harness encodes assumptions about the model it was built for, and as models improve those assumptions become overhead, then become drag. So a harness is not an asset you build once; it is something you must re-measure and shrink as the models grow, and every cut must be gated on evidence, because terser is not automatically better.

## The story in one arc

KITT's crew orchestrator was designed in the pre-Claude-4.5 era: four separated agent roles, a corrective-RAG learning loop, and 473 lines of orchestration instruction that told the model things it needed to be told at the time. In August 2026 the orchestrator was rewritten for the Claude 5 era using Claude Code itself, with every change gated on a golden-requirement evaluation: the same small FastAPI feature (REQ-GOLD-1, an echo endpoint with validation, boundary cases, OpenAPI presence, and coverage floors) run through the crew before and after, twice each, plus a no-harness control.

## The data: one REQ, three harness sizes

All runs implement the identical requirement from the identical fixture. Crew runs use the models the skill assigns (scout on haiku; coder, tester, auditor on sonnet). Naked runs use a single sonnet agent, same tier as the crew's working agents, with only the requirement file, the code, and an instruction to deliver production quality.

| | Naked Claude (no harness) | Heavy harness (473-line skill) | Right-sized harness (119-line skill) |
|---|---|---|---|
| Agent dispatches per run | 1 | 5 | 4 |
| Subagent tokens per run (n=2 avg) | 31,507 (30,694 / 32,320) | 250,804 | 205,082 |
| Feature works, suite green | Yes (both runs, verified independently: 8/8 tests, 100% coverage, ruff clean) | Yes (both runs) | Yes (both runs) |
| Acceptance criteria verified independently | Only because we paid extra to check (see below) | 9/9 by an auditor that re-runs everything | 9/9, same auditor rigor |
| Who wrote the tests | The same agent that wrote the code | A tester that cannot touch production code | Same separation |
| Independent audit verdict | None produced by the run itself | UNBLOCKED x2 (1-2 warnings) | UNBLOCKED x2 (0 warnings) |
| Post-hoc independent quality check (paid separately) | WOULD PASS WITH WARNINGS x2; ~35k tokens per review to reconstruct the assurance | (audit is built in) | (audit is built in) |
| Durable learnings captured | None | 0-3 per run, gated through the auditor | Same, plus the evaluator engages only when the corpus is big enough to need selection |
| Spec traceability / tracking doc | None | Full | Full, one contradiction class structurally eliminated |

### How to read this honestly

- **The naked run is cheap and, on a task this small, correct.** Roughly 8x cheaper than the crew, and both naked runs shipped working, well-tested code (verified independently, not self-reported). That is the point, not a problem: a harness is overhead you must earn. Running a four-role crew on a 20-line endpoint is paying for verification the task barely needs. Right-sizing includes knowing when the harness is bigger than the job.
- **The audit cost did not disappear; it moved.** The naked runs produced no verdict anyone can trust without re-reading the code. To fill the naked column of this table we had to pay ~35k tokens per run for an independent post-hoc review, which is most of the gap between the naked run and a right-sized crew phase doing the same checking. In a team setting that deferred cost lands on a human reviewer. The harness does not add an audit; it schedules one you were going to owe anyway, and makes its result a durable artifact.
- **Both post-hoc reviews returned WOULD PASS WITH WARNINGS, and the warnings repeat.** Both naked runs shipped the generic-dict response schema (the OpenAPI contract documents an untyped object, not named fields) and 422 tests that cannot tell which validation constraint fired. Individually small; as a pattern across a backlog, exactly the make-it-work-over-make-it-right drift that compounds. The crew handles the same question differently: its coder spec explicitly permits or forbids each shape, so quality is judged against codified team standards instead of whichever reviewer's taste shows up later, and spec_writes updates the standard when a new pattern earns its place.
- **What the naked run does not produce at any price:** role separation (the coder graded its own homework), a tracking trail, or a learnings entry that makes the next run smarter. On one small REQ those are luxuries. Across a real backlog they are the difference between compounding quality and compounding drift. Anthropic's own harness-design work found the same boundary: self-evaluating agents "respond by confidently praising the work," so evaluation stays separate even as everything else shrinks.
- **Quality deltas barely show on a task this small.** The naked-vs-crew comparison is primarily a cost measurement with a quality spot-check; the repeated-warning pattern above is the visible edge of the quality argument, not its proof. The proof lives at backlog scale, in the separation-of-roles evidence and the published multi-agent results cited below.

## The shrink, measured

The rewrite cut the orchestrator 75% and the eval showed no regression and several improvements:

| Metric | 473-line skill | 119-line skill |
|---|---|---|
| Dispatches per run | 5 | 4 |
| Scout-phase tokens | 72,725 avg | 38,409 avg (-47%) |
| Total tokens per run | 250,804 avg | 205,082 avg (-18%) |
| Auditor warnings | 1-2 | 0 |
| Verdicts, criteria, role separation | UNBLOCKED, 9/9, clean | identical |

What made the cuts safe was that each one was grounded in observed behavior, not taste:

1. **The skill's Phase-0/Step-1 scout split was dead weight.** In both baseline runs the Phase-0 scout ignored its mode boundary and did Step-1's work anyway; 473 lines of instruction did not hold the boundary. Merging the phases halved scout cost with identical outcomes. The instruction wasn't controlling the model; it was billing it.
2. **The prescribed coder round-trip for a one-line status flip was pure ceremony.** Both baseline orchestrations skipped it on sight. The rewrite assigns the flip to the orchestrator, and adds the gap-analysis close-out that baseline run 2's auditor proved was missing (it flagged a self-contradictory tracking doc; post-rewrite audits found zero).
3. **The 4x-per-run CRAG retrieval ceremony collapsed to 1x with a threshold.** All four prescribed retrievals short-circuited identically on a small corpus. The independent evaluator survives, gated to engage only above five candidates, because its job is structural (a circuit breaker against the learning loop feeding its own biases back), and that argument is about loop topology, not model capability.
4. **What was deliberately kept:** role separation (held perfectly in all crew runs), the scout-contract validator gate, the five-condition coverage gate, stop-on-BLOCKED, and the auditor as sole learnings writer. The harness shrank around its load-bearing walls, not through them.

## The external evidence this aligns with

- **Anthropic simplified their own harness as models improved.** Their long-running app-development harness went from a three-agent system for Opus 4.5 to a simplified version for Opus 4.6, with the stated lesson that harness complexity should be continuously re-evaluated as models improve. (anthropic.com/engineering/harness-design-long-running-apps)
- **The Opus 5 prompting guidance says to delete legacy verification scaffolding outright:** explicit verification instructions now cause over-verification, and delegation needs capping rather than encouragement. (platform.claude.com/docs, Prompting Claude Opus 5)
- **Context is the scarce resource.** Tool definitions alone can consume 50k+ tokens before work starts; deferred loading recovers ~85% of it, and Anthropic's worked example of a context-heavy connector is Jira at ~17k tokens of definitions. (anthropic.com/engineering/advanced-tool-use, effective-context-engineering)
- **The counterweight that keeps this honest:** Anthropic's April 23, 2026 postmortem, where a verbosity-reducing prompt change measurably hurt coding quality and was reverted. Terser is not automatically better. That is why every cut above rode through a recorded eval gate (`docs/slimming-ledger.md` is the receipt for every deletion; `evals/golden-req/` is the gate).
- **Why multi-agent structure at all:** Anthropic's multi-agent research system beat single-agent by 90.2% on tasks needing multiple independent directions, with delegation quality as the bottleneck; and their 400k-session study of Claude Code found humans making most planning decisions while the model makes execution decisions. The harness is where the planning half gets encoded. (anthropic.com/engineering/multi-agent-research-system, anthropic.com/research/claude-code-expertise)

## Limits of this data, stated plainly

- One golden REQ, small and greenfield, n=2 per condition. Directional, not statistical.
- The blocker-fix, frontend-handoff, and Jira-sourced-requirement paths of the crew were compressed in the rewrite but not exercised by this eval; they get exercised in demo rehearsal.
- Coverage floors were trivially satisfied (the handler has no branches); a harder second fixture would strengthen the gate.
- The naked runs had the acceptance criteria handed to them in a well-written REQ file. A large share of real-world harness value is upstream of this eval: turning vague intent into REQ files this good.
