# Plugin field notes: what the harness actually cost, and what it actually bought

Study run 2026-08-21. Index and verdict. The three companion files carry the detail:

| File | What it holds |
|---|---|
| [`footprint.md`](footprint.md) | Static token cost of the WOPR MCP tool surface and the generated plugins, old versus new. |
| [`naked-baseline.md`](naked-baseline.md) | The control arm: an agent that scaffolded the same project with WOPR fully withheld. |
| [`p4-scaffold-observations.md`](p4-scaffold-observations.md) | First-hand notes from the WITH-WOPR arm on where the harness helped and where it fought back. |

---

## 1. What was measured, and how

Two agents were given the same scaffolding job (Angular front end, FastAPI backend, Postgres, skeleton plus infrastructure, both test suites green) on the same machine, on the same day, on the same model (`claude-opus-5`, every assistant message in both transcripts reports that model id). The WITH-WOPR arm ran as the main loop in Claude Code session `22c2ed8d-dd36-4ac0-aa7d-6c439d12061f` with the WOPR repo, its templates, its schema docs, its seed learnings, and its golden fixture all readable, and produced `/home/jrwhip/Work/AI/WOPR/arcade`. The CONTROL arm ran as subagent `ad3bd71ad9d0c27f3` under hard isolation rules (may read only `arcade/requirements/*.md` and `arcade/implementation-tracking.md`, may not read anything under `wopr/`, `webteam-ai-tools/`, or `wopr-plugins/`, may not call any `mcp__wopr__*` tool or invoke any Skill) and produced `/home/jrwhip/Work/AI/WOPR/.p4-naked-baseline`. Token and cost figures below are read directly from the `usage` objects in the Claude Code JSONL transcripts under `~/.claude/projects/-home-jrwhip-Work-AI-WOPR/`, deduplicated by assistant `message.id`; tool calls are counted by unique `tool_use.id`. Read section 7 before quoting any of it: the arms were not briefed identically, and the WITH-WOPR arm's session is not cleanly separable from the analysis work that produced these very documents.

---

## 2. Token and cost comparison

Snapshot as of read time, 2026-08-22T03:25Z. The WITH-WOPR session was still open and still being written when these numbers were taken, so its figures are a floor, not a final total.

Rates used, from the bundled `claude-api` skill (`Current Models` table, cached 2026-06-24, and `shared/prompt-caching.md` line 141): `claude-opus-5` input $5.00 / MTok, output $25.00 / MTok, cache read 0.1x input ($0.50 / MTok), cache write 1.25x input for the 5 minute TTL ($6.25 / MTok) and 2x input for the 1 hour TTL ($10.00 / MTok). Each message was priced with the TTL its own `usage.cache_creation` object reports.

| | WITH-WOPR arm (main session, includes analysis) | CONTROL arm (naked baseline subagent) |
|---|---:|---:|
| Transcript | `22c2ed8d-....jsonl` | `subagents/agent-ad3bd71ad9d0c27f3.jsonl` |
| Window (UTC) | 02:56:15 to 03:22:40 | 03:04:43 to 03:20:04 |
| Assistant turns | 138 | 75 |
| Input tokens (uncached) | 276 | 150 |
| Output tokens | 79,571 | 17,251 |
| Cache creation, 1 hour TTL | 169,829 | 0 |
| Cache creation, 5 minute TTL | 0 | 111,751 |
| Cache read | 15,746,341 | 4,999,802 |
| **Total tokens** | **15,996,017** | **5,128,954** |
| **List-price cost** | **$11.56** | **$3.63** |
| Tool calls | 138 (Bash 94, Write 29, Read 7, Edit 4, Agent 3, AskUserQuestion 1) | 107 (Bash 53, Write 44, Edit 8, Read 2) |

The control arm's own report estimated "~105" tool calls and 118,543 subagent tokens. The transcript says 107 tool calls, which is close, and 5,128,954 tokens, which is not: the self-reported figure appears to have counted only non-cache-read tokens. The transcript figure supersedes it. No self-reported number is used anywhere in this table.

