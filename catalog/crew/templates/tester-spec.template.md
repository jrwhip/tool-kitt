# Tester Spec Template

> **For pack users:** this is a skeleton for the testing standards document the `crew-tester` agent reads before writing any tests. Fill in every `[STACK: ...]` marker. Delete sections that do not apply. Add sections the skeleton doesn't have if your stack has unique testing concerns (property-based testing, snapshot testing, mutation testing, fuzz testing, etc.).
>
> The goal is to give the tester agent a single authoritative source for what tests belong in which directory, how they are named, what they cover, and what they are forbidden to do. If you find yourself correcting the tester twice, the correction belongs here.

---

# Tester Spec - [PROJECT NAME]

> **Target stack:** [STACK]
> **Test framework:** [STACK: e.g. JUnit 5 + Mockito + MockMvc, Vitest + Testing Library, pytest + httpx]
> **Coverage tool:** [STACK: e.g. JaCoCo, c8, coverage.py]

---

## Requirements Sources

The tester agent reads these before writing any tests.

| Document | Path | What it tells the tester |
|---|---|---|
| Implementation tracking | `[STACK: e.g. CURRENT_REQUIREMENTS.md]` | Which REQs need coverage, which need disabled stubs, which need nothing. Also carries the pinned `spec_version` and `generator_version`. |
| Extracted requirements | `[STACK: e.g. LEGACY_REQUIREMENTS.md]` | Acceptance criteria for each REQ |
| Coder spec | `[STACK: e.g. CODER_SPEC.md]` | What the production code is supposed to look like, the Migration Context for this session, and the coverage gate definition (section 22). |
| OpenAPI spec | `[STACK: e.g. /v3/api-docs, specs/openapi.json]` | Source of truth for endpoint shapes, status codes, and model types. Tests assert against the spec, not against hand-copied types. |

---

## Build and Test Commands

| Purpose | Command |
|---|---|
| Run unit tests only | `[STACK: e.g. mvn test -Dtest='unit.**']` |
| Run component or integration tests only | `[STACK]` |
| Run the full suite | `[STACK]` |
| Run tests for a single file | `[STACK: e.g. mvn test -Dtest=WidgetServiceTest, vitest run widget-service.test.ts]` |
| Generate coverage report | `[STACK]` |
| View coverage report | `[STACK: path to generated report file]` |

---

## Coverage Configuration

- **Tool:** [STACK]
- **Targets:** [STACK: e.g. line coverage >= 80%, branch coverage >= 70%, per-package excludes]
- **Scope:** [STACK: which packages or directories are in scope, which are excluded and why]
- **CI enforcement:** [STACK: does CI fail on drop? what threshold?]

---

## Generated Types and Spec-Driven Fixtures

**Rule:** when the coder spec's section 4 mandates a generated client, tests use the same generated types for fixtures, mocks, and assertions. Hand-written type copies are forbidden.

**Why:** when the spec changes and the client regenerates, tests fail loud at the type boundary instead of drifting silently. A hand-written `WidgetResponse` in a test will compile forever even when the real generated type has added a new required field. By the time someone notices, production is already broken.

**How:**

- Import model types from the generated client (e.g., `import type { Widget } from '@org/api-client'`) rather than redeclaring them.
- Build fixtures with the generated type. If a fixture needs to omit fields, use the generator's request type that already omits them, or `satisfies` / equivalent to keep the compiler honest.
- When mocking services, mock the generated service interface, not a shape-only copy.

**`uniqueItems: true` boundary (if your generator honors it):**

When the spec declares a collection field with `uniqueItems: true`, some generators emit `Set<T>` at that boundary instead of `T[]`. Test fixtures and mock responses for those fields must produce the same container type the generator emits. Check one generated file from your client to confirm the container type, then write fixtures accordingly.

**This stack:**

