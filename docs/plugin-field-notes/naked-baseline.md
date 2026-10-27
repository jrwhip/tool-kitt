# Naked Baseline: KITT Arcade scaffold, control arm

Date: 2026-08-21
Model: Claude Opus 5 (1M context), Claude Code / Agent SDK
Arm: CONTROL. No KITT plugin, no skills, no MCP tools, no templates, no seed
learnings. The only inputs were the task prompt and `requirements/REQ-ARC-1.md`
through `REQ-ARC-8.md` plus `implementation-tracking.md`.
Output directory: `/home/jrwhip/Work/AI/KITT/.p4-naked-baseline/`

Wall clock: 21:04:48 to 21:17:08 local, **12 minutes 20 seconds**.

---

## 1. What I produced

### File tree with line counts

```
   83  backend/alembic/env.py
   55  backend/alembic.ini
    0  backend/alembic/README
   28  backend/alembic/script.py.mako
   28  backend/alembic/versions/0001_baseline_empty_schema.py
   67  backend/pyproject.toml
   69  backend/README.md
   14  backend/src/arcade_api/api/__init__.py
   49  backend/src/arcade_api/api/health.py
    3  backend/src/arcade_api/__init__.py
   46  backend/src/arcade_api/config.py
   75  backend/src/arcade_api/db.py
   66  backend/src/arcade_api/main.py
   10  backend/src/arcade_api/models/__init__.py
    1  backend/src/arcade_api/schemas/__init__.py
   27  backend/src/arcade_api/schemas/health.py
    1  backend/src/arcade_api/scripts/__init__.py
   38  backend/src/arcade_api/scripts/export_openapi.py
   76  backend/tests/conftest.py
   38  backend/tests/test_alembic.py
   26  backend/tests/test_config.py
   21  backend/tests/test_db.py
   31  backend/tests/test_health.py
   31  backend/tests/test_openapi.py
   28  docker-compose.yml
   15  .env.example
   85  frontend/angular.json
   17  frontend/.editorconfig
   44  frontend/.gitignore
   36  frontend/package.json
 8045  frontend/package-lock.json        (generated)
    5  frontend/.prettierignore
   12  frontend/.prettierrc
   22  frontend/proxy.conf.json
   33  frontend/public/favicon.ico        (binary, from ng new)
   55  frontend/README.md
   25  frontend/src/app/app.config.spec.ts
   18  frontend/src/app/app.config.ts
   26  frontend/src/app/app.html
   46  frontend/src/app/app.routes.spec.ts
   19  frontend/src/app/app.routes.ts
   52  frontend/src/app/app.scss
   44  frontend/src/app/app.spec.ts
   28  frontend/src/app/app.ts
   17  frontend/src/app/core/api-base-url.spec.ts
   15  frontend/src/app/core/api-base-url.ts
   16  frontend/src/app/home/home.ts
   16  frontend/src/app/not-found/not-found.ts
   13  frontend/src/index.html
    5  frontend/src/main.ts
   26  frontend/src/styles.scss
   10  frontend/tsconfig.app.json
   31  frontend/tsconfig.json
    9  frontend/tsconfig.spec.json
    4  frontend/.vscode/extensions.json
   20  frontend/.vscode/launch.json
   42  frontend/.vscode/tasks.json
   78  .github/workflows/ci.yml
   23  .gitignore
   33  implementation-tracking.md        (copied from arcade/)
   39  Makefile
   63  README.md
   20  requirements/REQ-ARC-1.md          (copied from arcade/)
   20  requirements/REQ-ARC-2.md          (copied)
   22  requirements/REQ-ARC-3.md          (copied)
   20  requirements/REQ-ARC-4.md          (copied)
   20  requirements/REQ-ARC-5.md          (copied)
   22  requirements/REQ-ARC-6.md          (copied)
   22  requirements/REQ-ARC-7.md          (copied)
   20  requirements/REQ-ARC-8.md          (copied)
```

### Totals

