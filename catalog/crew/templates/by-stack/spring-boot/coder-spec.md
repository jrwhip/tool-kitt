# Coder Spec - TODO: project name

> **Stack:** Spring Boot 3.x, Java 21, Maven, springdoc-openapi, JPA/Hibernate.
> **This file:** stack-pre-filled starting point. Adjust per project; do not start from scratch.
> **For the deep version:** `catalog/crew/templates/by-stack/_generic/coder-spec.md`.

---

## Migration Context

Structural decisions for this session live here. Examples:

- Module consolidation: `[TODO if applicable]`
- Endpoint renames: `[TODO if applicable]`
- Excluded scope: `[TODO if applicable]`
- Database schema changes: `[TODO if applicable]`
- Known-wrong legacy behaviors NOT to preserve: `[TODO if applicable]`

If this is a net-new project, write `No structural changes this session; implement REQs as extracted.`

---

## Build and Test Commands

| Purpose | Command |
|---|---|
| Clean build with tests | `mvn clean verify` |
| Compile only | `mvn compile` |
| Run tests | `mvn test` |
| Integration tests | `mvn verify` (the `failsafe` plugin runs `*IT.java`) |
| Coverage report | `mvn verify` (JaCoCo binds to `verify`); report at `target/site/jacoco/index.html` |
| Run the application | `mvn spring-boot:run` |
| Regenerate the static OpenAPI artifact | `mvn springdoc-openapi:generate` (or whatever profile this project uses) |

If the project uses Gradle instead of Maven, replace `mvn <goal>` with `./gradlew <task>` and adjust paths.

---

## Source Layout

| Concern | Path |
|---|---|
| Production source | `src/main/java/<base_package>/...` |
| Resources | `src/main/resources/` |
| Tests | `src/test/java/<base_package>/...` |
| Static OpenAPI artifact | `src/main/resources/openapi.json` (or wherever `wopr.yml` declares) |
| Database migrations | `src/main/resources/db/migration/` (Flyway) |

`base_package` lives in `wopr.yml` (`project.base_package`). All new classes go under that root.

---

## Architecture Patterns

### Layered structure
- `controller/` - REST endpoints. Only HTTP concerns.
- `service/` - business logic. No HTTP, no SQL.
- `repository/` - Spring Data JPA interfaces. No business logic.
- `entity/` - JPA entities. No logic beyond validation annotations.
- `dto/` - request and response models. Generated from OpenAPI when possible; hand-written only when no spec exists yet.
- `mapper/` - DTO <-> entity conversion. Prefer MapStruct.

### Dependency injection
- Constructor injection only. `@Autowired` on fields is forbidden in new code.
- Lombok's `@RequiredArgsConstructor` is the project's preferred shortcut.
- Never use field injection (`@Autowired private SomeService svc;`).

### REST controllers
- `@RestController` (not `@Controller` + `@ResponseBody` on every method).
- Every endpoint annotated with `@Operation` (springdoc) so the OpenAPI spec carries `summary`, `description`, request/response shapes, and example values.
- Status codes via `ResponseEntity.<status>().body(...)` or `@ResponseStatus`.
- Validation via `@Valid` on the request body parameter; constraint annotations on the DTO.

### Transactions
- `@Transactional` at the SERVICE layer, not the controller.
- Read-only operations: `@Transactional(readOnly = true)`.

### Exception handling
- A single `@RestControllerAdvice` class maps exceptions to HTTP responses.
- No `catch (Exception e) { return null; }` anywhere. Either handle the exception or let it propagate.
- Domain exceptions extend a project-specific base (`<Project>RuntimeException` or similar).

---

## OpenAPI Production

The backend is the OpenAPI source of truth. Every controller and DTO touched MUST update its annotations, then regenerate the static spec.

1. Add or update `@Operation`, `@ApiResponse`, `@Schema` annotations on the controller method and the DTOs it references.
2. Run `mvn spring-boot:run` briefly (or the `springdoc:generate` task) to refresh `src/main/resources/openapi.json`.
3. Commit the regenerated `openapi.json` in the same change.

The auditor BLOCKS on:
- A controller method with no `@Operation`.
- A DTO field with no `@Schema(description = "...")`.
- An annotation change that did not regenerate the spec.

The pinned springdoc version lives in `wopr.yml` (`openapi.pinned_generator_version`) and matches `pom.xml`.

---

## Persistence

### Entities
- `@Entity` classes are POJOs with `@Id`, field annotations, and JPA relationship annotations. No business logic.
- `@Column(nullable = false)` and `@Column(length = N)` match the database schema. Schema drift is a BLOCKER.
- Use `@Version` for optimistic locking on aggregate roots when applicable.

### Repositories
- Extend `JpaRepository<Entity, Id>` or `CrudRepository`.
- Custom queries use `@Query` with JPQL (preferred) or native SQL when necessary. Annotate native queries with `nativeQuery = true`.

### Migrations
- All schema changes go through Flyway under `src/main/resources/db/migration/`.
- Migration filenames: `V<version>__<description>.sql`.
- Never hand-edit a checked-in migration. Add a new `V<next>__<correction>.sql` instead.

---

## Anti-Patterns (auditor surfaces these as BLOCKERs)

- Field injection (`@Autowired` on a private field).
- `@Controller` + `@ResponseBody` instead of `@RestController`.
- Business logic in controllers.
- HTTP concerns in services.
- Database access from controllers.
- `@Transactional` on controller methods.
- Catch-all exception swallowing.
- Hand-edited generated OpenAPI artifacts (the static `openapi.json` is generated; do not edit it directly).
- `System.out.println` for logging. Use SLF4J via Lombok's `@Slf4j`.

---

## Coverage Gate

1. Build passes. `mvn clean verify` exits 0.
2. Full test suite passes. Zero new failures.
3. Line coverage >= **TODO: project floor (start at 80)**. Branch coverage >= **TODO: project floor (start at 70)**. Measured by JaCoCo at `target/site/jacoco/index.html`.
4. If the REQ touched the API surface, the frontend handoff contract has a line item with a JSON Pointer into `openapi.json`.
5. Static-analysis Quality Gate (SonarCloud, SonarQube, or equivalent) is `Passed` for the latest scan covering this REQ's commits.

---

## Spec Maintenance

When `spec_writes` is ON (default), amend this spec when a new pattern emerges. Examples:

- A new idiom for cross-cutting concerns (a new annotation, a new aspect).
- A naming convention for a new category of class.
- A decision about how to handle a specific Hibernate / JPA quirk.
- A build-config rule (Maven profile, dependency version pin, surefire/failsafe configuration).

Two inconsistent patterns are NEVER tolerated. If the new pattern replaces an old one, rewrite the old usage.