- [STACK: import path for generated types, e.g. `import type { ... } from '@org/api-client'`]
- [STACK: where shared test fixtures live, e.g. `src/test/java/com/example/fixtures/`, `src/test-utils/fixtures.ts`]
- [STACK: rule on whether to use generator-provided factories, if any]
- [STACK: rule on generated code coverage: generated files are excluded from coverage denominators; verify the exclusion pattern matches the generator's output path]

---

## Directory Structure

The tester creates test files in the directories this section specifies. Mixing test types across directories breaks the auditor's layer checks.

```
[STACK: fill in your test tree, e.g.:
src/test/java/com/example/project/
├── unit/
│   ├── service/
│   ├── mapper/
│   └── util/
├── component/
│   ├── controller/
│   └── integration/
└── config/
    └── TestConfig.java
]
```

Rules:

- [STACK: e.g. Unit tests live in `unit/`. No Spring context loading. Mocks only.]
- [STACK: e.g. Component tests live in `component/`. Import the shared TestConfig. Use MockMvc or a test HTTP client.]
- [STACK: e.g. Integration tests (if distinct) live in `integration/`. Use real dependencies via Testcontainers.]

---

## 1. Shared Test Configuration

If the stack requires a shared test configuration (a test-only bean registry, a fixture module, a test harness), define it here. Otherwise, delete this section.

- **File:** [STACK: e.g. `TestConfig.java`, `test-setup.ts`, `conftest.py`]
- **Purpose:** [STACK: what the shared config provides: mock beans, test database, fake secrets, etc.]
- **When to import:** [STACK: every component test; never in unit tests; always in integration tests]
- **Code template:** [STACK: inline code example]

---

## 2. Test Properties and Fixtures

Configuration files the tests rely on.

- **File:** [STACK: e.g. `application-test.properties`, `.env.test`, `pytest.ini`]
- **Key settings:** [STACK: database URL for tests, mock auth, swagger URI, timezone]
- **Forbidden settings:** [STACK: anything that must never point at production]

---

## 3. Unit Test Pattern

**Universal rules:**

- No framework context loading in unit tests. No `@SpringBootTest`, no `render()` with a full provider tree, no `pytest.fixture(scope='session')` that starts a real database.
- Mock the collaborators. Test the unit in isolation.
- One test method per observable behavior. Happy path, null or empty input, validation failure, business-rule enforcement, not-found, error mapping.

**Stack-specific:**

- [STACK: mocking library, e.g. Mockito, vi.fn(), pytest-mock]
- [STACK: annotation or setup pattern, e.g. `@ExtendWith(MockitoExtension.class)`, `beforeEach`, fixtures]
- [STACK: preferred assertion library, e.g. AssertJ, @testing-library, assertpy]
- [STACK: typical unit test shape, as a code template]

**What every unit test covers:**

| Path | Required? | Notes |
|---|---|---|
| Happy path | Always | The primary success case |
| Null or empty input | Always for public methods | |
| Validation failure | When the method validates | |
| Business-rule enforcement | When the method enforces a rule | |
| Not-found | For lookups | Usually returns 404 at the controller boundary |
| Exception mapping | When the method throws | Verify the exception type and message |

---

## 4. Component / Integration Test Pattern

**Universal rules:**

- Exercise the full request-to-response path through the framework.
- One test per HTTP-status-code path per endpoint. If the coder spec says "this endpoint can return 200, 400, and 500," you write three tests, even if the 500 path is hard to trigger.
- Import the shared test configuration.
- Use the same auth mechanism the production code uses, even if auth is permit-all in this build.

**Stack-specific:**

- [STACK: HTTP test client, e.g. MockMvc, supertest, httpx.AsyncClient]
- [STACK: test slicing annotation, e.g. `@WebMvcTest`, `@MockMvcTest`]
- [STACK: how to seed test data]
- [STACK: how to tear down between tests]

**Required coverage per endpoint:**

| HTTP status | Required? | Notes |
|---|---|---|
| 2xx success | Always | Typically 200 or 201 |
| 4xx client error | Usually | 400 for validation, 404 for not-found, domain-specific codes as applicable |
| 5xx server error | When the coder spec has explicit 5xx paths | Triggered via mocked repository failure or similar |

---

## 5. Time Zone Test Anchoring

If the target code handles time zones (and most business apps do), tests must cover both DST and non-DST dates. Time bugs hide until the spring/fall transition.

- **DST anchor date:** [STACK: e.g. 2024-06-15 (during DST in America/Denver)]
- **Non-DST anchor date:** [STACK: e.g. 2024-01-15 (not during DST)]
- **Rule:** every test that constructs a `LocalDateTime`, `Date`, `chrono::DateTime`, or equivalent must use one of these two anchors or be explicit about why.

If the target code does not handle time zones in any meaningful way, delete this section.

---

## 6. Coverage Standards

- **Line coverage floor:** [STACK: e.g. 80%]
- **Branch coverage floor:** [STACK: e.g. 70%]
- **Excluded classes or files:** [STACK: generated code, configuration classes, main entry points]
- **Generated code is always excluded.** Files produced by the OpenAPI generator (see coder spec section 4) do not count toward either coverage numerator or denominator. Verify the exclusion pattern in the coverage tool config matches the generator's actual output path.

### Coverage gate (contract with the coder and auditor)

The coverage gate is a five-condition contract owned and stated by the crew orchestrator (`wopr-run-crew`); the coder spec's section 22 carries its stack-specific commands and floors. The tester spec's job is to make conditions 3 (coverage thresholds) and 5 (static-analysis Quality Gate; see section 7 of this spec) verifiable and recorded. On every tester-agent run, the tester:

1. Runs the full coverage command after writing tests and confirms line and branch coverage meet or exceed the floors above.
2. Records the measured coverage in the implementation-tracking document's `coverage_status` field on the log entry for the current REQ, in the canonical format defined in section 7: `line XX% / branch YY% / static_analysis: PASS|FAIL (reason) / gate: PASS|FAIL (reason)`. There is exactly one format; the auditor parses it.
3. Does not mark a REQ's tests complete until the measured coverage meets the floor. If coverage is short, the tester either adds tests to close the gap or flags the gap in the tracking document with a concrete description (e.g., "REQ-X-2 missing: 404 path, 406 business-rule-reject path").

The auditor cross-checks the tracking document's `coverage_status` against a fresh coverage report. Drift between the two is a BLOCKER finding. A tester marking coverage as PASS when a fresh report shows FAIL is a BLOCKER finding.

**What the auditor checks:** coverage targets are met per package; no untested public service method; no untested HTTP-status-code path per endpoint; every endpoint covered by a test has a JSON Pointer reference matching the spec's current state.

---

## 7. Static-Analysis Quality Gate

The tester is responsible for triggering the static-analysis scan after writing tests and before reporting `coverage_status: gate: PASS`. Coverage and static-analysis findings are evaluated together; coverage measurement alone does not satisfy the gate (see coder spec section 22 condition 5).

**Universal rule:** the tester runs the project's configured static-analysis scan against the latest commit, fetches the Quality Gate result, and includes the verdict in the `coverage_status` field. Format: `line XX% / branch YY% / static_analysis: PASS|FAIL (reason) / gate: PASS|FAIL`. Both `static_analysis` and the overall `gate` must be PASS for the REQ to advance.

**This stack:**

- **Platform:** [STACK: e.g. SonarCloud, SonarQube self-hosted, ruff/mypy CI gate, ESLint CI gate]
- **Project key:** [STACK: e.g. `your-org_<repo-name>`]
- **Local scan command:** [STACK: e.g. `mvn -B verify sonar:sonar -Dsonar.token=$SONAR_TOKEN -Dsonar.projectKey=<key>`, or `ruff check .` / `eslint .`]
- **CI scan workflow:** [STACK: e.g. `.github/workflows/sonar.yml` runs on push to feature branches and on PR open]
- **Quality Gate fetch:** [STACK: e.g. tester runs `curl -sS -u "$SONAR_TOKEN:" "$SONAR_URL/api/qualitygates/project_status?projectKey=<key>"` and parses `projectStatus.status` (`OK` or `ERROR`); for a plain linter gate, the exit code of the local scan command doubles as the fetch]
- **Severity thresholds for this gate:** [STACK: e.g. BLOCKER, CRITICAL, and MAJOR issues introduced on this branch fail the gate; MINOR and INFO are reported but non-blocking]
- **Required token environment variables:** [STACK: e.g. `SONAR_TOKEN` set in CI secrets and in developer's `~/.zshrc` or `.env.local`]

**What the tester does:**

1. After running the test suite and confirming pass + coverage thresholds, runs the local scan command (or pulls the CI scan result if CI ran first on the same commit).
2. Polls the platform until the analysis completes for the current commit (some platforms, e.g. SonarCloud, run analysis asynchronously; project size determines wait time).
3. Records the Quality Gate verdict and any new BLOCKER/CRITICAL/MAJOR findings introduced by this REQ in the implementation-tracking log entry.
4. If the gate fails, treats the failure the same as a coverage-floor failure: REQ stays `🔄`, the gap is described concretely, and the coder addresses it before re-entry.

**What the auditor cross-checks:** fresh fetch of the Quality Gate from the platform's API; comparison against the tester's recorded verdict; drift is a BLOCKER finding. The coder spec section 22 condition 5 is the canonical rule; this section operationalizes it for the tester.

If the project does not yet have a static-analysis platform configured, the tester records `static_analysis: SKIPPED (platform not configured)` and the auditor produces a WARNING flagging the absence. Skipping is allowed only as a project-level deferral with explicit acknowledgment in the Migration Context; default expectation is a configured platform.

---

## 8. Test Naming Convention

**Universal rule:** test method names describe the behavior under test in present or past tense, not the method being called.

**Stack-specific:**

- [STACK: naming template, e.g. `should<ExpectedBehavior>When<Condition>`, `given_X_when_Y_then_Z`, `test_<unit>_<condition>_<expected>`]
- [STACK: is there a case convention? camelCase, snake_case, kebab-case?]
- [STACK: required prefixes or suffixes, e.g. `test_`, `Test.java`]

**Examples for this stack:**

| Under test | Condition | Test method name |
|---|---|---|
| createWidget | valid input | [STACK: e.g. `shouldCreateWidgetWhenInputIsValid`] |
| createWidget | null input | [STACK: e.g. `shouldThrowWhenInputIsNull`] |
| createWidget | schema constraint violation | [STACK: e.g. `shouldThrow500WhenNameExceedsMaxLength`] |

---

## Key Files

- [STACK: e.g. `TestConfig.java` - shared component test config]
- [STACK: e.g. `application-test.properties` - test properties]
- [STACK: e.g. `TimeZoneTestAnchors.java` - shared DST anchor dates]
- [STACK: any fixture or factory class used across tests]