| Metric | Count |
|---|---|
| Files in the tree (excluding `node_modules/`, `.venv/`, `.angular/`, `__pycache__/`, `*.egg-info/`) | 70 |
| Files authored or modified by me (excluding the 9 copied requirement files, `package-lock.json`, `favicon.ico`) | 59 |
| Total lines in those 59 files | 1,887 |
| Backend lines | 883 |
| Frontend lines | 758 |
| Root-level lines (compose, Makefile, README, CI, env, gitignore) | 246 |

Of the 59 "authored" files, 17 came out of `ng new` untouched (`.editorconfig`,
`.vscode/*`, `tsconfig.*`, `.prettierrc`, `.gitignore`, `main.ts`,
`index.html` before I edited the title, and so on). Genuinely hand-written
source and config is roughly 40 files.

---

## 2. Actual test-run output

### Backend

Command: `cd backend && .venv/bin/pytest -v`

```
============================= test session starts ==============================
platform linux -- Python 3.13.9, pytest-9.1.1, pluggy-1.6.0 -- /home/jrwhip/Work/AI/KITT/.p4-naked-baseline/backend/.venv/bin/python3
cachedir: .pytest_cache
rootdir: /home/jrwhip/Work/AI/KITT/.p4-naked-baseline/backend
configfile: pyproject.toml
testpaths: tests
plugins: asyncio-1.4.0, cov-7.1.0, anyio-4.14.2
asyncio: mode=Mode.AUTO, debug=False, asyncio_default_fixture_loop_scope=function, asyncio_default_test_loop_scope=function
collecting ... collected 16 items

tests/test_alembic.py::test_alembic_ini_is_present PASSED                [  6%]
tests/test_alembic.py::test_alembic_ini_carries_no_database_url PASSED   [ 12%]
tests/test_alembic.py::test_there_is_exactly_one_migration_head PASSED   [ 18%]
tests/test_alembic.py::test_every_revision_has_an_upgrade_and_downgrade PASSED [ 25%]
tests/test_config.py::test_settings_read_the_arcade_env_prefix PASSED    [ 31%]
tests/test_config.py::test_database_url_defaults_to_async_postgres_driver PASSED [ 37%]
tests/test_config.py::test_unknown_environment_is_rejected PASSED        [ 43%]
tests/test_config.py::test_get_settings_is_cached PASSED                 [ 50%]
tests/test_db.py::test_session_executes_a_round_trip PASSED              [ 56%]
tests/test_db.py::test_metadata_is_the_single_alembic_target PASSED      [ 62%]
tests/test_health.py::test_health_reports_ok PASSED                      [ 68%]
tests/test_health.py::test_health_does_not_require_the_database PASSED   [ 75%]
tests/test_health.py::test_readiness_reports_database_up PASSED          [ 81%]
tests/test_openapi.py::test_openapi_document_is_served PASSED            [ 87%]
tests/test_openapi.py::test_health_endpoints_are_documented PASSED       [ 93%]
tests/test_openapi.py::test_responses_use_named_schemas_not_inline_objects PASSED [100%]

============================== 16 passed in 0.07s ==============================
PYTEST_EXIT=0
```

**Exit code 0. 16 passed.**

### Frontend

Command: `cd frontend && mise exec node@24 -- npm test -- --reporters=verbose`
(ANSI escapes stripped)

