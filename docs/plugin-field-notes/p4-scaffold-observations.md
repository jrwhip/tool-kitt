# P4 scaffold: first-hand notes on using WOPR

> Recorded by the main-loop agent during the WOPR Arcade scaffold, 2026-08-21.
> Companion files: `footprint.md` (token cost), `naked-baseline.md` (control arm).
> Every claim here is something that happened during this session, with the file
> or command that produced it. Nothing is inferred from reading the catalog.

## The headline

The WOPR **content** (templates, schema doc, seed learnings, the golden fixture)
did most of the work and was worth its weight. The WOPR **tooling surface** was
either unreachable, wrong about this project, or actively misleading about where
it wrote files. Not one `mcp__wopr__*` tool was called in this session, because
the server wired into the live session is a stale build (see `footprint.md`).
Every WOPR function used here was called by importing the Python module directly
out of the clean-room repo.

That split is the finding. WOPR's value in this session was as a **library of
opinions**, not as an **MCP tool surface**.

---

## What helped, concretely

| Artifact | What it saved |
|---|---|
| `docs/wopr-yml-schema.md` | Settled the two-project question in one read. The field tables made it obvious that one `wopr.yml` describes exactly one source root, so backend and front end each needed their own. The control arm never faced this question and produced no config at all. |
| `catalog/crew/templates/by-stack/{fastapi,angular}/` | Four spec files that were 70% correct before editing. They carry real opinions (routers hold no logic, `AsyncSession` is per-request, OnPush everywhere, `.spec.ts` not `.test.ts`) that would otherwise have to be re-derived or, worse, left implicit. |
| `catalog/crew/data/learnings-seed/` | 10 entries seeded before a line of feature code exists. The CRAG pre-step has something to retrieve on the first crew run instead of an empty corpus. |
| `evals/golden-req-2/fixture/` | The single most useful file in the repo for this task. A working `wopr.yml` for a FastAPI project answered more questions faster than the schema doc did, because it showed a real filled-in `openapi` section rather than a field table. |
| `detect_stack` | Correctly identified both targets and, notably, that Angular 22's test runner is Vitest. That is a post-cutoff fact the detector got right. |

The control arm's biggest failure mode is the one WOPR's content directly
prevents: it **fabricated 14 dependency version pins from memory and got 10
wrong**, including a non-existent `httpx>=0.29`. Templates that name real
versions, and a `uv.lock`, are the fix for exactly that.

---

## What got in the way

### 1. The generated `wopr.yml` needed correcting in five of six sections

`propose_wopr_yml` output versus what shipped:

| Field | Generated | Correct | Why it was wrong |
|---|---|---|---|
| `project.slug` | `backend` | `arcade-api` | Derived from the directory basename. |
| `project.name` | `Backend` | `WOPR Arcade API` | Same. |
| `target_source_root` | `src` | `src/arcade_api` | Stops at `src/`, does not look inside for the package. |
| `requirements.local.path` | `requirements` | `../requirements` | Cannot express a shared requirements directory. |
| `openapi` | (absent) | `/openapi.json` + pin | No section emitted at all, though FastAPI was detected. |

The schema doc says `openapi` is required when a consuming pack uses it, so the
generator omitting it for a detected FastAPI project is a straight contradiction
between the doc and the tool.

### 2. `detect_stack` missed facts that were sitting in the files it read

`package_manager: "pip"` for a project with `uv.lock` and `[dependency-groups]`
in `pyproject.toml`. `test_runner: null` with pytest in the dev group and
`[tool.pytest.ini_options]` present. `framework_version: null` for FastAPI, while
the Angular target got `^22.1.0` correctly. `openapi_role: null` for both, when
one is plainly the producer and one the consumer.

### 3. The learnings corpus split in two, silently

This is the worst one. `seed_learnings` and `append_learnings` disagree about
what a workspace is:

- `seed_learnings` writes to `<workspace>/LEARNINGS.md` unconditionally
  (`learnings.py`, `target_file = workspace / LEARNINGS_FILENAME`).
- `append_learnings` routes through `_resolve_write_path`, which requires
  `wopr.yml` at the workspace root and otherwise falls back to
  `~/.wopr/LEARNINGS.md`.

Arcade has `wopr.yml` in `backend/` and `frontend/`, not at the root. So
`seed_learnings` happily created `arcade/LEARNINGS.md` with 10 entries, and the
three entries appended right afterward went to the system corpus instead. They
had to be moved by hand.

Worse, `_resolve_read_paths` uses the same check, so `arcade/LEARNINGS.md` is
currently **unreachable**: never written by append, never read by search, and
`_ensure_workspace_registered` is a no-op without the root `wopr.yml`, so it is
not in the registry either. It is an orphan file that looks correct.

`seed_learnings` also returned the string "Workspace registered." in that exact
case, which was false. That is a status message asserting something the code
explicitly skipped.

**This blocks the demo's closing beat.** `git diff LEARNINGS.md` after a crew run
is the emotional close of the talk, and today it would show nothing at the repo
root. Needs a decision before P4 rehearsals.

