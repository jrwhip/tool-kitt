# Coder Spec Template

> **For pack users:** this is a skeleton for the coding standards document the `legacy-migration-coder` agent reads before doing any work. Fill in every `[STACK: ...]` marker with your stack's specifics. Delete sections that do not apply. Add sections the skeleton doesn't have if your stack has unique concerns (for example: WASM boundary crossings, serialization formats, cross-language FFI).
>
> The goal of this document is to give the coder agent a single authoritative source for every decision it would otherwise make ad-hoc. If you find the coder doing something you have to correct twice, that correction belongs here.

---

# Coder Spec - [PROJECT NAME]

> **Target stack:** [STACK: language + framework + major libraries + runtime version]
> **Legacy stack:** [STACK: what you are migrating from]
> **Project:** [STACK: project name and scope]

---

## Pattern Reference Projects

List one or two example projects (your team's own or publicly available) that embody the target architecture. The coder reads these only for calibration; nothing in the reference projects is authoritative.

- [STACK: path or URL to reference project 1, with a one-line note on what to look at]
- [STACK: path or URL to reference project 2]

---

## Build and Test Commands

The coder runs these commands to verify work before marking a requirement complete. List them explicitly so the coder does not have to guess.

| Purpose | Command |
|---|---|
| Compile or type-check | `[STACK: e.g. mvn compile, tsc --noEmit, cargo check]` |
| Run unit tests | `[STACK: e.g. mvn test -Dtest=unit, vitest run]` |
| Run component or integration tests | `[STACK]` |
| Run the full test suite | `[STACK]` |
| Lint or format | `[STACK]` |
| Build a deployable artifact | `[STACK]` |

---

## Package and Directory Structure

Describe the target layout. The coder creates new files in the matching locations; do not let it invent new layers.

```
[STACK: fill in your target tree, e.g.:
src/main/java/com/example/project/
├── controller/
├── service/
├── repository/
├── entity/
├── model/
│   ├── request/
│   └── response/
├── mapper/
├── exception/
└── config/
]
```

---

## Migration Context

> **Read this before starting work on any REQ.** This section captures the structural decisions for this migration that are not obvious from the REQ list or the legacy code alone. Every coder session reads it. The `wopr-run-crew` skill's Migration Context Prompt step writes the initial content; the developer edits it directly as scope shifts.

[MIGRATION_CONTEXT: structural decisions and notes, written by the developer or by the wopr-run-crew skill's Migration Context Prompt step at the start of each migration session]

Examples of what belongs here:

- **Module consolidation.** "The legacy app's `web` and `admin` modules are being merged into a single API. Role-based response filtering replaces separate endpoints."
- **Endpoint renames.** "Legacy `/getCase` is now `GET /api/v1/cases/{id}`. No alias is preserved."
- **Excluded scope.** "Email notifications are deferred to a later phase. REQs related to email are marked `❌ Out of Scope` in implementation tracking."
- **Data migration decisions.** "The `OLD_STATUS` column is dropped; all data migrated to `STATUS` via Flyway `V2__consolidate_status.sql` before code deploys."
- **Spec and generator version pins.** "Frontend generator is pinned to `openapi-generator-cli 7.21.0`. Backend spec is produced at `/v3/api-docs` by `springdoc-openapi 2.7.0`. Both upgrade in lockstep."
- **Known-wrong legacy behaviors.** "Legacy computes `reportDate = now()` at save time. That is a bug, not a feature. The rewrite uses the client-supplied `reportedAt` field."

If there are no structural decisions for this session, state that explicitly: "No structural changes this session; implement REQs as written."

---

## 1. Exception Handling

**Universal pattern:** throw domain exceptions at the service layer. Map them to user-facing responses at a single central point (a controller advice, a middleware, a handler registry). Controllers do not catch exceptions. The catch-all handler is forbidden.

**This stack:**

- [STACK: exception base class or error type, e.g. RuntimeException subclass, Result type, custom error trait]
- [STACK: where the central mapping lives, e.g. `@RestControllerAdvice`, Express middleware, Actix handler]
- [STACK: standard error response shape, as a code example]
- [STACK: rule about how many exception classes per service, if any]

---

## 2. Authentication and Authorization

**Universal pattern:** the target code expects an authenticated principal at every protected endpoint. The identity provider is an integration point, not part of the business logic.

**This stack:**

- [STACK: identity provider, e.g. OAuth2 resource server, custom JWT, session cookies]
- [STACK: role or permission model]
- [STACK: where role enrichment happens]
- [STACK: how to mark an endpoint public]
- [STACK: placeholder or test identity during development, if auth is deferred]

---

## 3. Logging Convention

**Universal pattern:** structured logging at every public service boundary. No `System.out`, `console.log`, `println!`, or equivalent in production code.

**This stack:**

- [STACK: logging framework, e.g. slf4j+logback, pino, tracing]
- [STACK: aspect, decorator, or middleware pattern that auto-logs method entry and exit]
- [STACK: log level policy, e.g. INFO for request boundaries, DEBUG for internal steps, ERROR only at the central exception handler]
- [STACK: any rules about log fields, e.g. correlation IDs, tenant IDs]

---

## 4. API Spec and Client Generation

**Universal pattern:** the API contract is one artifact, authored once on the backend and consumed by the frontend. The backend generates an OpenAPI spec from code annotations. The frontend generates typed client services from that spec. Neither side writes client code or schemas by hand.

**OpenAPI is mandatory for projects using this pack.** A migration with no OpenAPI spec is not in scope. If the target backend cannot emit a spec, stop here and address that first.

This section has three halves. Backend projects fill in 4a. Frontend projects fill in 4b. Any project that overrides generator output (frontend always, backend sometimes) fills in 4c.

### 4a. Backend: spec production

(Backend projects only. Frontend projects: skip to 4b.)

**Rule:** the backend generates an OpenAPI spec from code annotations. The spec is the source of truth for the API contract. The spec is versioned, pinned, and published at a stable location.

**This stack:**

- [STACK: spec generation tool and pinned version, e.g. `springdoc-openapi 2.7.0`, `zod-openapi 4.x`, `utoipa 5.x`]
- [STACK: annotation or decorator syntax the coder uses on controllers and models]
- [STACK: where generated docs are served at runtime, e.g. `/swagger-ui`, `/docs`, `/v3/api-docs`]
- [STACK: rule that every endpoint must have documented 2xx, 4xx, and 5xx responses]
- [STACK: rule against docstrings that just echo the field name]
- [STACK: build command or CI step that exports a static `openapi.json` file, e.g. "Maven `-Pswagger` profile writes `target/openapi.json`", "CI workflow `.github/workflows/publish-spec.yml`"]
- [STACK: where the published static spec artifact is consumed by the frontend, e.g. "uploaded to S3 bucket `s3://example-api-specs/<version>/openapi.json`", "fetched from `<backend-repo>` via Maven GAV coordinate", "committed to `specs/openapi.json` in the backend repo"]

**Spec version pinning (lockstep rule):**

- Every published spec artifact carries the backend's semantic version. Breaking changes bump the major version.
- The frontend's generator config pins the spec version it was generated against (see 4b). Upgrades are deliberate, not automatic.
- When the backend releases a new spec version, the frontend schedules a regeneration work item. Backend spec version and frontend generator invocation are lockstep-coordinated. The auditor blocks if the two drift.
- The current pinned spec version is recorded in the implementation-tracking document's `spec_version` header field.

**What the coder does and does not do:**

- Adds OpenAPI annotations to every new controller and model. Runs the spec-export build step and commits the resulting `openapi.json` in the same change.
- Does not hand-edit the generated `openapi.json`. If the generated output is wrong, fix the annotations, do not patch the artifact.
- When removing or changing an endpoint, updates annotations, regenerates the spec, and notes the contract delta in the frontend handoff contract in the same commit.

### 4b. Frontend: client consumption

(Frontend projects only.)

**Rule:** API services are generated from the backend's OpenAPI spec. The coder does NOT hand-write HTTP services, request types, or response types. The coder imports from a generated library and uses what is there. If a generated service is missing a field or endpoint, the fix is to regenerate the client (after the backend adds it), not to hand-write around it.

**This stack:**

- [STACK: path to the generated client lib, e.g. `libs/<app>/api/`, `@org/api-client`]
- [STACK: generator name and exact pinned version, e.g. `openapi-generator-cli typescript-angular 7.21.0`. Pin the version; do not float.]
- [STACK: generator config location, e.g. `openapitools.json`]
- [STACK: how the generator is invoked, e.g. "CI workflow at `.github/workflows/generate-api.yml`", "Nx target `pnpm nx run <lib>:generate-api`"]
- [STACK: spec source URL or artifact coordinate, e.g. "fetched from dev server at `/v3/api-docs`", "downloaded from S3 bucket", "built from `<backend-repo>` via Maven `-Pswagger` profile"]
- [STACK: spec version pinned for this generation, e.g. "openapi.json @ backend semver 4.2.1". This value lives in the implementation-tracking document's `spec_version` field.]
- [STACK: where the base URL is configured, e.g. environment file, injection token. For dev-proxy setups, use a relative base path like `/api` so the dev proxy can intercept; absolute URLs bypass the proxy.]
- [STACK: rule that regeneration is a CI step or a human-triggered action, not automatic per-commit]

**What the coder does and does not do:**

- Imports services and types from the generated lib. Does not modify the generated files.
- If the needed endpoint does not exist in the generated client, flags it in the tracking doc as a missing backend dependency. Does not write a hand-crafted fallback service.
- If the backend's OpenAPI annotations are wrong (bad path params, missing response types), flags the backend bug. Does not work around it in the frontend.
- If the generator's default output is wrong for this stack, fix via custom Mustache template (see 4c). Never hand-edit generated files.
- When the spec declares `uniqueItems: true`, the generator produces `Set<T>` at the boundary, not `T[]`. The coder writes consumers that handle Sets correctly, or converts at a single documented boundary (not scattered across the codebase).

### 4c. Post-generation customization via Mustache templates

**Rule:** when the generator's default output is wrong for this project, fix it by overriding the generator's Mustache template. Never hand-edit generated files. Hand edits are lost on regeneration; Mustache overrides survive.

**Required pattern:**

- Custom Mustache templates live alongside the generator config at a stable, version-controlled path.
- The generator config references the template directory (e.g., `templateDir` in `openapitools.json`).
- Every custom template has a header comment explaining (a) what the default produced, (b) why that was wrong for this stack, and (c) what the override changes. Example comment header: "Default `selectHeaderAccept` returns the first accepted mime type. When the spec declares `*/*` as its only response content type, this coerces the HTTP client to `responseType: 'blob'`, which breaks every JSON response. Override returns `application/json` when the accepted types include `*/*`."
- Regeneration must be idempotent: running the generator twice produces the same output.

**This stack:**

- [STACK: path to custom template directory, e.g. `openapi-generator-templates/typescript-angular/`]
- [STACK: which templates are overridden here, with a one-line reason each, e.g. "`configuration.mustache`: coerce `*/*` to `application/json`", "`api.service.mustache`: inject base URL from injection token"]
- [STACK: how the generator is configured to find the templates, e.g. "`templateDir` in `openapitools.json`"]
- [STACK: test or verification command that runs after regeneration to confirm the overrides took effect]

**When you MUST add a new Mustache override:**

- The default output produces code that does not compile.
- The default output produces code that compiles but is wrong at runtime (e.g., blob response instead of JSON, wrong base-URL resolution under a dev proxy).
- The default output violates a rule in this coder spec (e.g., uses an injection pattern forbidden by section 2).

**When you MUST NOT add a Mustache override:**

- To change cosmetic formatting of generated code. Let the generator output be what it is.
- To add domain logic to generated files. Generated files stay thin; domain logic lives in hand-written services that consume the generated clients.
- To work around a backend spec bug. Fix the spec.

---

## 5. Configuration and Secrets

**Universal pattern:** secrets come from a secrets manager in production and from a local file in development. Configuration is never hardcoded. Config files never contain secrets.

**This stack:**

- [STACK: production secrets source, e.g. AWS Parameter Store, Vault, Azure Key Vault]
- [STACK: local development source, e.g. application-local.properties, .env, config.local.yaml]
- [STACK: rule about .gitignore for the local source]
- [STACK: environment variables vs config files policy]

---

## 6. Data Access

**Universal pattern:** one authoritative data-access layer. No ad-hoc SQL scattered across services. No ORM and hand-written queries mixed in the same class.

**This stack:**

- [STACK: ORM or query library, e.g. Spring Data JPA, Prisma, Diesel, Dapper]
- [STACK: repository or data-access class convention]
- [STACK: query patterns allowed and forbidden, e.g. Specifications yes, string concatenation no]
- [STACK: transaction boundary rule]
- [STACK: fetch strategy defaults, e.g. LAZY on all relationships]
- [STACK: connection pool configuration pointer]

---

## 7. Model Naming (Request, Response, Entity)

**Universal pattern:** request models, response models, and internal entities have distinct types and distinct names. Never expose entities directly to the API. Separate request models for POST, PUT, and PATCH when the shapes differ.

**This stack:**

- [STACK: naming convention, e.g. CasePostRequestModel, CaseResponseModel, CaseEntity]
- [STACK: rule about the "DTO" suffix, if any]
- [STACK: shared-parent class rules, if any]

---

## 8. Entity and Domain Naming

- [STACK: entity class naming, e.g. `EmailAddressEntity`, `User`, `UserRecord`]
- [STACK: table-to-class naming convention if the mapping is not mechanical]
- [STACK: reserved or forbidden suffixes, e.g. no "DAO"]

---

## 9. Explicit Type Mapping

**Universal pattern:** explicit mapping at service boundaries. No auto-mapping library that couples the API contract to the internal schema by field-name coincidence. Every entity-to-model and model-to-entity conversion is explicit and reviewable.

**This stack:**

- [STACK: mapper tool or pattern, e.g. ModelMapper with strict mode, MapStruct, manual constructors]
- [STACK: where mapper beans or factories are registered]
- [STACK: one type-map per direction per entity, or shared?]

---

## 10. RESTful API Naming

**Universal pattern:** plural resource nouns. Kebab-case in URLs. Verb-free paths (no `/getCase`, it's `GET /cases/{id}`). Standard HTTP methods. Versioned base path.

**This stack:**

- [STACK: base path, e.g. `/api/v1`]
- [STACK: any deviations from the universal pattern and why]
- [STACK: status code policy on creates, e.g. 201 on POST success]
- [STACK: header contracts, e.g. X-Request-Id, X-User-Email]

---

## 11. Service Layer Method Flow

**Universal pattern:** every service method reads inputs, validates, performs the business operation, persists, returns a response model. Transaction boundary is at the service method, not higher or lower.

**This stack:**

- [STACK: transaction annotation or pattern, e.g. `@Transactional`, `with_transaction`, `db.transaction()`]
- [STACK: read-only vs write transaction convention]
- [STACK: typical method shape, as a code template]

---

## 12. Frontend Handoff Contract (UI Change Notification)

**Universal rule (not stack-specific):** every API contract change (new endpoint, deleted endpoint, changed status code, changed request or response field, changed header) gets a line in the frontend handoff contract document before the change lands. The auditor blocks merge if the handoff document is out of sync.

Point the coder at the specific file:

- **Handoff contract path:** `[STACK: e.g. UI_REQUIREMENTS_CHANGES.md, docs/api-changes.md]`
- **Required columns:** method, path, success status code, REQ ID, legacy path (if any), UI action required

See the `frontend-handoff-contract.template.md` in the pack for the structure.

---

## 13. Legacy Requirements Reference

Point the coder at the extracted-requirements document. Every REQ the coder implements must trace back to a line item there.

- **Extracted-requirements path:** `[STACK: e.g. LEGACY_REQUIREMENTS.md]`

See the `extracted-requirements.template.md` in the pack for the structure.

---

## 14. Implementation Tracking

Point the coder at the implementation-tracking document. Every REQ transition (`⏳` → `🔄` → `✅`) updates this document on the same commit as the code change.

- **Tracking document path:** `[STACK: e.g. CURRENT_REQUIREMENTS.md]`

See the `implementation-tracking.template.md` in the pack for the structure.

---

## 15. Stack-Specific Best Practices

List the anti-patterns, deprecated APIs, and training-data pitfalls the coder must avoid. This is where you correct the "most example code on the internet is wrong" problem.

- [STACK: e.g. `@Autowired` on fields is forbidden; use constructor injection]
- [STACK: e.g. `WebSecurityConfigurerAdapter` is removed in Spring Security 6; use `SecurityFilterChain`]
- [STACK: e.g. Don't use `useEffect` for data fetching; use TanStack Query]
- [STACK: e.g. Don't use Go's `interface{}`; use generics (Go 1.18+) or named types]

---

## 16. Build Configuration Discipline

- [STACK: pom.xml, package.json, Cargo.toml, build.gradle, etc.]
- [STACK: dependency pinning rules]
- [STACK: forbidden dependencies or deprecated versions]
- [STACK: artifact naming rules]

---

## 17. Schema-Driven Entity Design

**Universal pattern:** legacy schema is the authority. Entity fields mirror the schema exactly. Never add a column or field that isn't in the schema without updating both in one change.

**This stack:**

- [STACK: how nullability is declared on entity fields]
- [STACK: how column length or size is declared]
- [STACK: how sequences, auto-generators, or identity columns are declared]
- [STACK: rule about schema changes, e.g. DDL goes in a migration file before code changes]

---

## 18. Class and Method Naming

- [STACK: class suffix conventions, e.g. Controller, Service, Repository, Entity]
- [STACK: method naming patterns, e.g. verbs for actions, nouns for queries]
- [STACK: forbidden names, e.g. `DoStuff`, `Helper`, `Utils`]

---

## 19. Code Comments

**Universal rule:** comments explain WHY, not WHAT. Business rules that aren't obvious from the code deserve comments. Boilerplate does not.

**This stack:** [STACK: anything stack-specific about doc comments, e.g. Javadoc conventions, rustdoc format, JSDoc tags]

---

## 20. Time Zone and Localization Handling

**Universal pattern:** one authoritative zone for persistence, one for the application runtime, explicit conversion at the boundary. No hardcoded offsets anywhere.

**This stack:**

- [STACK: persistence layer zone, e.g. Oracle stores `America/Denver`, Postgres stores UTC]
- [STACK: application runtime zone, e.g. ECS container runs UTC]
- [STACK: where conversion happens, e.g. a `TimeZoneConstants` class, middleware, serializer]
- [STACK: DST anchor date used in tests]

---

## 21. Additional Stack-Specific Patterns

Anything the above sections did not cover. Examples: file upload handling, websocket patterns, background job patterns, multi-tenant isolation, feature flag integration, observability (metrics, tracing, profiling).

- [STACK: add sections as needed]

---

## 22. Coverage Gate

**Universal rule:** a REQ does not advance from `🔄 In Progress` to `✅ Implemented` until the coverage gate passes. The coder marks a REQ as `✅` only when all five conditions are met:

1. **Build passes.** `[STACK: build command]` exits 0.
2. **Tests pass.** `[STACK: full test command]` exits 0. Zero new failures.
3. **Coverage thresholds met** per the tester spec: line coverage ≥ `[STACK: floor, e.g. 80%]`, branch coverage ≥ `[STACK: floor, e.g. 70%]`. See `[STACK: tester-spec path]` section 6.
4. **Handoff contract current.** If the REQ changed the API surface (new endpoint, removed endpoint, changed status code, changed request or response shape, changed header), `[STACK: handoff contract path]` has a line item covering the change with a JSON Pointer into the published spec.
5. **Static-analysis quality gate passes.** The project's configured static-analysis tool (e.g. SonarCloud, SonarQube, ruff, ESLint, or equivalent) reports the configured Quality Gate as `Passed` for the latest scan covering this REQ's commits. Critical, blocker, and major issues introduced by this REQ count as failures even when the project's overall gate would otherwise pass.

If any condition fails, the REQ stays `🔄` and the failure is logged in the implementation-tracking document's `coverage_status` field for that log entry.

The auditor verifies all five conditions independently before issuing an `UNBLOCKED` verdict. A coder marking a REQ `✅` without the gate passing is a BLOCKER finding at audit.

**This stack (static-analysis gate):**

- [STACK: platform, e.g. SonarCloud, SonarQube self-hosted, ruff/mypy CI gate, ESLint CI gate, none-yet]
- [STACK: project key or organization, e.g. `your-org_your-repo` on `your-org` org]
- [STACK: how the scan runs, e.g. `mvn sonar:sonar -Dsonar.token=$SONAR_TOKEN` locally and via `.github/workflows/sonar.yml` on every push, or `ruff check .` / `eslint .` locally and via CI on every push]
- [STACK: where the gate result is fetched from, e.g. `GET /api/qualitygates/project_status?projectKey=<key>` against the platform's API; auditor reads the response]
- [STACK: which severities count as failures for this gate, e.g. BLOCKER, CRITICAL, MAJOR; informational and minor flagged but not gating]
- [STACK: who configures the platform-side Quality Gate (project lead, security team)]

---

## Key Files

Pointer list of files the coder agent should always be aware of:

- [STACK: e.g. `ExceptionController.java` - central exception mapping]
- [STACK: e.g. `SecurityConfig.java` - security wiring]
- [STACK: e.g. `TimeZoneConstants.java` - timezone constants]
- [STACK: add any file where a pattern change would ripple through the rest of the codebase]