```
> kitt-arcade-web@0.1.0 test
> ng test --reporters=verbose

❯ Building...
✔ Building...
Application bundle generation complete. [0.514 seconds] - 2026-08-22T03:16:18.446Z


 RUN  v4.1.11 /home/jrwhip/Work/AI/KITT/.p4-naked-baseline/frontend

 ✓  frontend  src/app/core/api-base-url.spec.ts > API_BASE_URL > defaults to same origin so the dev proxy handles routing 7ms
 ✓  frontend  src/app/core/api-base-url.spec.ts > API_BASE_URL > can be overridden by a provider 1ms
 ✓  frontend  src/app/app.config.spec.ts > appConfig > provides HttpClient 6ms
 ✓  frontend  src/app/app.config.spec.ts > appConfig > provides the Router with the application route table 3ms
 ✓  frontend  src/app/app.spec.ts > App shell > creates 27ms
 ✓  frontend  src/app/app.spec.ts > App shell > renders the brand 10ms
 ✓  frontend  src/app/app.spec.ts > App shell > renders a router outlet for feature routes 5ms
 ✓  frontend  src/app/app.spec.ts > App shell > renders one nav link per configured destination 4ms
 ✓  frontend  src/app/app.routes.spec.ts > routes > declares a root route and a wildcard 1ms
 ✓  frontend  src/app/app.routes.spec.ts > routes > lazy-loads every route 0ms
 ✓  frontend  src/app/app.routes.spec.ts > routes > navigation > renders the home route at / 35ms
 ✓  frontend  src/app/app.routes.spec.ts > routes > navigation > renders the not-found route for an unknown url 6ms

 Test Files  4 passed (4)
      Tests  12 passed (12)
   Start at  21:16:18
   Duration  427ms (transform 55ms, setup 432ms, import 89ms, tests 109ms, environment 756ms)

VITEST_EXIT=0
```

**Exit code 0. 12 passed.**

### Other verification actually run (not just claimed)

```
$ .venv/bin/ruff check . --output-format=concise
All checks passed!                                   # exit 0

$ .venv/bin/ruff format --check .
20 files already formatted                           # exit 0

$ .venv/bin/mypy src
Success: no issues found in 11 source files          # exit 0

$ npx prettier --check .
All matched files use Prettier code style!           # exit 0

$ npm run build
Initial total | 246.25 kB | 69.06 kB transfer
Lazy chunk files: home 496 bytes, not-found 489 bytes
Application bundle generation complete. [0.925 seconds]
BUILD_EXIT=0
```

Alembic was exercised against a real Postgres 18 container on port 55432:

```
$ alembic downgrade base
INFO  [alembic.runtime.migration] Running downgrade 0001 -> , baseline empty schema
$ alembic upgrade head
INFO  [alembic.runtime.migration] Running upgrade  -> 0001, baseline empty schema
$ alembic current
0001 (head)
```

The API was smoke-tested against that same Postgres:

```
$ curl -s localhost:8111/health
{"status":"ok","service":"KITT Arcade API","version":"0.1.0","environment":"local"}
$ curl -s localhost:8111/health/ready
{"status":"ready","database":"up"}
$ curl -s localhost:8111/openapi.json | head -c 200
{"openapi":"3.1.0","info":{"title":"KITT Arcade API","description":"Backend for **KITT Arcade**, ...
```

The container was torn down afterwards (`docker compose -p kitt-arcade-baseline down -v`).

---

## 3. Decisions I invented because nothing told me

Every one of these was a coin flip made by me, in isolation, with no stated
project convention to follow.

