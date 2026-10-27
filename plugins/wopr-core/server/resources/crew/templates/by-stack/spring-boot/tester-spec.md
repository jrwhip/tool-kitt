# Tester Spec - TODO: project name

> **Stack:** Spring Boot 3.x, Java 21, JUnit 5, Mockito, Spring MockMvc, JaCoCo, Maven.
> **This file:** stack-pre-filled starting point.
> **For the deep version:** the generic `tester-spec.template.md` in the crew pack's templates (fetch via `get_pack_template`, `pack="crew"`, `name="tester-spec.template.md"`).

---

## Requirements Sources

| Document | Path | Purpose |
|---|---|---|
| Implementation tracking | `IMPLEMENTATION_TRACKING.md` | Which REQs need coverage |
| Extracted requirements | (legacy projects) `EXTRACTED_REQUIREMENTS.md` | Acceptance criteria per REQ |
| Coder spec | `specs/coder-spec.md` | What the production code should look like |
| OpenAPI spec | `src/main/resources/openapi.json` | Source of truth; integration tests assert against generated types |

---

## Build and Test Commands

| Purpose | Command |
|---|---|
| Compile tests | `mvn test-compile` |
| Run unit tests | `mvn test` |
| Run unit + integration tests | `mvn verify` |
| Coverage report | `mvn verify` (JaCoCo binds to `verify`); HTML at `target/site/jacoco/index.html` |
| Run a single test class | `mvn test -Dtest=<ClassName>` |
| Run a single test method | `mvn test -Dtest=<ClassName>#<method>` |

The tester records coverage from JaCoCo's XML report at `target/site/jacoco/jacoco.xml` (parsed by the project's static-analysis platform, e.g. SonarCloud or SonarQube) or the HTML at `target/site/jacoco/index.html` (human-readable).

---

## Test File Layout

| Type | Location | Naming |
|---|---|---|
| Unit test | `src/test/java/<base_package>/...` | `<ClassName>Test.java` |
| Integration test | `src/test/java/<base_package>/...` | `<Feature>IT.java` |
| MockMvc / controller slice | `src/test/java/<base_package>/controller/` | `<Controller>Test.java` |
| Repository test | `src/test/java/<base_package>/repository/` | `<Repository>Test.java` |

Maven Surefire runs `*Test.java`. Failsafe runs `*IT.java`. The naming controls which lifecycle phase the tests run in. Mismatched names mean tests do not run at all; the auditor checks this.

---

## What to Test

Every service public method:
- Happy path
- Null / empty input
- Validation failure
- Business-rule enforcement (state transitions, role checks, etc.)
- Not-found cases

Every controller endpoint (via MockMvc):
- 200 (or 201) happy path
- 400 validation failure
- 404 not found
- 500 unexpected error (when applicable)
- Domain-specific codes (406, 409, 422) per endpoint

Every repository:
- Persist + retrieve round-trip via `@DataJpaTest` slice.
- Custom `@Query` methods.

Every entity:
- JPA mappings round-trip (one entity per class is enough; this catches the bulk of mapping errors).

---

## Test Isolation

- Unit tests do NOT load the Spring context. Use plain JUnit + Mockito.
- Controller tests use `@WebMvcTest(controllers = <ControllerClass>.class)` to load only the web layer.
- Repository tests use `@DataJpaTest`.
- Full-stack integration tests use `@SpringBootTest` and only when nothing thinner will do (full context loads are slow).

Loading `@SpringBootTest` for what could be a `@WebMvcTest` is a code smell the auditor flags.

---

## Shared Test Configuration

If the project has a shared base test class (`@SpringBootTest` setup, common test profiles, test fixtures), it lives at `src/test/java/<base_package>/AbstractTest.java` or similar. Every integration test extends it. Hand-rolling test config in every test class is the anti-pattern.

---

## Time and Date Anchoring

Tests that depend on `LocalDate.now()` or `Instant.now()` MUST use a fixed clock:

```java
@SpringBootTest(properties = "app.clock=2024-06-15T12:00:00Z")
```

or inject a `Clock` bean. Tests that pass at one wall-clock time but fail at another are a deferred BLOCKER.

If the project enforces DST and non-DST anchors, use `2024-01-15` (non-DST) and `2024-07-15` (DST) as the canonical fixtures.

---

## Fixtures and Mocks

### Use generated types
Test fixtures import response and request models from the project's own DTO classes. Hand-rolled shape copies in test files are a BLOCKER; when the schema changes, the compiler should tell you.

### `uniqueItems: true` collection fields
If OpenAPI declares `uniqueItems: true`, the project's DTO uses `Set<T>`. Build test fixtures with `Set.of(...)`, not `List.of(...)`. The compiler catches some mismatches; the test must use the same container type the production code emits.

### Coverage exclusions
- Generated code (the OpenAPI-generated client lib in a separate module, or any code under `target/generated-sources/`) MUST be excluded from JaCoCo coverage. Configure in `pom.xml` under the JaCoCo plugin's `excludes` list.
- Configuration classes (`@Configuration`) with no logic can be excluded.
- DO NOT exclude controllers, services, or repositories.

---

## Anti-Patterns (auditor surfaces these as BLOCKERs)

- A test method that does not start with `test` (Surefire / Failsafe by default expect class-level matching; method name conventions matter less but `should<Behavior>_when<Condition>` reads better than `test1`).
- Tests that hit a real database. Use `@DataJpaTest` (H2 in-memory) or Testcontainers.
- Tests that hit real HTTP endpoints. Use MockMvc or WireMock.
- `@Disabled` without a `value` explaining why and a TODO for the fix.
- Snapshot / golden-file tests for JSON output. Use explicit assertions on fields.
- `Thread.sleep` in tests. Use Awaitility for async waits.

---

## Coverage Gate (tester records, auditor cross-checks)

After tests pass, record on the REQ's implementation-tracking log entry:

```
coverage_status: line XX% / branch YY% / static_analysis: PASS / gate: PASS
```

Or on failure:

```
coverage_status: line XX% / branch YY% / static_analysis: PASS / gate: FAIL (specific reason)
```

PASS means:
- `mvn clean verify` exits 0.
- All `*Test` and `*IT` classes run; zero new failures.
- Line >= `[TODO: floor]`, branch >= `[TODO: floor]` per JaCoCo.
- The project's static-analysis Quality Gate (SonarCloud, SonarQube, or equivalent) is `Passed` for the relevant commit. New BLOCKER / CRITICAL / MAJOR findings introduced by this REQ fail the gate.

Never report `gate: PASS` without a fresh `mvn clean verify` measurement.

---

## Spec Maintenance

When `spec_writes` is ON (`wopr.yml` `specs.spec_writes`; default OFF), amend this spec when a new coverage shape or fixture idiom emerges. Examples:

- A new Testcontainers idiom (a shared base class for a specific service).
- A coverage rule for a new test category (parameterized JUnit 5 tests).
- A new test-isolation rule discovered after a flaky test was diagnosed.
- A JaCoCo configuration tweak other test authors will need.