**Do not read "$11.56 versus $3.63" as "WOPR cost 3.2x more."** The main session's total also contains the WOPR defect investigation (03:14 to 03:17 is spent reading `src/wopr/tools/learnings.py`, not scaffolding), the authoring of `p4-scaffold-observations.md`, the wopr repo's own 673-test suite run at 03:08:07, and the spawning of three subagents. There is no clean boundary between scaffold work and analysis work inside that session, and this document does not pretend to one. The only defensible partition is a prefix: through 03:04:00, before either subagent was spawned, the main session had spent **3,343,348 tokens, $2.85, 47 turns, 47 tool calls**, and had produced the backend only. That is a floor for the WITH-WOPR arm's scaffold cost, and it is already 78% of what the control spent to build both halves and write its report.

Two arithmetic notes. First, cache reads are 98.4% of the main session's tokens and 97.5% of the control's; both arms are dominated by re-reading a growing conversation prefix, not by anything either harness put in the window. Second, the two arms wrote cache entries at different TTLs (1 hour versus 5 minutes), which is a Claude Code runtime setting and not a property of either arm, and it costs the main session about $0.64 more than the same tokens would have cost at the 5 minute rate.

Sibling subagents, for completeness (both spawned by the main session, both counted in neither arm above): footprint audit `a870efbcb974d4f51`, 1,578,979 tokens, $1.55, 42 tool calls. This synthesis agent `a9a2646a447010353`, 822,270 tokens, $1.00, 18 tool calls at snapshot. Everything in this study, both arms plus all three analysis agents, totals **23,526,220 tokens and $17.75** at list price.

---

## 3. Output comparison

WITH-WOPR figures measured by walking `/home/jrwhip/Work/AI/WOPR/arcade` with the control arm's own exclusion set (`node_modules`, `.venv`, `.angular`, `__pycache__`, `*.egg-info`). CONTROL figures from `naked-baseline.md` section 1. Test counts are the last real run in each arm, not a claim.

| | WITH-WOPR (`arcade/`) | CONTROL (`.p4-naked-baseline/`) |
|---|---:|---:|
| Files in tree | 70 | 70 |
| Files authored (excluding the 9 shared requirement files, lockfiles, favicon) | 58 | 59 |
| Lines in those files | 2,072 | 1,887 |
| Backend lines | 745 | 883 |
| Frontend lines | 931 | 758 |
| Root lines | 396 | 246 |
| Backend tests passing | **2** (`uv run pytest`, 03:19:08) | **16** (`pytest -v`, exit 0) |
| Frontend unit tests passing | **2** (Vitest, 03:19:22) | **12** (Vitest, exit 0) |
| End to end tests passing | **1** (Playwright, 03:19:22) | 0 (no e2e harness) |
| **Total tests** | **5** | **28** |

What each arm produced that the other did not:

| WITH-WOPR only | CONTROL only |
|---|---|
| 4 crew spec files, 501 lines (`backend/specs/`, `frontend/specs/`) | Alembic baseline migration `0001_baseline_empty_schema` |
| 2 `wopr.yml` files, 66 lines | 14 more backend tests, 10 more frontend tests |
| `LEARNINGS.md`, 235 lines, 13 `LRN-` entries (10 seeded, 3 authored this session) | GitHub Actions CI, 78 lines, 3 jobs including a migration up/down/up round trip |
| `backend/uv.lock`, 1,233 lines | `Makefile`, `.env.example` at root |
| `frontend/src/app/api/schema.d.ts`, 72 lines, generated from the OpenAPI document | |
| Playwright config plus one e2e spec | |
| `eslint.config.js` | |
| `implementation-tracking.md` updated to 55 lines | left stale at 33 lines (its own section 4 item 13) |

The control arm shipped 5.6x the tests. The WITH-WOPR arm shipped the lockfile, the generated client, and the governance artifacts the control arm's report explicitly names as the things it punted on. Neither of those is a clean win, and section 7 explains why the test gap in particular cannot be attributed to the harness.

---

## 4. Where WOPR paid for itself

Each claim below names the file and the artifact. Nothing here is an impression.

