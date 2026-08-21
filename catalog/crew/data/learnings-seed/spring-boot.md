## LRN-2024-01-02-a: Constructor injection only; field injection breaks tests

```meta
date: 2024-01-02
project: _seed
stack: [spring-boot]
req: []
auditor_run: seed@spring-boot
severity: warning
seed: true
```

**What happened.** A service used `@Autowired` on a private field. The Spring context wired it fine at runtime, but unit tests that constructed the service via `new` could not inject mocks. Tests resorted to reflection hacks or `@SpringBootTest` (slow) to wire mocks.

**Why it matters.** Field injection hides the dependency surface and forces the test to load a Spring context just to construct the class. Constructor injection lets tests use plain Mockito + plain `new`, an order of magnitude faster.

**Pattern to encode.** Beans declare dependencies as constructor parameters. Lombok's `@RequiredArgsConstructor` is the project's preferred shortcut. Auditor BLOCKS on `@Autowired` on a field in new code.


## LRN-2024-01-02-b: @Transactional belongs at the service layer

```meta
date: 2024-01-02
project: _seed
stack: [spring-boot]
req: []
auditor_run: seed@spring-boot
severity: blocker
seed: true
```

**What happened.** A controller method was annotated `@Transactional`. Spring's transactional proxy sits in front of the controller bean; the transaction opened on every request and rolled back only on RuntimeException, masking domain errors that should have rolled back.

**Why it matters.** Controllers handle HTTP, not transactions. Putting `@Transactional` on a controller couples HTTP concerns to persistence semantics. Read-only operations should be explicit (`@Transactional(readOnly = true)` at the service), and write operations should commit/rollback per service-method boundary, not per request.