| Decision | What I chose | Why, and what else was equally defensible |
|---|---|---|
| **Backend project layout** | `src/` layout, package at `backend/src/arcade_api/` | Tests then import the installed package rather than the working tree, so a packaging error fails locally instead of in the container. A flat `backend/app/` layout is at least as common in FastAPI projects and I could have gone either way. |
| **Package name** | import name `arcade_api`, distribution name `kitt-arcade-api` | Nothing told me whether the product prefix belongs in the import path. `kitt_arcade` and plain `app` were both live options. |
| **Internal module split** | `api/` (routers), `schemas/` (pydantic), `models/` (ORM), `config.py`, `db.py`, `main.py`, `scripts/` | Layer-first. A feature-first split (`features/auth/{router,schemas,models}.py`) would arguably suit eight independent REQs better. I picked layer-first purely out of habit. |
| **Python version floor** | `requires-python = ">=3.13"`, venv on 3.13.9 | The machine has 3.14.7 system-wide. I dropped to 3.13 out of unverified caution about C-extension wheel availability on 3.14 for `asyncpg`. I never checked whether 3.14 actually works. That is a guess dressed as a decision. |
| **Build backend** | `hatchling` | No reason beyond it being the current default in most `uv init` output. `setuptools`, `pdm-backend`, `poetry-core` were all equivalent here. |
| **Dependency choices** | FastAPI, uvicorn[standard], pydantic v2, pydantic-settings, SQLAlchemy 2 async, asyncpg, Alembic | Standard, but `psycopg[binary,pool]` (v3) is the other mainstream async Postgres driver and arguably the better long-term pick. I chose asyncpg reflexively. |
| **Version pins** | Floor at the current release, ceiling at the next minor or major: `fastapi>=0.141.1,<0.142`, `sqlalchemy>=2.0.52,<2.1`, `mypy>=2.3.1,<3`, etc. | Nothing told me whether this project wants pins, ranges, or a lockfile. I did not create a `uv.lock` (see section 4). |
| **Test runner, backend** | pytest with `asyncio_mode = "auto"` via `pytest-asyncio` | `anyio` came in transitively and would have worked too. `auto` mode means test authors never write `@pytest.mark.asyncio`, which I like but did not clear with anyone. |
| **Test database** | in-memory SQLite via `aiosqlite`, per test, with `Base.metadata.create_all` | Makes `pytest` runnable with no container. The cost is real: SQLite is not Postgres, and REQ-ARC-2 (FIFO queue), REQ-ARC-5 (ratings applied exactly once) and any locking behaviour will need a real Postgres fixture that this scaffold does not provide. I chose the convenient option and pushed the hard problem downstream. |
| **Config approach** | `pydantic-settings`, `ARCADE_` env prefix, `.env` file support, `get_settings()` behind `lru_cache`, injected via `Depends` | The cache means tests must override the dependency rather than set env vars mid-run. That is a real constraint I imposed on future test authors without being asked. |
| **Health endpoint shape** | `GET /health` (liveness, no dependencies) plus `GET /health/ready` (readiness, returns 200 with `status: degraded` when the DB is down) | The task said "health endpoint", singular. I invented the split, invented the paths, and invented the choice to return 200 rather than 503 on a degraded dependency. Kubernetes convention would often want 503. |
| **Health paths vs API prefix** | health lives at the root, not under `/api` | `Settings.api_prefix = "/api"` exists but is unused so far, which is arguably dead config I should not have shipped. |
| **OpenAPI exposure** | Served live at `/openapi.json`, Swagger at `/docs`, ReDoc at `/redoc`; plus `python -m arcade_api.scripts.export_openapi <path>` writing a stable sorted JSON artifact | The export script exists so client generation does not need a running server or a database. Nothing told me whether the spec should be committed, generated in CI, or fetched at build time. I chose "gitignored artifact", which is a guess. |
| **Client generation** | **Not wired.** REQ-ARC-7 and REQ-ARC-8 both mandate a generated client, and I chose no generator. | `@hey-api/openapi-ts`, `ng-openapi-gen`, and `openapi-typescript` are all plausible. Picking one is a load-bearing decision I deferred rather than made. |
| **Alembic wiring** | `alembic init -t async`, then: URL injected in `env.py` from `arcade_api.config` (so `alembic.ini` holds no credentials), `target_metadata = arcade_api.models.Base.metadata`, `compare_type` and `compare_server_default` enabled, `prepend_sys_path = %(here)s/src`, `ruff format` post-write hook | The credentials-out-of-ini choice is right and I would defend it. The `compare_server_default = True` choice generates noisy diffs on some setups; nothing told me the project's tolerance for that. |
| **Migration id convention** | zero-padded sequential ids via explicit `--rev-id 0001`, `file_template = %%(rev)s_%%(slug)s`, UTC timestamps | Alembic's default is a random hash. Sequential ids read better but require discipline and will collide on parallel branches. I picked readability and wrote the discipline into the README, which is exactly the kind of rule that gets ignored. |
| **Baseline migration** | one empty revision `0001_baseline_empty_schema` | So `alembic upgrade head` is meaningful and `alembic_version` exists from day one. Alternative is no revision at all until REQ-ARC-1. |
| **Postgres version** | `postgres:18-alpine` | Newest. Also the version whose data-directory convention changed and cost me a debugging cycle (section 6). |
| **Angular version and flags** | Angular 22.1.5 (checked npm), `--zoneless --routing --style=scss --ssr=false --test-runner=vitest --ai-config=none` | SSR off because the app is behind auth and websocket-driven. Nobody told me that. |
| **Test runner, frontend** | Vitest through the `@angular/build:unit-test` builder, jsdom, configured in `angular.json` with no `vitest.config.ts` | This is the Angular 22 default. Karma was the alternative. Configuring in `angular.json` rather than a runner config file means Vitest plugins are unavailable until someone adds `runnerConfig`. |
| **Frontend structure** | `src/app/{core,home,not-found}`, lazy `loadComponent` on every route, `OnPush` everywhere, `data-testid` selectors in tests | The `core/` directory with one token in it is speculative structure. A feature-first layout (`src/app/features/{lobby,play,leaderboard}`) is what REQ-ARC-7/8 actually imply and I did not build toward it. |
| **API base URL strategy** | `proxy.conf.json` in dev forwarding `/api`, `/health`, `/openapi.json`, `/ws`; `API_BASE_URL` injection token defaulting to `''` (same origin) | Deliberately avoids Angular `environments/` files and `fileReplacements`. Defensible, but it is a convention nobody ratified, and the deployment story ("both behind one host") is an assumption I invented. |
| **Extras nobody asked for** | GitHub Actions CI (3 jobs including a migration up/down/up round trip), a `Makefile`, `.env.example`, root and per-side READMEs | "Infrastructure" is vague enough that I read it as license to add these. A convention document would have said yes or no in one line. |