1. **It shipped a lockfile, and the control's single worst failure was the absence of one.** The control fabricated 14 dependency pins from memory and got 10 wrong, including `httpx>=0.29` (no such release) and `mypy>=1.19,<2` when the current release is 2.3.1, a ceiling that would have excluded the only correct version (`naked-baseline.md` section 4 item 1). It then shipped no `uv.lock` at all and did not notice until writing its own report (item 3). `arcade/backend/uv.lock` is 1,233 lines.
2. **It picked the OpenAPI client generator, which the control identified as the biggest thing it punted on.** Two of eight requirements forbid hand-written HTTP services (`naked-baseline.md` section 4 item 6). The control wrote an export script and moved on. The WITH-WOPR arm shipped `frontend/src/app/api/schema.d.ts`, 72 lines, generated.
3. **The golden fixture answered configuration questions faster than the schema document did.** `evals/golden-req-2/fixture/` gave a real filled-in `openapi` section instead of a field table (`p4-scaffold-observations.md`, "What helped"). The schema doc then settled the two-project question in one read: one `wopr.yml` describes exactly one source root, so backend and front end each got their own. The control produced no config at all and never faced the question.
4. **`detect_stack` got a post-cutoff fact right:** it identified Angular 22's test runner as Vitest (`p4-scaffold-observations.md`, "What helped"). That is exactly the category the control arm proved it cannot self-supply.
5. **The stack templates carried real, non-obvious opinions.** Four spec files were roughly 70% correct before editing and carry contracts (routers hold no logic, `AsyncSession` is per request, OnPush everywhere, `.spec.ts` not `.test.ts`) that the control arm had to invent unilaterally, and did: it logged roughly 25 unilateral convention decisions with no basis beyond its own defaults (`naked-baseline.md`, bottom line).
6. **The always-on cost of the tier that delivered all of this is small in absolute terms.** `wopr-core` fully installed is 7,453 tokens (`footprint.md` section 5), which is 0.047% of the 15,996,017 tokens the WITH-WOPR session actually consumed.

## 5. Where WOPR cost more than it returned

1. **The MCP tool surface was not merely unhelpful, it was unreachable.** Zero `mcp__wopr__*` tools were called in the entire session. The server wired into `~/.claude.json` is the stale installed `wopr 0.2.0` binary pointed at `WOPR_WORKSPACE=/home/jrwhip/Work/AI/webteam-ai-tools` (`footprint.md` section 1). Every WOPR function used in the WITH-WOPR arm was reached by importing the Python module directly out of the repo. The 5,969 tokens of new tool definitions measured in `footprint.md` section 2 bought nothing in this session because they were never loaded.
2. **One template teaches an idiom that raises `TypeError` today.** `catalog/crew/templates/by-stack/fastapi/tester-spec.md` recommends `httpx.AsyncClient(app=app, base_url=...)` twice; the `app` keyword was removed in httpx 0.28 (`p4-scaffold-observations.md` section 7). A coder following that spec crashes on the first test written against the API. That is negative value, not dead weight.
3. **The generated `wopr.yml` was wrong in five of six sections** and had to be corrected by hand: `project.slug`, `project.name`, `target_source_root` (stops at `src/`, does not look inside for the package), `requirements.local.path` (cannot express a shared requirements directory), and a missing `openapi` section that the schema doc says is required (`p4-scaffold-observations.md` section 1). `detect_stack` separately reported `package_manager: "pip"` for a project with `uv.lock`, and `test_runner: null` with pytest configured (section 2).
4. **The learnings corpus silently split in two.** `seed_learnings` wrote `arcade/LEARNINGS.md` unconditionally; `append_learnings` routed the next three entries to `~/.wopr/LEARNINGS.md` because `wopr.yml` sits in `backend/` and `frontend/`, not at the repo root. `_resolve_read_paths` uses the same check, so `arcade/LEARNINGS.md` is currently written by nothing and read by nothing. `seed_learnings` returned the string "Workspace registered." in a case where registration was explicitly skipped (`p4-scaffold-observations.md` section 3).
5. **Two stub writers produced output that was discarded wholesale.** The 138 line handoff contract was shaped around a legacy migration and was replaced entirely; the 113 line tracking stub was deleted in favour of the 33 line one produced by `wopr-wargame` (`p4-scaffold-observations.md` section 5). Both stubs also emit their own instructions into the artifact.
6. **Client-shaped residue survived the clean-room port.** SonarCloud gates in three of four spec files, Nx and pnpm throughout the Angular pair, `libs/<api-name>/` paths that do not exist. All stripped by hand (`p4-scaffold-observations.md` section 6).
7. **The eager tier moved the wrong way against what is actually running.** Adopting `wopr-core` would raise the current session floor by 5,246 tokens (2,207 to 7,453), and 81.9% of that floor is MCP tool definitions (`footprint.md` section 5). The 67 to 23 tool cut halved tool-definition tokens but mean tokens per tool rose from 171.6 to 259.5, because descriptions grew as the count fell (`footprint.md` section 2).