**Pattern to encode.** `@Transactional` lives on `@Service` methods. Read-only operations: `@Transactional(readOnly = true)`. Never on a controller or repository (repositories already inherit from Spring Data's transactional defaults).


## LRN-2024-01-02-c: Catch-all exception swallowing hides production bugs

```meta
date: 2024-01-02
project: _seed
stack: [spring-boot]
req: []
auditor_run: seed@spring-boot
severity: blocker
seed: true
```

**What happened.** A method wrapped its body in `try { ... } catch (Exception e) { return null; }`. The first real failure under prod traffic returned `null` to the caller without a stack trace; the operator spent two days finding the swallow before they could fix the underlying NullPointer.

**Why it matters.** Catch-all swallowing turns a loud failure into a silent one. The caller assumes success, the next layer NullPointers downstream, and the original cause is gone.

**Pattern to encode.** Project exceptions extend a project-specific base (`<Project>RuntimeException`). A single `@RestControllerAdvice` maps known exceptions to HTTP responses. Never `catch (Exception e) { /* swallow */ }`. Never `catch (Exception e) { return null; }`. Either handle or propagate.


## LRN-2024-01-02-d: ETag derived from entity.toString() drifts across sessions

```meta
date: 2024-01-02
project: _seed
stack: [spring-boot]
req: []
auditor_run: seed@spring-boot
severity: warning
seed: true
```

**What happened.** A POST endpoint computed the ETag from `entity.toString()`. Hibernate's default `toString()` includes proxy metadata that changes session-to-session, so the freshly-created entity's ETag was unstable between the create response and the next read.

**Why it matters.** Optimistic locking depends on a stable ETag for the same logical state. An ETag that flips between calls breaks every conditional update with a false 412.

**Pattern to encode.** Compute ETags from a canonical DTO projection with sorted fields. Never from `entity.toString()`, never from a persistence-managed instance directly.


## LRN-2024-01-02-e: Java version pin must match CI workflow setup-java input

```meta
date: 2024-01-02
project: _seed
stack: [spring-boot]
req: []
auditor_run: seed@spring-boot
severity: blocker
seed: true
```

**What happened.** `pom.xml` pinned `<java.version>21</java.version>`. `.github/workflows/build.yml` had `uses: actions/setup-java@v4` with `java-version: 17`. Local builds passed (developer had Java 21). CI builds passed too (compiled on 17, ran on 17). Production deployed the 17-compiled artifact. A method using `java.util.SequencedCollection` (Java 21) threw `NoSuchMethodError` at runtime.

**Why it matters.** Version drift between build config and CI is invisible until the runtime hits a missing API. Lockstep is non-negotiable.

**Pattern to encode.** Any framework or runtime version pinned in `pom.xml` (or `build.gradle`) MUST match the corresponding value in every `.github/workflows/*.yml` that builds the project. Auditor BLOCKS on drift.


## LRN-2026-05-13-a: Spring Boot 4 renamed spring-boot-starter-aop to spring-boot-starter-aspectj

```meta
date: 2026-05-13
project: _seed
stack: [spring-boot, spring-boot-4, maven]
req: []
auditor_run: seed@spring-boot-4
severity: warning
seed: true
```

**What happened.** In Spring Boot 4.x the AOP starter was renamed. `spring-boot-starter-aop` produces a missing-bean error at runtime when an `@Aspect` is loaded under the SB4 parent. The correct starter is `spring-boot-starter-aspectj`.

**Why it matters.** Crew agents trained on SB 3.x docs default to the old name. The error surface is a `NoSuchBeanDefinitionException` for the aspect, far from the pom, so the cause is non-obvious.

**Pattern to encode.** When `spring-boot-starter-parent` major version is at least 4 AND any class is annotated `@Aspect`, the pom must declare `spring-boot-starter-aspectj`. Auditor: grep `<artifactId>spring-boot-starter-aop</artifactId>` against `<spring-boot-starter-parent version >= 4>` and flag.


## LRN-2026-05-13-b: Read-write entity split via @Immutable view entity

```meta
date: 2026-05-13
project: _seed
stack: [spring-boot, jpa, hibernate, oracle]
req: []
auditor_run: seed@spring-boot
severity: warning
seed: true
```

**What happened.** A legacy schema with resolved-FK Oracle views was modelled with two entities per logical resource: a mutable `@Entity` on the writable table, and a separate `@Entity @Immutable` on the view that pre-resolves FK descriptions. Write paths use the mutable entity; read paths return the resolved one.

**Why it matters.** Hibernate's `@Immutable` suppresses UPDATE/DELETE SQL generation, so the read-only contract is enforced at the ORM layer rather than by convention. Without the split, agents either pollute the write model with `@Transient` resolved-name fields, or do application-side joins, or use JPQL projections that bypass entity caching.

**Pattern to encode.** For every legacy view (`VIEW_X` joining `X` with lookup tables), generate a sibling `@Entity @Immutable @Table(name = "VIEW_X")` class and route reads through a `JpaRepository<View, Long>`. The mutable entity stays focused on the row; the view entity stays focused on display.


## LRN-2026-05-13-c: JWT authentication enrichment via external role lookup

```meta
date: 2026-05-13
project: _seed
stack: [spring-boot, oauth2, security]
req: []
auditor_run: seed@spring-boot
severity: warning
seed: true
```

**What happened.** When OAuth2 JWT claims do not carry application-specific roles, the conversion implements `Converter<Jwt, AbstractAuthenticationToken>`: it merges `JwtGrantedAuthoritiesConverter`'s default authorities with an external lookup (RestClient call to a role service using the JWT as the auth header), filters returned roles through an allowlist constant, and adds them as `SimpleGrantedAuthority`. External-call failure logs at WARN and returns the default authorities; it does not block login.

**Why it matters.** Identity-provider role claims are usually generic and slow to change. Application-specific roles live in a domain service. Embedding the lookup in the JWT-to-Authentication conversion keeps `@PreAuthorize` and method security working naturally without each service repeating the role-fetch boilerplate.

**Pattern to encode.** For Spring Security OAuth2 resource servers needing app-specific roles, implement `Converter<Jwt, AbstractAuthenticationToken>` and wire it via `oauth2ResourceServer.jwt(j -> j.jwtAuthenticationConverter(converter))`. Always filter external roles through a known allowlist; never trust the external response shape verbatim. External-call failure must downgrade gracefully (WARN log + default authorities), not fail the whole authentication.


## LRN-2026-05-13-d: Pokemon catch wrapping every service method is a blocker

```meta
date: 2026-05-13
project: _seed
stack: [spring-boot, java]
req: []
auditor_run: seed@spring-boot
severity: blocker
seed: true
```

**What happened.** Service methods wrapped every body in `try { ... } catch (DomainException e) { throw e; } catch (Exception e) { throw new ServiceException(INTERNAL_SERVER_ERROR, "Failed to X: " + e.getMessage()); }`. Bad client input (e.g. `NumberFormatException` on a parsed query parameter) became a 500. The original stack trace and `cause` were gone. Nothing in the catch logged.

**Why it matters.** Every observed failure surfaces as the same generic 500 with a wrapped message. Debugging requires re-running with debug logging to recover the type and cause. Worse, legitimate 4xx scenarios (bad input) are reported as 5xx, breaking client retry behavior and SLOs. Related to LRN-2024-01-02-c but distinct: that entry covers swallow-and-return-null; this entry covers wrap-and-remap-to-5xx.

**Pattern to encode.** Auditor BLOCKS on any service-layer `catch (Exception e)` that re-throws without preserving `cause`, OR that catches a checked domain exception just to re-throw it unchanged. Acceptable shapes: (1) no try/catch, propagate naturally; (2) `catch (SpecificRuntimeException e)` translating to a specific domain exception with `cause` preserved; (3) outer `@ExceptionHandler` catches the generic case once for the whole controller.


## LRN-2026-05-13-e: Speculative duplication of Post/Put request models

```meta
date: 2026-05-13
project: _seed
stack: [spring-boot, java]
req: []
auditor_run: seed@spring-boot
severity: warning
seed: true
```

**What happened.** A domain defined `XPostRequestModel` and `XPutRequestModel` as byte-identical 56-field classes with a javadoc claim of "kept separate so POST and PUT shapes can evolve independently without coupling." No evolution existed. The duplication forced two byte-identical `applyRequestToEntity()` overloads, two Swagger schemas, two unit-test fixtures.

**Why it matters.** Speculative future-proofing pays only on a hypothetical that may never arrive. When the request shapes actually diverge, splitting at that moment is cheap because the divergence is concrete. Splitting up-front guarantees the duplication is permanent and compounds (mappers, schemas, tests all double).

**Pattern to encode.** One request model per logical operation shape, regardless of HTTP method. Auditor: any two request-model classes in the same package whose declared field signatures are identical must be collapsed to a single class. Split only when a real field-level divergence exists.


## LRN-2026-05-13-f: Empty-shell service-specific exception subclasses multiply boilerplate

```meta
date: 2026-05-13
project: _seed
stack: [spring-boot, java]
req: []
auditor_run: seed@spring-boot
severity: warning
seed: true
```

**What happened.** A service-specific exception (`CaseService4xxException`) extended a base (`ClientProjectBBaseException`) with no added fields, methods, or behavior. The `RestControllerAdvice` then registered four `@ExceptionHandler` methods (one per service x 4xx/5xx) with byte-identical bodies. Adding a second service required two more empty-shell exceptions and two more handlers.

**Why it matters.** Exception class identity should encode behavioral difference (response shape, log level, recovery path). Subclassing for namespace clarity alone forces N times the handler boilerplate without N times the behavior. The service-specific identity belongs in the exception's `message` field, not its type.

**Pattern to encode.** One base 4xx and one base 5xx per domain, both carrying `httpStatus` as a field. `RestControllerAdvice` has exactly two handlers (one per base class) that read `httpStatus`. Auditor: any `@ExceptionHandler` method whose body is byte-identical to another in the same advice is a finding; the exception types should be merged.


## LRN-2026-05-13-g: API responses should not contain UI display strings

```meta
date: 2026-05-13
project: _seed
stack: [spring-boot]
req: []
auditor_run: seed@spring-boot
severity: warning
seed: true
```

**What happened.** A controller returned `List<String>` containing hard-coded human labels: `"Case Response Form"`, `"Supporting Documents"`, `"Email"`, `"Additional Information"`, `"Reviewed"`. The frontend received the labels directly and rendered them verbatim.

**Why it matters.** Backend changes become coordinated frontend code drops. Label edits force API version bumps. i18n becomes a server concern. The contract conflates display copy with operational state, and the API is no longer translatable without server changes.

**Pattern to encode.** Return enum identifiers or stable tab IDs from controllers (`["RESPONSE_FORM", "DOCS", "EMAIL"]`). The client maps IDs to labels and handles translation. Auditor: flag any controller response with a string field containing a space character where the field is not explicitly free-text (descriptions, comments, requester addresses, etc.).


## LRN-2026-05-13-h: Hand-rolled entity-to-DTO mappers are a duplication tax

```meta
date: 2026-05-13
project: _seed
stack: [spring-boot, java]
req: []
auditor_run: seed@spring-boot
severity: warning
seed: true
```

**What happened.** A service had three `mapToXResponseModel(entity)` methods, each 50+ lines of hand-typed builder calls (`.field(entity.getField())`). ModelMapper was declared in the pom but never imported. Field rename meant touching every mapper; adding a fourth response model meant another 50-line mapper.

**Why it matters.** Mapper code is linear in field count and quadratic in entity-DTO pairs. Hand-typed mappers tend to drift from the entity (forgotten field, copy-paste from wrong source) and are themselves tested separately, duplicating the production logic into tests.

**Pattern to encode.** When 3+ entity-to-DTO mappers exist with field-by-field assignment, replace with MapStruct (compile-time, type-safe; preferred for new code) or use the already-declared ModelMapper (reflection-based). Auditor: count `.setX(entity.getX())` or builder `.x(entity.getX())` chains per method and flag any exceeding 20 fields without a mapper library import.