### 4. `ensure_sidecar_gitignored` is gated on the server's pinned workspace

Seeding a project other than the server's own workspace skips the gitignore
update entirely, so the embeddings sidecar would have been committed. Documented
behavior, but the failure is silent and the consequence is a machine-specific
binary in git.

### 5. The two stub writers emit their own instructions into the artifact

`write_tracking_doc_stub` and `write_handoff_contract_stub` both produce files
that open with a "For pack users:" preamble explaining what the template is, then
repeat the `# [PROJECT NAME]` title. The 138-line handoff contract is shaped
entirely around a legacy migration ("Clean-Break Notice", "legacy path aliases")
and was replaced wholesale for a greenfield project. The 113-line tracking stub
was deleted outright: the 33-line one produced by `wopr-wargame` in P2e was
better in every respect.

### 6. Both spec templates carried client-shaped residue

SonarCloud quality gates in three of four spec files, for a project with no
Sonar. Nx and pnpm throughout the Angular pair, for a single-app npm project.
`libs/<api-name>/` paths that do not exist here. All had to be stripped.

### 7. One template taught an idiom that raises `TypeError` today

`catalog/crew/templates/by-stack/fastapi/tester-spec.md` recommends
`httpx.AsyncClient(app=app, base_url=...)` twice. The `app` keyword was **removed**
in httpx 0.28. Had the coder followed the tester spec, the first test written
against the API would have crashed at construction. This is the strongest single
argument in the repo for the harness-thesis point that stale scaffolding is not
merely dead weight, it is negative value.

### 8. Six stale path references to the old repo

`webteam-ai-tools/docs/wopr-yml-schema.md` appeared in `wopr_yml.py` (baked into
every generated config header), `wopr-create-yml/SKILL.md`, `crew/README.md`,
`templates/README.md`, and `wopr.example.yml`. Fixed in this session; 673 tests
still pass. A dangling reference to `webteam-ai-tools/docs/perpetual-learning.md`
remains in `crew/README.md`: that document did not port, so the pointer is dead.

### 9. The tracking doc and handoff contract are namespaced under `legacy-migration`

The only schema fields that locate these two files live in the `legacy-migration`
block, and the schema doc itself notes they are the only fields in that block
that surviving tooling reads. A greenfield project must either declare a
`legacy-migration` section it has nothing to do with, or accept the defaults and
lose the ability to point at a repo-level tracking doc.

---

## Where the plugin was simply absent

Nothing in WOPR had an opinion on any of these, and all three cost real time:

1. **Postgres 18 moved its volume mount point.** The container exited 1 on first
   start. The control arm hit the identical wall independently, which makes it a
   genuine post-cutoff delta rather than a one-off.
2. **`openapi-typescript` still pins peer `typescript@^5.x`** while Angular 22
   ships TypeScript 6, so the install fails outright and the reflex fixes
   (`--legacy-peer-deps`, downgrading TS) are both wrong.
3. **`ng new --defaults` on Angular 22 does not set `strict: true`.** A fresh
   scaffold is non-strict unless you notice.

All three are now `LRN-2026-08-21-{a,b,c}` in `arcade/LEARNINGS.md`. They are
exactly the "post-cutoff knowledge" category the redesign says should survive,
and the corpus had none of them.

---

## Improvements this suggests, in rough priority order

1. **Reconcile workspace resolution across the learnings tools.** One rule, one
   corpus. A repo whose projects each carry a `wopr.yml` is still one workspace.
   Blocking for the demo close.
2. **Stop asserting outcomes that were skipped.** "Workspace registered." must
   not print when registration was a no-op.
3. **Fix `propose_wopr_yml` to emit the `openapi` section** for a detected
   FastAPI or Angular target, and to look inside `src/` for the package.
4. **Teach `detect_stack` to read what it already opened:** uv versus pip,
   pytest, framework version, producer versus consumer.
5. **Purge the templates:** the httpx idiom, Sonar, Nx and pnpm, `libs/` paths.
   Only item one is urgent, but all four are visible on camera.
6. **Split the stub templates' instructions out of their output.** The preamble
   belongs in the pack README, not in the file the operator ships.
7. **Move `tracking_doc` and `handoff_contract` out of `legacy-migration`** into
   a shared section, or into `specs`.
8. **Reconsider what the eager tier buys.** Per `footprint.md`, adopting
   wopr-core raises the current session floor rather than lowering it, and 82% of
   that tier is MCP tool definitions. The 67-to-23 tool cut halved tool-definition
   tokens, but mean tokens per tool went up: descriptions grew as the count fell.

## Method and its limits

Everything above is from this one session, scaffolding one project, with no crew
run. It says nothing about how the packs behave during an actual scout, coder,
tester, auditor cycle, which is where most of the harness lives. Findings 1
through 4 are code-level and hold regardless. Findings 5 through 9 are content
judgments about a greenfield project and would read differently on the legacy
migration the templates were written for.