---

## 6. The observation that matters most

**Both arms independently hit the Postgres 18 volume-mount change, and the control arm fabricated 10 of 14 dependency pins.** Put those two facts next to each other and the conclusion is uncomfortable for the thesis this study was built to support.

The Postgres 18 failure is the clean case. `postgres:18-alpine` refuses to start with the volume mounted at `/var/lib/postgresql/data`, because the 18 images expect a single mount at `/var/lib/postgresql` with data in a version subdirectory. Every docker-compose snippet in training data uses the pre-18 path. The control arm hit it and burned three tool calls (`naked-baseline.md` section 5 rework table, section 6 item 4). The WITH-WOPR arm hit it too, with the entire 286,456 token catalog, the seed learnings, and the stack templates available (`p4-scaffold-observations.md`, "Where the plugin was simply absent"). The harness did not contain the fact. Two more of the same kind followed: `openapi-typescript` still pins peer `typescript@^5.x` against Angular 22's TypeScript 6, and `ng new --defaults` on Angular 22 does not set `strict: true`. The corpus had none of the three. They exist now only because this session wrote them as `LRN-2026-08-21-{a,b,c}`.

The dependency-pin failure is the mirror image. Ten of fourteen pins were fabricated, and every one was caught, for free, by `uv pip install` failing on `httpx>=0.29`. No harness content was involved. The fix that would have prevented the whole class is a committed lockfile, which is not prose and costs zero context tokens.

So: the only failure category in this study that a harness was uniquely positioned to prevent is post-cutoff fact drift, and WOPR's current content did not prevent it, because it does not contain those facts. Meanwhile the largest single failure the control arm suffered was solved by a deterministic artifact and a verification loop, not by instruction. And 81.9% of what `wopr-core` charges a session before anything is invoked (6,107 of 7,453 tokens) is MCP tool definitions, and 94.8% of the deep tier behind `wopr-core`'s skills (186,931 of 197,236 tokens) sits in `references/` directories. Both of those are instruction and process. Neither is fact.

The defensible conclusion is narrower and less flattering than "right-size the harness": **the parts of a harness that earn their tokens are the parts that carry verified post-cutoff facts, and the parts that force a deterministic verification loop (a lockfile, a generated client, an eval). Prose that re-teaches judgment earns nothing, and prose that has gone stale is worse than absent, because the model will follow it.** The httpx idiom in the tester spec is the proof of the last clause: an agent trusting WOPR would have written a test that crashes at construction, and an agent with no harness at all would have written a working one.

The uncomfortable part for the redesign is that WOPR's token budget is currently allocated almost inversely to that finding. The mechanism designed to carry facts (the LEARNINGS corpus) had zero of the three facts this session needed, and is currently split across two files, one of which is unreachable by its own read path. The mechanisms that carry instruction are the ones consuming the tokens. Slimming the tool surface from 67 to 23 addressed the cheap half of that problem, and per `footprint.md` did it by removing tools rather than shortening prose, which is why mean cost per tool went up. Nothing in this study supports the claim that the harness as it stands today improves output. What it supports is a claim about which 5% of it would.

---

## 7. Ranked improvements

Merged and deduplicated across all three input files. Tag meanings: **blocking-for-demo** means the recorded demo either breaks or shows something embarrassing on camera; **high** means it costs real time or produces wrong artifacts; **low** means it is correctness or hygiene with no demo exposure.