---

## 4. Where I was uncertain or guessed (brutal version)

1. **Every single dependency version was a hallucinated guess on the first
   pass.** I wrote 14 pins from memory. When I ran `uv pip install`, resolution
   failed on `httpx>=0.29` (no such release; current is 0.28.1). I then queried
   PyPI for all 14 and found **10 of 14 were wrong**, including `mypy` where I
   guessed `>=1.19,<2` and the current release is **2.3.1**, a major version I
   did not know existed. My ceiling `<2` would have excluded the only correct
   version. If the install had not failed on `httpx` first, I would have shipped
   a `mypy<2` pin and never noticed.
   *What I wanted a convention document to tell me:* pin policy (floors vs
   ranges vs lockfile), and the approved dependency set with versions, so I am
   never guessing at package registry state from training data.

2. **I do not know if Python 3.13 is right.** The machine runs 3.14.7. I chose
   3.13 on an unverified hunch about wheel availability and never tested 3.14.
   That is a guess presented as a decision, and it is exactly the kind of thing
   that quietly becomes the project's floor forever.
   *Wanted:* "Python floor is X."

3. **I did not create a lockfile.** No `uv.lock`, no `requirements.txt`. The
   backend is reproducible only to the resolution of the ranges, while the
   frontend has a real `package-lock.json`. That is an inconsistency I created
   and did not notice until writing this report.
   *Wanted:* "Backend uses `uv lock` / `uv sync`, committed."

4. **The health endpoint contract is entirely invented.** One endpoint or two.
   Root path or under `/api`. 200-with-degraded or 503. Version string in the
   body or not. Nobody told me any of it, and every one of those is a decision
   an ops team would have opinions about.
   *Wanted:* the health/readiness contract, verbatim.

5. **SQLite-for-tests is a shortcut with a bill attached.** It makes the suite
   fast and container-free today. REQ-ARC-2's FIFO pairing, REQ-ARC-5's
   "ratings applied exactly once", and any `SELECT ... FOR UPDATE` will need
   real Postgres and a transactional fixture. I built none of that and did not
   flag it in the code. I optimised for "tests green in 12 minutes" over "tests
   that will still be the right tests in three weeks", which is precisely the
   cheap-outsourcing quality pattern.
   *Wanted:* "Integration tests run against a real Postgres via testcontainers /
   a session-scoped compose fixture; unit tests may use SQLite."