| # | Improvement | Tag | Source |
|---|---|---|---|
| 1 | Repoint the wired MCP server. `~/.claude.json` runs the stale installed `wopr 0.2.0` binary against `WOPR_WORKSPACE=/home/jrwhip/Work/AI/webteam-ai-tools`. No `mcp__wopr__*` tool from the new build is callable in a live session today. | blocking-for-demo | `footprint.md` §1; `p4-scaffold-observations.md` headline |
| 2 | Reconcile workspace resolution across the learnings tools. One rule, one corpus; a repo whose projects each carry a `wopr.yml` is still one workspace. Today `arcade/LEARNINGS.md` is written by `seed_learnings`, never read by search, never appended to, and not in the registry. This kills the `git diff LEARNINGS.md` close. | blocking-for-demo | `p4-scaffold-observations.md` §3 |
| 3 | Remove `httpx.AsyncClient(app=app, ...)` from `catalog/crew/templates/by-stack/fastapi/tester-spec.md`. The `app` keyword was removed in httpx 0.28; a coder following the spec crashes on the first API test. | blocking-for-demo | `p4-scaffold-observations.md` §7 |
| 4 | Strip client-shaped residue from the spec templates: SonarCloud gates in 3 of 4 files, Nx and pnpm throughout the Angular pair, `libs/<api-name>/` paths. All visible on camera. | blocking-for-demo | `p4-scaffold-observations.md` §6 |
| 5 | Seed the corpus with verified post-cutoff facts, starting with the three this session found (Postgres 18 mount point, `openapi-typescript` peer TypeScript 5.x versus Angular 22's TypeScript 6, `ng new` does not set `strict`). This is the category the study shows actually pays. | high | §6 above; `p4-scaffold-observations.md`, "Where the plugin was simply absent"; `naked-baseline.md` §6.4 |
| 6 | Ship a convention document naming real pinned versions and mandating a committed lockfile. 10 of 14 pins fabricated in the control arm; the arm shipped no lockfile and did not notice. | high | `naked-baseline.md` §4.1, §4.3 |
| 7 | Stop asserting outcomes that were skipped. `seed_learnings` printed "Workspace registered." when registration was a documented no-op. | high | `p4-scaffold-observations.md` §3 |
| 8 | Fix `ensure_sidecar_gitignored`: seeding any workspace other than the server's pinned one silently skips the gitignore update, so a machine-specific embeddings binary gets committed. | high | `p4-scaffold-observations.md` §4 |
| 9 | Fix `propose_wopr_yml`: emit the `openapi` section for a detected FastAPI or Angular target, look inside `src/` for the package, allow a shared requirements directory, and derive slug and name from something other than the directory basename. Five of six sections needed correction. | high | `p4-scaffold-observations.md` §1 |
| 10 | Teach `detect_stack` to read what it already opened: uv versus pip, pytest, framework version, OpenAPI producer versus consumer. | high | `p4-scaffold-observations.md` §2 |
| 11 | Decide, in the catalog, the five contracts the control arm proved get invented otherwise: health and readiness contract verbatim, client generator plus output path plus regen command, WebSocket message envelope, auth middleware placement, and integration-tests-against-real-Postgres policy. | high | `naked-baseline.md` §4.4, §4.5, §4.6, §4.7, §4.8 |
| 12 | Cut tool-description length. The new 23-tool server costs 5,969 tokens at a mean of 201.8 description tokens per tool; the live 0.2.0 server does 25 tools in 1,913 tokens at a mean of 40.4. The five learnings tools alone are 1,853 tokens, 31.0% of the new server. | high | `footprint.md` §2 |
| 13 | Split the stub templates' instructions out of their output. The preamble belongs in the pack README, not in the file the operator ships; both stubs were discarded wholesale anyway. | high | `p4-scaffold-observations.md` §5 |
| 14 | Move `tracking_doc` and `handoff_contract` out of the `legacy-migration` block into a shared section or into `specs`. A greenfield project should not have to declare a legacy-migration section. | low | `p4-scaffold-observations.md` §9 |
| 15 | Fix the dead pointer to `webteam-ai-tools/docs/perpetual-learning.md` in `crew/README.md`; that document did not port. | low | `p4-scaffold-observations.md` §8 |
| 16 | Re-examine what the eager tier buys. `wopr-core` always-on is 7,453 tokens, 81.9% of it MCP tool definitions, and adopting it raises the current session floor by 5,246 tokens rather than lowering it. | low | `footprint.md` §5; `p4-scaffold-observations.md` §8 |
| 17 | Publish the frontend folder convention and the state-management rule. The control arm's `core/` directory holds one injection token and nothing builds toward REQ-ARC-7's real-time state fan-out. | low | `naked-baseline.md` §4.10 |

---

## 8. What this study cannot tell you

Read this section before quoting any number above.

1. **Neither arm ran the crew.** `wopr-crew` is 1 skill and 5 agents, 454 eager tokens and 8,442 on-trigger tokens (`footprint.md` section 3), and the scout, coder, tester, auditor cycle plus the CRAG pre-step is where most of the harness lives and where its central claim (separate evaluation from generation) is supposed to pay. Nothing here measures any of it. This study measures a scaffold, which is the one task where a harness has the least to do.
2. **The two arms were not given the same prompt.** The control was told, verbatim, "unit tests wired and passing on both sides" and "Get both test suites green." The WITH-WOPR arm's brief was "P4: demo repo scaffold" plus a plan file whose P4 line reads "Angular + FastAPI + wopr.yml + specs + seed learnings." The 28 versus 5 test gap in section 3 is at least partly a briefing difference, and this study cannot separate the two causes. Do not present the test gap as a harness effect.
3. **The WITH-WOPR arm is not an isolated arm.** Scaffolding, WOPR defect investigation, the wopr repo's own 673-test suite, the authoring of `p4-scaffold-observations.md`, and the spawning of three analysis subagents all happened in one session with no boundary between them. The $11.56 figure includes all of it. The $2.85 prefix through 03:04:00 is the only clean partition, and it covers the backend only.
4. **The MCP surface was never exercised.** Zero `mcp__wopr__*` calls happened. `footprint.md`'s tool-definition token counts are a static measurement of a surface that was not loaded in either arm, and no claim here about the tool layer's runtime behaviour has evidence behind it.
5. **`footprint.md` uses OpenAI's tokenizer.** All its counts come from `tiktoken` `o200k_base`, because no Anthropic tokenizer was available on the machine (`footprint.md`, "Method and its limits"). Its deltas and percentages are trustworthy because both sides use the same encoder; its absolute values are a proxy. Its eager tier (T1) is a reconstruction of how Claude Code lists catalog items, not an observation, and it understates real eager cost.
6. **The dollar figures are list-price arithmetic, not an invoice.** They multiply transcript `usage` counts by published `claude-opus-5` API rates. Claude Code subscription billing does not work that way. Use them as a comparison unit between arms, not as spend.
7. **n = 1 per arm.** One project, one stack, one model, one day, one machine, one operator. Nothing here supports a general claim about harnesses. The control arm's own conclusion and the WITH-WOPR arm's own conclusion were each written by the agent that produced the work, which is exactly the self-evaluation problem the crew design exists to avoid.
8. **Green tests are not a quality measure.** The control's 16 backend tests run against in-memory SQLite, and its own report flags that REQ-ARC-2's FIFO pairing and REQ-ARC-5's exactly-once ratings will need real Postgres that the scaffold does not provide (`naked-baseline.md` section 4 item 5). The WITH-WOPR arm's 2 backend tests were never claimed to be sufficient. Neither arm's output was reviewed by a third party.
9. **Wall clock is not comparable.** The control ran 15 minutes 21 seconds of assistant activity in a fresh context. The main session ran 26 minutes 25 seconds carrying a session prefix that grew to fill most of its cache reads. Neither number includes the human time spent framing the arms.
10. **The study cannot say whether removing WOPR would have made the WITH-WOPR arm better.** It can only say which specific artifacts helped, which specific artifacts were wrong, and that one specific template would have broken the build. Running the same scaffold a second time with WOPR withheld from the main loop, or running the crew in both arms, is the experiment that would answer the actual question.