6. **The OpenAPI client generator is the single biggest thing I punted on.**
   Two of eight requirements explicitly forbid hand-written HTTP services and
   mandate generated types. The correct time to pick the generator is at
   scaffold time, when the wiring is cheap. I wrote an export script, a README
   sentence, and moved on. Someone will now pick a generator under deadline
   pressure while implementing REQ-ARC-8.
   *Wanted:* "Client generator is X, output goes to Y, regenerated by command Z,
   committed / not committed."

7. **No WebSocket infrastructure at all.** Four of eight REQs are WebSocket
   requirements. I added a `/ws` proxy rule and a sentence in the API
   description. There is no connection manager, no message envelope type, no
   test harness for socket messages. "Skeleton plus infrastructure" arguably
   should have included a typed message envelope shared by both sides, since
   that shape is the hardest thing to change later.
   *Wanted:* whether the WS envelope is part of scaffolding, and whether its
   types are generated, hand-shared, or duplicated.

8. **No auth infrastructure.** Same argument: REQ-ARC-1 gates six other REQs
   behind JWT, and the "401 on every endpoint except join, health, and the
   OpenAPI document" rule is a global middleware decision, not a feature
   decision. I built no place for it to live.

9. **`Settings.api_prefix` is dead config.** I added it, never used it, and
   left it in. Small, but it is the seed of "why is this here" three months
   from now.

10. **Frontend directory structure is speculative.** `core/` holds one
    injection token. There is no `features/`, no shared UI directory, no state
    management decision (signals-only? a store? services?). REQ-ARC-7 needs
    real-time state fanning out to a board, a map, an animation layer, and a
    host-line feed. Nothing in this scaffold makes that easier.
    *Wanted:* the frontend folder convention and the state-management rule.

11. **I invented a visual identity.** Green-on-black WarGames terminal colours,
    "SHALL WE PLAY A GAME?", "NO SUCH TERMINAL", CSS custom properties named
    `--arcade-*`, BEM-ish SCSS. All of that is design work nobody authorised. If
    the real design system differs, this is throwaway.

12. **Test naming and structure conventions are mine.** Backend uses
    sentence-style function names (`test_health_does_not_require_the_database`).
    Frontend uses `describe`/`it` with `data-testid` selectors. Both are
    reasonable; neither is agreed.

13. **The `implementation-tracking.md` file did not get updated.** It still
    reads "no implementation exists yet" and lists nothing about scaffolding. I
    copied it and left it stale. Nothing told me whether scaffold work is
    supposed to be tracked there, and I did not ask.

14. **I copied `requirements/` into my working directory** rather than sharing
    the original, because the isolation rules put my output somewhere else.
    In a real repo this would be a single shared directory, so the layout I
    produced is one directory-copy away from the intended one.

15. **`ng new` created 17 files I never reviewed in depth** (`.vscode/*`,
    `.editorconfig`, `tsconfig.*`). I verified strict mode empirically because
    `tsconfig.json` had no `"strict": true` and I could not remember whether
    TypeScript 6 defaults it on (it does; I probed it with a deliberate type
    error). I did not audit the rest.

16. **The Angular workspace project is still named `frontend`**, so builds land
    in `dist/frontend`. I renamed the npm package to `kitt-arcade-web` but not
    the `angular.json` project key. Inconsistent, and I noticed only while
    reading the build output.

---

## 5. Wall clock and step count

| Metric | Value |
|---|---|
| Wall clock | 12 min 20 s (21:04:48 to 21:17:08) |
| Total tool calls | **~105** (103 before writing this report, plus teardown and the report write) |
| Calls that were rework | **~28, about 27%** |

Rework breakdown by cause:

| Cause | Calls burned |
|---|---|
| Wrong dependency version pins (install failure, PyPI lookup, edit, reinstall) | 4 |
| `pyproject.toml` referenced `README.md` before it existed (build failure, then write) | 2 |
| Docker container name collision with an unrelated running container | 4 |
| Postgres 18 data-directory convention (failed start, log read, edit, recreate) | 3 |
| Alembic `post_write_hooks` hook type wrong | 2 |
| Ruff violations in my own code and in Alembic-generated files (diagnose, template rewrite, isort config, regenerate, re-verify) | 10 |
| `angular.json` invalid `browsers: []` schema value | 2 |
| Wrong Vitest reporter flag (`--reporter` vs `--reporters`) | 2 |

Note the shape: **almost none of the rework was about design.** All of it was
about not knowing current facts (package versions, image conventions, builder
schemas, CLI flags) or about linting my own output into compliance with rules I
had just set myself.

---

## 6. What I got wrong on the first attempt

1. **Ten of fourteen dependency version pins were fabricated.** Detail in
   section 4 item 1. The `mypy>=1.19,<2` pin is the worst of them: mypy 2.3.1 is
   current, and my ceiling would have silently excluded it.

2. **`pyproject.toml` declared `readme = "README.md"` before I wrote the file.**
   Hatchling failed the editable build with `OSError: Readme file does not
   exist`. Ordering mistake, trivially avoidable.

3. **`docker-compose.yml` hardcoded `container_name: arcade-db`,** which
   collided with a container already running on the machine from an unrelated
   stack, and would have collided with any second copy of this project.
   Removing `container_name` and letting Compose namespace it is the correct
   answer, and I only learned it by breaking.

4. **`postgres:18-alpine` refused to start** with the volume mounted at
   `/var/lib/postgresql/data`. Postgres 18 images expect a single mount at
   `/var/lib/postgresql` with data in a version subdirectory. Every
   docker-compose Postgres snippet in my training data uses the pre-18 path. I
   copied the old convention without checking.

5. **The Alembic `ruff_format` post-write hook used `type = console_scripts`,**
   which failed with `Could not find entrypoint console_scripts.ruff`, because
   ruff ships a compiled binary and exposes no console_scripts entry point. The
   fix is `type = exec` with an explicit executable path. The migration was
   still generated, so this failed loudly but harmlessly; it would have rotted
   quietly if I had not been reading output.

6. **Ruff flagged ten violations in code I had just written and in the file
   Alembic generated from its stock template.** Three separate root causes:
   - a 101-character import line in `db.py` (my own rule, violated immediately);
   - Alembic's stock `script.py.mako` emits `typing.Union`, `typing.Sequence`,
     and unconditional `op`/`sa` imports, all of which trip `UP007`, `UP035`,
     and `F401`. I rewrote the template;
   - ruff's isort classified the installed `alembic` package as **first-party**
     because a directory named `alembic/` exists at the project root, so import
     ordering could never be satisfied until I added
     `known-third-party = ["alembic"]`. That one took two diff inspections to
     see.

   I then had to regenerate the baseline migration three times to get a
   lint-clean generated file.

7. **`angular.json` `test.options.browsers = []` failed schema validation**
   (`must NOT have fewer than 1 items`). I added the key defensively without
   knowing the schema. Empty array means "jsdom", except it does not; omitting
   the key means jsdom.

8. **Used `--reporter=verbose` for the final frontend run.** The Angular
   unit-test builder takes `--reporters` (plural). Rejected with
   `Unknown argument: reporter`.

9. **Prettier reformatted six files I had written or edited,** including my own
   `app.html` and `angular.json`. I wrote code without running the formatter
   first, then let the formatter rewrite it.

None of these were caught by thinking. Every one was caught by running the
thing. The 12-minute wall clock is only honest because the failures were fast.

---

## Bottom line for the experiment

The control arm produced a working, tested, lint-clean, type-checked scaffold
in about 12 minutes and 105 tool calls, with both suites green (16 backend, 12
frontend) and Alembic verified round-trip against a real Postgres.

What it also produced: roughly **25 unilateral convention decisions** with no
basis other than my defaults, **one hallucinated dependency ecosystem** that
took a failed install to discover, and **three deferred decisions**
(client generator, WebSocket envelope, auth middleware placement) that are
cheap now and expensive at REQ-ARC-7.

The rework was 27% of calls, and essentially all of it was
"I did not know a current fact" or "I violated a rule I had just written." Both
are the categories a convention document and a fact-checked template eliminate.
