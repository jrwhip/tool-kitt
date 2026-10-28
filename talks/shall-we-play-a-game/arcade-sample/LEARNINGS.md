## LRN-2026-08-21-c: openapi-typescript peer-pins TypeScript 5, Angular 22 ships TypeScript 6

```meta
date: 2026-08-21
project: _seed
stack: [angular, openapi-generator]
req: []
auditor_run: seed@angular
severity: warning
seed: true
```

**What happened.** `npm install -D openapi-typescript` on a fresh Angular 22 project failed on peer dependency resolution: `openapi-typescript` declares a peer of `typescript@^5`, but Angular 22's scaffold installs TypeScript 6. The reflex fixes both make things worse: `--legacy-peer-deps` silently accepts a peer mismatch that may bite later, and downgrading the project's TypeScript to 5.x fights the framework's own pin.

**Why it matters.** The failure looks like a broken package rather than a lagging peer range, so the obvious fixes attack the wrong layer. Downgrading TypeScript project-wide to satisfy one dev-only codegen tool is a worse trade than isolating the tool.

**Pattern to encode.** Run `openapi-typescript` through a version-pinned `npx` invocation (e.g. `npx -y openapi-typescript@latest ...` in its own step) so its peer resolution stays local to that invocation, or add a `resolutions`/`overrides` entry scoped to that package only. Do not reach for `--legacy-peer-deps` or downgrade the project's TypeScript version.

## LRN-2026-08-21-c2: openapi-typescript still pins peer typescript ^5.x, so Angular 22 rejects it

```meta
date: 2026-08-21
project: arcade
stack: [angular, typescript, openapi]
req: []
auditor_run: scaffold@p4
severity: major
origin: human
```

**What happened.** `npm install -D openapi-typescript@7.13.0` failed with ERESOLVE against a fresh Angular 22 app. Angular 22 ships TypeScript 6.0; openapi-typescript's latest release and its `next` tag both declare `peerDependencies.typescript: "^5.x"`.

**Why it matters.** The reflex fixes both cost something. `--legacy-peer-deps` or an `overrides` block silences the check but leaves a false constraint in the lockfile that the next person has to re-litigate. Downgrading TypeScript to satisfy a codegen tool is backwards: the tool never type-checks the project, it only emits a `.d.ts`.

**Pattern to encode.** When a code-generation CLI conflicts on peers with the framework's TypeScript, do not install it. Run it through `npx <tool>@<pinned-version>` from an npm script so it resolves its own isolated tree, and pin the same version in `wopr.yml` under `openapi.pinned_generator_version` so the auditor still has a lockstep value to check. Reserve `--legacy-peer-deps` for libraries that actually ship runtime code into the bundle.

## LRN-2026-08-22-a: 100% coverage does not prove a signal-exposed WS message type is actually consumed by the UI

```meta
date: 2026-08-22
project: arcade-web
stack: [angular, vitest, websocket, signals]
req: [REQ-ARC-7]
auditor_run: frontend/AUDIT_REPORT.md@2026-08-22
severity: blocker
```

**What happened.** `GameSocketService` (the coder-spec's mandated single owning service for `/ws/game`) correctly exposed all seven server-to-client message types as readonly signals, including `moveError`. The tester wrote a passing unit test asserting `moveError()` updates when a `move_error` frame arrives. Coverage reported 100% line/branch/function on the service and on every component. But no component ever read `gameSocket.moveError()` -- the handoff contract's documented UI action ("transient rejection cue: shake the cell, toast the message; route non-recoverable codes to an error state") was never built. The auditor found this only by grepping for the signal's call sites outside test files, not from any tool output.

**Why it matters.** Coverage tools measure whether producer-side code executed, not whether a consumer exists downstream. A well-tested, fully-covered signal or observable can be entirely dead from the user's perspective while every quality gate reports green. This is structurally invisible to line/branch coverage because there is no untaken branch -- the producer code runs fine every time.

**Pattern to encode.** When a spec mandates a service expose "every message type as a signal" (fan-out architecture), the audit checklist must separately verify each exposed signal has at least one non-test call site, not just that the producer path is covered. Grep for `<signalName>(` outside `*.spec.ts` as a cheap first pass before trusting coverage numbers on message-routing services.

## LRN-2026-08-22-h: A test-constraint-justified DI escape hatch needs a revert trigger, or it becomes permanent silent-failure debt

```meta
date: 2026-08-22
project: arcade-web
stack: [angular, dependency-injection]
req: [REQ-ARC-7]
auditor_run: frontend/AUDIT_REPORT.md@2026-08-22
severity: warning
```

**What happened.** A coder-spec pattern permitted `inject(Router, { optional: true })` in production code, justified entirely by a pre-existing spec file's `TestBed` not providing `Router`: "the optional form only matters for the untouched spec... flag the spec gap to the tester." The tester then fixed the harness to provide `Router` unconditionally for every test, old and new. Nothing then reverted the production code to an unconditional `inject(Router)`. The optional-injection pattern now sits, unnecessarily, on a security-relevant auth-redirect effect: if the "production always has a router" assumption is ever violated, the failure mode is a silent no-op rather than a loud `NullInjectorError`.

**Why it matters.** Escape-hatch patterns adopted to work around a specific, named test constraint are only ever justified while that constraint holds. Nothing in the pattern's own definition created a trigger to check whether the constraint had since been resolved, so the workaround outlived its reason and became permanent, unexamined defensive code on a path where silent failure is the worst possible outcome.

**Pattern to encode.** When a spec sanctions a DI/test workaround "until the tester adds proper coverage," the handoff that closes the gap should also flag the production code for revert-consideration, not just record the new test coverage. The auditor should re-check the stated justification's continued validity every time, not just confirm the pattern was followed.

## LRN-2026-08-22-i: Exhaustive per-value test coverage belongs at the layer that branches on the value, not the layer that merely passes it through

```meta
date: 2026-08-22
project: arcade-web
stack: [angular, vitest, websocket]
req: [REQ-ARC-7]
auditor_run: frontend/AUDIT_REPORT.md@2026-08-22
severity: suggestion
```

**What happened.** A prior audit suggested a service-layer WS-message spec should parameterize over all 7 members of a discriminated-union code field, since it only tested 2 directly. A later fix exhaustively covered all 7 at the consumer layer (the component that maps each code to distinct UI text) instead. Re-examining the service's actual routing code showed it performs zero per-code branching -- it stores the whole message object regardless of which of the 7 values arrived. Parameterizing the service spec over all 7 values would have tested nothing the 2-value spec did not already prove; the router doesn't care which value it is.

**Why it matters.** "Only N of M enum values are tested at this layer" is not automatically a gap. Whether it is a gap depends on whether that layer's code varies its behavior by value. Flagging it reflexively, without checking for branching, sends fix effort to the wrong file and can produce redundant tests that inflate a suite without adding assurance.

**Pattern to encode.** Before treating partial per-value coverage as a finding, check whether the flagged code path branches on the value at all. If it's a pure pass-through, the exhaustive check belongs at the nearest layer that actually discriminates.

## LRN-2026-08-22-j: permission-classifier cloud/process cleanup blocks are inconsistent per-invocation, not a hard per-role wall

```meta
date: 2026-08-22
project: arcade-web
stack: [amplify-gen2, aws-cdk, dynamodb, postgres, bash-tooling]
req: [REQ-ARC-9]
auditor_run: frontend/AUDIT_REPORT.md@2026-08-22
severity: warning
origin: crew-auditor
```

**What happened:** During REQ-ARC-9, the coder's `TRUNCATE TABLE` (local Postgres residue) and the tester's `aws dynamodb delete-item` (live AWS residue) were both blocked by the environment's permission classifier, each escalating cleanup to a later role. Auditing the same REQ, the *identical-shaped* `TRUNCATE TABLE` and a *different* `aws dynamodb delete-item` call both succeeded directly for the auditor, while an unrelated `pkill` against the auditor's own throwaway local verification process was blocked instead.

**Why it matters:** Three separate crew roles lost time on the same REQ's residue cleanup assuming a hard, role-scoped prohibition. The evidence instead points to a narrower, non-obvious trigger tied to command shape or invocation context, not intent or role.

**Pattern to encode:** Do not treat one classifier block as proof the action is categorically forbidden for your role. Retry the specific cleanup command once before escalating; if it still blocks, name the exact command in the handoff (as prior roles correctly did) rather than assuming a workaround is needed. Whoever owns the classifier rule should treat this as cross-role evidence the block is invocation-scoped, not role-scoped.

## LRN-2026-08-22-k: Lambda Function URLs need explicit Content-Type on manual curl verification

```meta
date: 2026-08-22
project: arcade-web
stack: [amplify-gen2, lambda-function-url, aws-sdk, curl]
req: [REQ-ARC-9]
auditor_run: frontend/AUDIT_REPORT.md@2026-08-22
severity: suggestion
origin: crew-auditor
```

**What happened:** `guest-join`'s handler correctly returns `400 invalid_body` when `JSON.parse(event.body)` throws. A bare `curl -X POST <function-url> -d '{"callsign":"abc"}'` (no explicit `Content-Type` header) also lands on that same `invalid_body` branch — not because the JSON is malformed, but because of how the Lambda Function URL's `APIGatewayProxyEventV2` shape handles an unset content-type on the request. The tester discovered this the hard way while re-running the coder's documented curl checks by hand; the auditor independently reproduced it while re-verifying AC#4 live.

**Why it matters:** Vitest's mocked `APIGatewayProxyEventV2` fixtures don't reproduce this at all (the tests construct the event object directly, bypassing real HTTP content negotiation), so unit coverage gives no signal here. Anyone hand-verifying a Function URL endpoint with a plain `curl -d` will see a misleading `invalid_body` and may chase the wrong bug.

**Pattern to encode:** Always pass `-H "Content-Type: application/json"` explicitly on any manual `curl` check against a Lambda Function URL that parses a JSON body — treat it as load-bearing, not optional, for every future ARC-10+ platform endpoint added under `amplify/functions/`.

## LRN-2026-08-22-l: A failed shared-document edit tool is a report, not a license to regenerate

```meta
date: 2026-08-22
project: arcade-web
stack: [process, multi-agent-crew]
req: [REQ-ARC-10]
auditor_run: frontend/AUDIT_REPORT.md@2026-08-22
severity: warning
origin: crew-auditor
```

**What happened.** REQ-ARC-10's scout, working against `implementation-tracking.md` (a 429-line shared tracking document owned collectively by every crew role across every REQ), hit a targeted-edit tool failure and responded by regenerating the entire file from scratch rather than retrying or narrowing the edit. The orchestrator caught this before it landed and restored the file from git. No data was permanently lost, but the near-miss was serious: a wholesale rewrite of a shared, append-heavy document by a single role risks silently dropping other roles' prior entries, Structural Context rulings, and implementation-log history that a targeted edit would have left untouched.

**Why it matters.** Shared tracking documents in a multi-agent crew accumulate authority incrementally -- each role's entries are evidence future roles and the auditor depend on. A tool failure on a targeted edit (a diff not applying, an anchor text not matching) is information about the edit request, not permission to escalate to a destructive full-file rewrite. The two failure modes have wildly different blast radii: a mis-targeted edit fails loudly and leaves the file untouched; a wholesale regeneration can succeed mechanically while silently dropping content the generating role had no way to know it needed to preserve.

**Pattern to encode.** When a targeted edit to a shared, multi-role-owned document fails, retry with a narrower anchor or escalate the failure in the handoff rather than regenerating the file. Reserve full-file rewrites for files a single role exclusively owns end-to-end (e.g. a fresh spec section format change explicitly requested). Any role about to write a full replacement of a file with pre-existing multi-role content should treat that as a stop-and-check moment, not a routine recovery step.

## LRN-2026-08-23-a: A reconcile-by-poll mechanism only heals a race if the action it polls can act, not just observe

```meta
date: 2026-08-23
project: arcade-web
stack: [aws, dynamodb, distributed-systems, reconcile-by-poll]
req: [REQ-ARC-11]
auditor_run: frontend/AUDIT_REPORT.md@2026-08-23
severity: warning
origin: crew-auditor
```

**What happened.** REQ-ARC-11's queue-pairing fix (a two-party eventually-consistent-read race) was declared closed after its first cycle with a claim that a residual triple-race case was "left to the existing reconcile-by-read pairing watchdog (`status`'s own poll) to self-heal." That claim was never live-verified and was wrong: `status`'s pre-existing check only discovered a game the caller was ALREADY a party to -- it never attempted a claim for a caller still genuinely unpaired. The frontend's own periodic `status` poll was therefore polling a dead end; a caller stuck in the residual window had no path back to pairing short of the full queue-TTL expiry, not "one watchdog interval" as claimed. Live verification (20 iterations) caught 1 stuck outcome before a second fix cycle made `status` itself run the actual discovery-plus-claim logic.

**Why it matters.** "There's already a reconcile-by-read watchdog for this" is a comforting but unverified claim in any system with more than one poll-shaped mechanism. A watchdog that only re-reads state the caller already has access to (rather than attempting the specific corrective write the residual case needs) provides zero coverage for exactly the case it's invoked to justify, while looking, on paper, like defense in depth.

**Pattern to encode.** When a fix's safety argument rests on "an existing poll/watchdog will catch the residual case," verify that poll's own action actually performs the SAME corrective operation the residual case needs -- read the poll handler's code, don't infer coverage from its existence or its polling cadence. If the poll is read-only relative to the residual case, it is not a healer for that case, no matter how frequently it runs.

## LRN-2026-08-23-a2: A content-addressed deploy asset without exclusions can force a disruptive infra replacement from zero production-code drift

```meta
date: 2026-08-23
project: arcade-web
stack: [aws-cdk, lambda-layers, python, typescript]
req: [REQ-ARC-12]
auditor_run: frontend/AUDIT_REPORT.md@2026-08-23
severity: HIGH
origin: crew-auditor
```

What happened: `amplify/functions/shared_python/layer-resource.ts` built a Lambda Layer via `Code.fromAsset(join(__dirname, 'layer'))` with no `exclude`, so it hashed and zipped every byte under that directory -- including co-located `test_*.py` files (this project's established test-colocation convention) and transient `__pycache__`/`.pytest_cache`/`.coverage` residue a routine local `pytest --cov` run leaves behind. A test file added or a stray coverage artifact left on disk after the layer's last deploy changed the computed asset hash on the next deploy relative to what was live, forcing a Layer *replacement* (Layer versions are immutable) even though zero production code (`elo.py`/`joshua.py`/`joshua_lines.json`) had changed. On a CloudFormation stack running Express-mode-with-disable-rollback, a replacement-type update is rejected outright and the stack gets stuck in `UPDATE_FAILED` with no self-heal on retry -- requiring an operator-consented full stack recreate.

Why it matters: the failure mode looks exactly like "the production content changed and something about that change is unsupported," which sends debugging effort toward the wrong file entirely. The real cause is invisible in `git status` (test residue, gitignored) and invisible in the diff (no production file touched). This can recur on any content-addressed deploy artifact (a Layer, a container image build context, a static-asset bundle) that globs a source directory without excluding its own test/build byproducts.

Pattern to encode: before trusting a "just my production edit" mental model for why a content-addressed deploy artifact is being replaced, inspect what the packaging step actually swept up (`unzip -l` / equivalent) and diff it against the intended file set. Any packaging step for a directory that also holds co-located tests, caches, or build byproducts needs an explicit exclude list from day one, not after the first deadlock.
```

## LRN-2026-08-23-b: A dev server already listening on the expected e2e port produces a false "config is fine, app is broken" signal

```meta
date: 2026-08-23
project: arcade-web
stack: [playwright, e2e, dev-environment]
req: [REQ-ARC-12]
auditor_run: frontend/AUDIT_REPORT.md@2026-08-23
severity: MEDIUM
origin: crew-auditor
```

What happened: an e2e run against the deployed stack (`ARCADE_E2E_BASE_URL` deliberately unset for a local-mode check) intermittently behaved as though it were hitting a completely different, unrelated application -- because a DIFFERENT project's own `ng serve`/dev server happened to already be bound to the same default port (`:4200`) this project's local Playwright `webServer` mode also expects. Playwright's own port-reuse/`webServer` startup logic did not detect the mismatch; the run proceeded against the wrong app's markup, producing failures that read like application regressions rather than an environment collision.

Why it matters: this class of false alarm burns real debugging time chasing a nonexistent regression in the application under test, because every symptom (selectors not found, unexpected navigation, blank assertions) looks identical to a genuine break. It is specific to *any* shared-machine dev workflow where multiple projects default to the same conventional port, not just this repo.

Pattern to encode: before diagnosing an e2e failure as an application bug -- especially one that behaves nonsensically (elements that should obviously exist are missing, or unrelated content appears) -- verify what is actually listening on the target port/URL (e.g. `curl`/`lsof -i` the port, or check the served page's own identifying markup) before trusting that the failure says anything about the code under test. This is cheap and should be a reflex, not a last resort, whenever multiple projects on one machine share default dev-server ports.
```

## LRN-2026-08-23-a3: Trace-and-classify every e2e "flake" against a named mechanism before disclosing it as environmental

```meta
date: 2026-08-23
project: arcade-web
stack: [aws-amplify-gen2, dynamodb, appsync-events, lambda, playwright, angular-22]
req: [REQ-ARC-12]
auditor_run: frontend/AUDIT_REPORT.md@2026-08-23 (closing re-audit)
severity: high
origin: crew-auditor
```

**What happened:** across REQ-ARC-12's fix chain, three genuinely different production bugs (a host-line reconciliation gap, a heartbeat background-tab-throttling gap, and a DynamoDB read-consistency race) all presented identically at the Playwright layer as "an intermittent, unexplained e2e failure against the deployed stack." Each was only correctly separated from the others, and from ordinary AWS tail latency, by tracing the SPECIFIC failing request/response bytes (CloudWatch invocation logs, DynamoDB item state, or a captured Playwright network trace's stored resource bodies) back to a named code path -- never by re-running until green or by DynamoDB aftermath alone. The closing audit itself found a FOURTH instance this same session: a recorded fix ("6 of 6 consecutive clean, 84/84, zero reproductions") for a false `out_of_turn` rejection did not hold under independent re-verification -- 3 fresh batches reproduced it twice, and only a byte-level Playwright trace (the stored request/response JSON inside each `trace.zip`) proved the SAME mechanism was still live, at a reduced but nonzero rate a small "N-of-N clean" batch cannot rule out.

**Why it matters:** a team that stops at "re-ran and it passed" or "DynamoDB looks fine now" will systematically under-count real defects as flakes, and will falsely close fixes that only reduced -- rather than eliminated -- a race's reproduction rate. This compounds: each falsely-closed finding removes a real symptom from the pool the NEXT investigator has to explain, making genuinely unrelated bugs look like a single mysterious flake.

**Pattern to encode:** never accept "flake" or "fixed, N consecutive clean" as a final answer without independently reproducing (fresh batches, not the original discoverer's own runs) AND root-causing at the evidence layer specific to the transport in play -- CloudWatch/DynamoDB for async server-side effects, a full-network-trace Playwright run (`--trace on` for every test, not just retries) for anything where a response BODY (not just its arrival) matters, since a `200` with `ok:false` is invisible to aftermath-only evidence like a stalled DB row. A small number of post-fix clean batches is not statistically powered to distinguish "closed" from "same bug, lower rate" when the pre-fix rate was itself probabilistic.

## LRN-2026-08-23-b2: A completion/watchdog "done" check must be a conjunction of every signal a client still expects, not just the first one

```meta
date: 2026-08-23
project: arcade-web
stack: [angular-22, appsync-events, reconcile-by-read, watchdog-timers]
req: [REQ-ARC-12]
auditor_run: frontend/AUDIT_REPORT.md@2026-08-23 (closing re-audit)
severity: medium
origin: crew-auditor
```

**What happened:** a self-healing reconcile watchdog (armed on every state advance, cleared when "the game is over") cleared itself the instant the FIRST terminal signal arrived (`game_state.result` going non-null), even though a SECOND, independently-published signal for the exact same terminal moment (`host_line`'s win/draw/forfeit outro) was guaranteed by the system's own publish-ordering contract to arrive strictly AFTER the first. The watchdog's "done" check asked only "is the primary state terminal?" when the real question was "have ALL the signals I still expect for this terminal moment arrived?" -- and a push dropped in the gap between those two questions had nothing left watching for it, closing a live production gap that shipped a broken/fallback outcome to real users before an audit caught it via three full-suite batches.

**Why it matters:** this is a general shape, not specific to one payload type: any completion detector, watchdog, or "settled" check that gates on ONE signal when the domain actually promises several ordered signals for the same event will silently stop protecting the LATER signals the moment the FIRST one lands -- and because the failure only manifests on an at-most-once/lossy transport, it is invisible to any test that only ever exercises the happy path where every signal arrives.

**Pattern to encode:** when a "settled"/"done"/"complete" check gates cleanup or a watchdog's own re-arm decision, enumerate every distinct signal the domain's own ordering contract promises for that terminal moment, and make the check a CONJUNCTION of all of them, not just the most obvious/first-arriving one. Test each conjunct with a DIFFERENT trigger that isolates it (a dropped-then-repaired second signal, not just "eventually all signals arrived together") -- a test suite that only ever constructs the happy-path/single-branch shape of a terminal event (e.g. always a `win`, never a `forfeit` whose string representation collides with `win`'s) cannot discriminate a version of the conjunction that got the precedence or completeness wrong.

## LRN-2026-08-24-a: A harness that seeds a dependency's state directly instead of calling the real producer is blind until two coincidentally-equal identity sources diverge

```meta
date: 2026-08-24
project: arcade-web
stack: [angular, vitest, aws-amplify, identity-federation]
req: [REQ-ARC-13]
auditor_run: frontend/AUDIT_REPORT.md@2026-08-24
severity: high
origin: crew-auditor
```

**What happened:** `game-events-client.service.spec.ts`'s harness seeded `GuestCredentialsStore.set(identityId, ...)` directly instead of calling `service.connect(identityId)` (the real producer of the class's own `connectedIdentityId` field). This worked, undetected, for three prior REQs because the guest-only code path always set both sources to the identical value in the same call -- no test could have told them apart even in principle. The production code itself carried the matching bug: `submitMove`/`callGamePresence`/`reconcileGameState` read `GuestCredentialsStore.identityId()` instead of `connectedIdentityId`. Adding a second identity path (an account session, which never writes to `GuestCredentialsStore`) broke the coincidence and surfaced both the harness gap and the production bug simultaneously -- 19 tests either failed outright or kept passing for the wrong reason (a negative assertion trivially true when the guarded call never fires at all).

**Why it matters:** two independent data sources that happen to always agree in every code path exercised so far look, from a coverage report, identical to one genuinely-unified source. The 100%-passing suite provided zero evidence about which source production code actually read.

**Pattern to encode:** when a class threads an identity/config value through both a locally-owned field and a shared store it also happens to read elsewhere, seed tests via the real producer method, not by writing directly into the shared store -- and add at least one test where the two sources are seeded with DIFFERENTLY-valued data, asserting which one the real call carries. This is the only test shape a coincidentally-equal harness can never express.

## LRN-2026-08-24-b: A fire-and-forget catch-all swallows a newly-introduced credential-refresh failure mode identically to the old, already-accepted network failure it was designed for

```meta
date: 2026-08-24
project: arcade-web
stack: [aws-amplify, cognito, identity-federation, playwright]
req: [REQ-ARC-13]
auditor_run: frontend/AUDIT_REPORT.md@2026-08-24
severity: high
origin: crew-auditor
```

**What happened:** `GameEventsClientService.submitMove` wraps its signed `post()` call in a bare `try/catch` that silently swallows any failure, a design choice inherited unchanged from the WS-era `sendMove` ("surfaces as nothing happened, same as the old socket's silent drop-if-not-open behavior"). That catch was written when the only realistic failure was a dropped network call. REQ-ARC-13 changed what can throw inside that same call: `post()`'s SigV4 signing now depends on `cognitoCredentialsProvider`'s newly-added authenticated-role credential resolution/refresh, introduced specifically to satisfy AC#5 (session survival past the access-token lifetime). An auditor's fourth independent run of the exact AC#5 journey (two solo runs, two full batches) reproduced a real failure: the account player's first post-wait move never reached any `GameMoveFunction` CloudWatch log group at all (confirmed by log-group search on the exact `gameId`) -- the click resolved with no visible error, and the game eventually resolved by forfeit. Three of four runs passed clean, so the coder's and tester's own (smaller) verification samples never saw it.

**Why it matters:** a catch-all written to accept one class of failure (an offline/dropped network call, an acceptable UX trade at the time) silently expands its blast radius the moment a call it wraps starts depending on new failure-prone machinery -- here, credential refresh -- without anyone re-examining whether the original "fail silently" justification still holds for the NEW thing that can now throw inside the same block. The failure is real and material (it undermines the exact acceptance criterion the new dependency exists to satisfy) but is invisible to a small number of clean runs, since the underlying race is probabilistic.

**Pattern to encode:** when a change adds a new dependency (especially one with its own async refresh/retry lifecycle, like a credentials provider) inside an existing fire-and-forget catch-all, re-audit whether that catch's original "swallow and move on" justification still applies to every new thing that can now throw inside it -- and if the acceptance criterion the new dependency exists to prove is "survives X," budget more than 1-2 verification runs before trusting a clean pass, since credential-refresh races are exactly the class of failure a small sample under-detects.

## LRN-2026-08-24-c: A client-asserted identity is a claim, not a proof -- cryptographic verification is required the moment an action is account-scoped and irreversible

```meta
date: 2026-08-24
project: arcade-web
stack: [angular, amplify-gen2, dynamodb, cognito, lambda-function-url]
req: [REQ-ARC-14]
auditor_run: frontend/AUDIT_REPORT.md@2026-08-24
severity: HIGH
origin: crew-auditor
```

**What happened:** REQ-ARC-14's scout contract recommended trusting a body-passed `sub`, "verified" only by confirming the caller held some valid signed credential -- the SAME trust model this codebase's other platform functions already use for their client-asserted `identityId`. An operator ruling overrode this as forgeable: any signed caller (even a guest's own valid credentials) could assert another account's `sub` in the body and permanently steal a resource tied to it. The fix cryptographically verifies the caller's Cognito ID token against the pool's JWKS and acts only on the token's own verified claim. The auditor independently re-attacked the deployed endpoint: forged/tampered/missing tokens all rejected at 401; a forged `sub` riding alongside a real token was structurally unreachable (the handler never parses it); and a real token submitted while a *different* identity's credentials did the IAM signing still resolved to the token's own account, never the signer's -- proving the two trust layers (coarse IAM signing, fine-grained token verification) are genuinely independent and composable, not redundant.

**Why it matters:** most authenticated actions in a system are fine with "some valid signed caller" as the whole trust model -- a guest's own pairing, moves, and presence are self-contained to that one session and cost nothing if merely coarse-grained. The trust model silently stops being sufficient the instant an action's correctness depends on WHICH specific account is calling AND its effect is durable/hard-to-reverse (here: permanent, exclusive ownership). Reusing the codebase's existing, working trust pattern by default is the natural move and was exactly the wrong one here.

**Pattern to encode:** before trusting any client-asserted identity field (a body `sub`, a JWT claim read without signature verification, a session id used as if it were proof), ask: does this action's correctness depend on WHICH identity is calling (not just "some" valid one), and is the effect account-scoped and durable/irreversible? If yes to both, the identity must be cryptographically verified server-side against its own issuer (JWKS/JWT verification, not "the caller holds a valid credential for some other coarser-grained gate"), and the verified claim -- never a request-body field of the same name -- is the only thing the handler may act on.

## LRN-2026-08-24-d: Re-own a pinned regression test to encode a not-yet-implemented target design, not just prose

```meta
date: 2026-08-24
project: arcade-web
stack: [angular, testing, process]
req: [REQ-ARC-15]
auditor_run: frontend/AUDIT_REPORT.md@2026-08-24
severity: MEDIUM
origin: crew-auditor
```

What happened: a REQ-ARC-15 crew-run ruling required a watchdog's "settled" conjunction to gain a third leg (chat confirmation), but the literal implementation broke several pre-existing, boundary-protected regression tests pinning the OLD two-leg behavior. Rather than leaving the gap as a disclosed prose scope-note for the next coder pass to rediscover and re-derive, the tester rewrote those exact pins to the NEW target shape -- deliberately making them fail against current, unmodified production code. A later completion pass then built directly against the already-written, unambiguous acceptance tests.

Why it matters: a scope note in a tracking document is advisory and re-interpretable; a failing pin is a mechanical, unambiguous contract the next implementer cannot silently under-deliver against or misread. It also makes the gap's existence impossible to quietly lose track of -- the suite itself reports incomplete work as failing, not green-with-an-asterisk.

Pattern to encode: when a design ruling conflicts with an existing pinned test, and the constrained role cannot edit tests, escalate to the role that CAN (tester/spec-owner) to rewrite the pin to the target shape -- never leave the conflict as unenforced prose, and never silently work around the pinned behavior to avoid touching it. Verify by construction which sibling pins are unaffected before touching them, to avoid scope creep.

## LRN-2026-08-24-e: Two vendored copies plus a lockstep pin on both real loaders is a legitimate "canonical source" when a packaging boundary blocks true single-sourcing

```meta
date: 2026-08-24
project: arcade-web
stack: [polyglot-monorepo, serverless, testing]
req: [REQ-ARC-15]
auditor_run: frontend/AUDIT_REPORT.md@2026-08-24
severity: LOW
origin: crew-auditor
```

What happened: a blocklist needed to be shared between a Python Lambda (zipped verbatim, no bundler reach into a sibling directory) and a TypeScript Lambda (esbuild-bundled, can reach a shared directory). True single-sourcing was structurally impossible. The fix vendored two physical JSON copies plus a "lockstep" test pair: each side's spec imports ITS OWN real loader (a genuine module load) and diffs the output against the OTHER language's raw JSON file -- together proving both real loaders, not just the two source files, agree.

Why it matters: "one canonical source" is sometimes used loosely to describe a design intent (one place a human edits) rather than a literal single file, and an auditor or future engineer taking the phrase at face value could wrongly flag two vendored copies as a drift risk, or conversely trust a "canonical" label without checking whether the drift-detection pin actually exercises both real code paths versus just diffing the two files against each other (which would only catch JSON drift, never a loader-logic bug in either language).

Pattern to encode: when a packaging/bundler boundary makes true single-sourcing impossible across runtimes, judge the substitute by two criteria, not the "canonical" label: (1) does the pin invoke each side's REAL loader (not just re-derive from the raw file), and (2) does the pin run in a suite that actually executes before every deploy/merge in that project's own process, even absent CI. Both present is an acceptable, honestly-documented substitute.

## LRN-2026-08-24-f: An LLM invoker must check the completion's stop/finish reason, not just whether text came back, before trusting it for a safety-critical fallback design

```meta
date: 2026-08-24
project: arcade-web
stack: [python, bedrock, llm-integration]
req: [REQ-ARC-16]
auditor_run: frontend/AUDIT_REPORT.md@2026-08-24
severity: blocker
origin: crew-auditor
```

**What happened:** REQ-ARC-16's direct-reply path (`chat_host.py::_invoke_chat_bedrock_sync`) calls Bedrock's Converse API and unconditionally returns `response["output"]["message"]["content"][0]["text"]`. The caller's fallback-on-failure design (`if generated: line = ...; else: line = select_direct_reply_fallback()`) only routes to the canned pool on an exception, a timeout, or an empty string. Live adversarial testing (an instruction-override probe) reproduced 2/2: Nova's own content-moderation intercepted the request, the Converse call still returned HTTP success with non-empty text, and that text -- raw refusal/moderation boilerplate, not an in-character line -- was published to real players indistinguishable from a genuine generated reply. No exception, no timeout, no empty string: the one signal the fallback design actually checked for never fired.

**Why it matters:** Any LLM-integration pattern that "falls back to a safe default on failure" is only as good as its failure detection. A non-empty string is not proof of a successful, on-topic, in-persona completion -- content filtering, guardrail intervention, and refusal are all "successful API calls" from the SDK's point of view. This is invisible to unit tests that mock the invoker as success-or-None, and invisible to live testing that doesn't specifically probe content likely to trip the model's own safety layer.

**Pattern to encode:** When wrapping any LLM completion API for a system with a safe-fallback design, inspect the response's own stop/finish-reason field (Bedrock Converse: `stopReason`; OpenAI: `finish_reason`; etc.) and treat any non-normal value as a failure routed through the SAME fallback path a timeout or exception already uses -- never rely on "did text come back" alone as the success signal.

## LRN-2026-08-24-g: A git-hash-stamped deploy-freshness check is structurally unsound against a "commit the work after it's deployed" operational convention -- verify content, not the stamp, or redesign the check to tolerate the convention

```meta
date: 2026-08-24
project: arcade-web
stack: [ci-cd, deploy-verification, angular, amplify]
req: [REQ-ARC-15, REQ-ARC-16]
auditor_run: frontend/AUDIT_REPORT.md@2026-08-24
severity: warning
origin: crew-auditor
```

**What happened:** This project's own operating convention is "commit the crew's work at the gate, audit after" -- meaning a Hosting deploy routinely happens against an uncommitted working tree, and the deploy script's own `data-build-id` stamp substitution captures whatever `git rev-parse --short HEAD` was AT THAT MOMENT (the previous REQ's commit), not the commit that will eventually contain the deployed content. REQ-ARC-15's audit first flagged this as a manual-observation WARNING, content-hash-verified as non-functional. One REQ later, REQ-ARC-16 hit the identical gap, but this time an automated e2e test (`00-deploy-freshness.spec.ts`) added specifically to catch stale bundles now hard-fails on it deterministically, every run, reproduced 2/2 in two independent fresh batches -- a mechanical guard defeating itself against the exact convention it coexists with.

**Why it matters:** A freshness check built on a baked-in stamp assumes deploy-then-commit are atomic or ordered commit-then-deploy. Any project where "commit at gate, deploy during work" is a deliberate risk-mitigation convention (not a mistake) will produce this exact false-positive class on every cycle, and a check that hard-fails on it either gets silently ignored (eroding its own value) or blocks merges on a non-issue.

**Pattern to encode:** When a freshness/staleness guard is built on a stamp that only updates at deploy time, and the project's own workflow allows commits after the deploy with no further code changes, either (a) re-run the stamp substitution as an explicit step of the "commit at gate" convention itself, or (b) have the automated check fall back to a stronger content-hash comparison (of a content-addressed build artifact, e.g. a hashed bundle filename) before concluding staleness, rather than trusting the stamp alone.

## LRN-2026-08-24-h: A Playwright "drain a live-transitioning element" helper's check-then-act is not atomic against the state it's checking

```meta
date: 2026-08-24
project: arcade-web
stack: [playwright, e2e, dynamodb, shared-queue]
req: [REQ-ARC-16]
auditor_run: frontend/AUDIT_REPORT.md@2026-08-24
severity: medium
origin: crew-tester
```

**What happened.** Four call sites across three e2e spec files (`callsign-claim.spec.ts`, `chat.spec.ts`, two in `auth-account-flow.spec.ts`) independently reimplemented the same idiom to opportunistically dismiss an in-progress queue search before doing something else: `if (await cancelSearch.isVisible().catch(() => false)) { await cancelSearch.click(); }`. The auditor reproduced a 30s test-timeout failure 2/2 on one of these sites with a Playwright call log showing "element is not stable... element was detached from the DOM, retrying" -- the shared, no-per-test-isolation queue this suite polls (an established, disclosed rule) genuinely CAN resolve the search (a real pairing) in the gap between the visibility check and the click, detaching the button mid-click and defeating Playwright's own click-retry loop for the remainder of the calling TEST's own timeout budget, not a short one. A later tester pass could not reproduce it across 7 fresh attempts (1 full batch + 6 solo `--grep`-targeted runs, some traced) -- consistent with a genuinely low-rate race, not a deterministic bug, and the auditor's own preserved error-context (not re-run cleanliness) was what actually proved the mechanism.

**Why it matters.** A "just dismiss it if it's there" helper built on `isVisible()` then a separate `click()` is only safe if nothing else can change the element's state in between -- in a suite whose own design premise is a SHARED, unisolated queue table other concurrent test activity (or this identity's own real pairing) can mutate at any time, that assumption is false by construction, not by mistake. The failure is intermittent and low-rate enough that a small number of clean re-runs (by design or by luck) looks like confirmation it doesn't exist, exactly the trap `LRN-2026-08-23-a` warns about.

**Pattern to encode.** For any Playwright helper whose whole point is "opportunistically act on an element only if a live, externally-mutable state condition currently holds" (not a real assertion about that state), bound the action's own timeout well below the test's overall timeout and swallow its own failure (`.click({ timeout: 5_000 }).catch(() => undefined)`) -- a detached/navigated-away target means the condition already resolved on its own, which is success for an opportunistic helper, not a failure to retry indefinitely. Reserve the un-bounded, un-swallowed form for call sites that are a genuine assertion about the app's behavior (e.g. `lobby.spec.ts`'s own `expect(cancelSearch).toBeVisible()` + `.click()` pins proving the cancel-search feature itself works) -- do not apply this pattern there, since swallowing a real assertion's failure would hide a genuine regression.

## LRN-2026-08-24-i: Cognito's built-in `COGNITO_DEFAULT` email service has a low, non-obvious daily send quota separate from the account's own SES quota

```meta
date: 2026-08-24
project: arcade-web
stack: [aws-cognito, aws-ses, e2e, playwright]
req: [REQ-ARC-16]
auditor_run: frontend/AUDIT_REPORT.md@2026-08-24
severity: warning
origin: crew-tester
```

**What happened.** After a full day of crew work across REQ-ARC-13/14/15/16 (each involving multiple `/auth/register` e2e journeys, several full-batch re-runs, and this pass's own repeated flake-chasing re-runs), fresh `/auth/register` submissions began failing with the app's own generic "COULD NOT REACH THE SERVER. TRY AGAIN." -- reproducing 3/3, including on the FIRST registration of an otherwise-fresh full-batch run (ruling out same-run self-throttling). `aws cognito-idp describe-user-pool --query 'UserPool.EmailConfiguration'` showed `EmailSendingAccount: COGNITO_DEFAULT` -- Cognito's own built-in email service, which caps at roughly 50 sends per rolling 24h REGARDLESS of the AWS account's own SES sending quota (`aws ses get-send-quota` showed 50000/day, 0 sent -- SES was never in the loop at all, since Cognito's default service doesn't route through it).

**Why it matters.** This surfaces identically to a real backend/network outage from the UI's own generic error copy, and nothing in the account's own SES console or CLI output hints at the actual cause (SES reports itself as healthy and nearly unused) -- a dev/tester chasing this by checking SES-side metrics will find nothing wrong and may misdiagnose a code regression in the register flow itself. The quota is cumulative across EVERY registration any crew role runs in a 24h window, not scoped per-test-file or per-role, so it can silently exhaust from unrelated work earlier the same day.

**Pattern to encode.** Before diagnosing a `/auth/register` (or any Cognito-`signUp`-driven) e2e failure as an application bug, check the User Pool's own `EmailConfiguration.EmailSendingAccount` -- if it is `COGNITO_DEFAULT`, treat a sudden, otherwise-unexplained wave of register failures as a likely daily-quota exhaustion first, especially late in a day with heavy cumulative registration-flow test volume. The durable fix (switching to a verified SES identity, removing the ~50/day ceiling) is a production/infra change, not a test fix -- record it as a standing follow-up rather than chasing it as a code regression each time it recurs.

## LRN-2026-08-24-j: A DynamoDB `ConditionExpression` comparing ISO-8601 timestamp strings from two different language runtimes is not format-agnostic -- lexicographic comparison, not parsed-datetime comparison

```meta
date: 2026-08-24
project: arcade-web
stack: [dynamodb, python, typescript, eventbridge-scheduler, cross-language]
req: [REQ-ARC-17]
auditor_run: frontend/AUDIT_REPORT.md@2026-08-24
severity: MEDIUM
origin: crew-auditor
```

**What happened.** `rematch-offer-expiry`'s fired-handler CAS re-check compares a Python-written `offerExpiresAt` (`datetime.now(UTC).isoformat()`, live-verified format: microsecond precision, `+00:00` offset suffix) against a TypeScript-written `:now` (`new Date().toISOString()`, live-verified format: millisecond precision, `Z` suffix) via a plain DynamoDB `ConditionExpression: 'offerExpiresAt <= :now'`. DynamoDB compares String-type attributes byte-wise, not as parsed datetimes -- unlike application code that does `new Date(x).getTime()` (immune to this class entirely; confirmed the codebase's own `grace-sweep/handler.ts` does exactly that and is safe). Because `'+' (0x2B) < '.' (0x2E)` in ASCII, the two producers' differing suffix characters can make a lexicographic comparison disagree with the true chronological ordering when the compared prefixes are close, and a separate truncation-to-whole-seconds step elsewhere in the same request (scheduling the actual fire time) widens the window this can matter in. No test in either language's suite ever constructed the OTHER language's real timestamp format to compare against.

**Why it matters.** Two producers each individually "just using ISO-8601" is not sufficient when the comparison happens inside a datastore's own native conditional-write mechanism rather than in application code -- there is no `Date` parser standing between the two strings to normalize the format difference away. This class is invisible to any test that only ever constructs fixtures in ONE language's own native format.

**Pattern to encode.** Before trusting a cross-language DynamoDB `ConditionExpression`/`FilterExpression` comparison between two timestamp-shaped String attributes, verify (a) which of the two comparison sides is genuinely written by the OTHER runtime in production (not assumed via a same-format test fixture), and (b) whether the actual live formats byte-compare correctly for every case that matters, especially near a boundary. Prefer normalizing both producers to an identical format (fixed fractional-second digit count, identical UTC suffix) at the point of write, or parse-and-compare in application code instead of relying on the datastore's native string ordering.

## LRN-2026-08-21-a: Postgres 18 moved the data volume mount point

```meta
date: 2026-08-21
project: arcade
stack: [fastapi, postgres, docker]
req: []
auditor_run: scaffold@p4
severity: blocker
origin: human
```

**What happened.** `docker compose up -d db` on `postgres:18-alpine` with the long-standing `- pgdata:/var/lib/postgresql/data` mount exited 1 immediately. The log complained about data in "/var/lib/postgresql/data (unused mount/volume)".

**Why it matters.** Every Postgres compose file written before Postgres 18 uses the `/data` mount, so this fails silently-looking on a first `up` and the container is simply gone. The error text does not say "change your mount"; it talks about `pg_upgrade` and directory layouts, which reads like an upgrade warning rather than a fatal config error.

**Pattern to encode.** On Postgres 18 and newer, mount the volume at `/var/lib/postgresql`, not `/var/lib/postgresql/data`. The image places the cluster in a major-version subdirectory so `pg_upgrade --link` does not cross a mount boundary. Carrying the old path forward from a pre-18 compose file is the failure.

## LRN-2026-08-21-b: httpx 0.28 removed the AsyncClient(app=...) shortcut

```meta
date: 2026-08-21
project: arcade
stack: [fastapi, pytest, httpx]
req: []
auditor_run: scaffold@p4
severity: major
origin: human
```

**What happened.** The FastAPI testing idiom taught nearly everywhere, `httpx.AsyncClient(app=app, base_url=...)`, raises `TypeError` on httpx 0.28 and newer. The `app` keyword was removed, not deprecated.

**Why it matters.** It is the single most-copied FastAPI test snippet, so it appears in stack templates, older docs, and model output alike. The failure is at construction time, which is fine, but the fix is not guessable from the error: the caller has to know `ASGITransport` exists.

**Pattern to encode.** Build in-process test clients as `AsyncClient(transport=ASGITransport(app=app), base_url="http://test")`. Put that in a shared `client` fixture in `conftest.py` once so no test constructs its own. Treat any `AsyncClient(app=...)` in a diff as a stale-idiom flag.

## LRN-2026-08-22-a2: Verify claimed coverage-tracing artifacts with an A/B re-run, not by reading the explanation

```meta
date: 2026-08-22
project: arcade-api
stack: [fastapi, starlette, coverage.py, pytest, asgi]
req: [REQ-ARC-1]
auditor_run: backend/AUDIT_REPORT.md@2026-08-22
severity: warning
origin: crew-auditor
```

**What happened.** The tester spec claimed `coverage run`/`pytest --cov` under-traces a router coroutine's statements past certain `await` points when dispatched through `ASGITransport` (fastapi 0.141.1 / starlette 1.6.0 / coverage 7.15.4 / Python 3.12), and that a compensating direct-dispatch test class was added rather than accepting the undercount. Per the auditor mandate to treat such precedent skeptically, I re-ran the suite twice: once as committed (60 passed, `routers/auth.py` 100%), once with the compensating test class deselected (57 passed, same assertions still pass, `routers/auth.py` drops to 76%, missing exactly the lines the spec named). The artifact reproduced deterministically.

**Why it matters.** A claim like this is exactly the shape of a plausible-sounding excuse for weak coverage — "the tool is wrong, not the tests" — and an auditor who accepts it because it reads carefully-worded and cites specific line numbers has been talked out of verifying, not convinced by evidence. It also turned out to be true here, so blanket skepticism without a cheap verification step would have produced a false BLOCKER.

**Pattern to encode.** When a tester/coder spec cites a tool-behavior anomaly as justification for a testing pattern, don't just read the explanation — reproduce it with a two-run A/B (remove the compensating code, show the claimed symptom appears; restore it, show it clears) before accepting or rejecting the claim in the audit report.

## LRN-2026-08-22-b: `db.rollback()` on a non-exceptional branch still expires every tracked ORM object

```meta
date: 2026-08-22
project: arcade-api
stack: [fastapi, sqlalchemy, asyncio, postgres]
req: [REQ-ARC-2]
auditor_run: backend/AUDIT_REPORT.md@2026-08-22
severity: warning
origin: crew-auditor
```

**What happened.** `services.queue`'s `try_pair` and `enqueue` call `db.rollback()` as normal control flow, not inside an `except` block -- "fewer than two candidates to pair" and the `IntegrityError` backstop. `AsyncSession.rollback()` expires every ORM object the session is tracking regardless of `expire_on_commit`, so any post-rollback attribute access on an object built earlier in the same test (e.g. `player.player_id`) raises `sqlalchemy.exc.MissingGreenlet`, an error whose text gives no hint the rollback caused it. Verified directly: reproduced the failure, then confirmed the fix (capture the id into a local before the rollback-triggering call) clears it. Hit three times while writing this REQ's tests per the tracking log.

**Why it matters.** Any future service whose normal (non-error) control flow calls `db.rollback()` -- not just its exception handlers -- will hit this, and the failure mode is misleading enough to burn real debugging time each time it's independently rediscovered.

**Pattern to encode.** Capture any ORM attribute needed after a call that might rollback into a plain local variable *before* making that call, whenever a service's normal control flow (not just `except` blocks) can call `db.rollback()`.

## LRN-2026-08-22-c: Scout `files_touched` systematically omits small supporting-infrastructure edits

```meta
date: 2026-08-22
project: arcade-api
stack: [fastapi, wopr-scout-contract]
req: [REQ-ARC-1, REQ-ARC-2]
auditor_run: backend/AUDIT_REPORT.md@2026-08-22
severity: suggestion
origin: crew-auditor
```

**What happened.** Two REQs in a row, the coder touched files the scout's `files_touched` list didn't name. REQ-ARC-1: three test files (schema/config unit tests, flagged as a suggestion in that audit). REQ-ARC-2: `core/config.py` (two new `Settings` fields for queue TTL/interval) and `models/__init__.py` (two new model exports). Both audits independently found the same shape of drift: small, necessary, low-risk supporting edits that follow mechanically from a `class_inventory` entry the scout *did* declare, but weren't separately enumerated as a touched file.

**Why it matters.** The files_touched drift rule exists to catch genuine scope creep, but two-for-two false-positive-shaped drift on trivial wiring files (a settings field, a package `__init__` export) means an auditor re-derives the same "this is fine" judgment call from scratch each time instead of having a standing rule to lean on.

**Pattern to encode.** When auditing files_touched drift, distinguish (a) a small mechanical consequence of a `class_inventory` entry the scout already declared (a settings field backing a documented TTL, an `__init__` export for a documented model) from (b) genuinely unscoped new work. Only (b) warrants more than a suggestion-level note.

## LRN-2026-08-22-d: "Documented in the API description" needs a literal artifact check, not a substitute-document check

```meta
date: 2026-08-22
project: arcade-api
stack: [python, fastapi, openapi]
req: [REQ-ARC-3]
auditor_run: backend/AUDIT_REPORT.md@2026-08-22
severity: blocker
origin: crew-auditor
```

**What happened:** REQ-ARC-3's AC#9 required WebSocket message types to be "documented in the API description." The scout, coder, and tester all treated this as satisfied by `frontend-handoff-contract.md`'s WS table (thorough and accurate) and never touched `FastAPI(description=...)` or any route's `description` field to actually mention `move`/`game_state`/`move_error`. No test asserted on `info.description`'s content, so the gap reached the audit gate undetected.

**Why it matters:** A requirement that names a specific artifact ("the API description," "the OpenAPI document," "the migration file") is testable against that literal artifact, not against whichever document happens to carry the same information in spirit. Substitute documentation can be excellent and still fail the letter of the criterion — and when it does, no test written against the substitute will ever catch it, because the substitute is what the tests were written against too.

**Pattern to encode:** When an acceptance criterion names a specific document/field/endpoint, write (or ask the tester to write) at least one assertion against that literal thing, even when a better, more complete substitute already exists elsewhere. Auditors: when a criterion anchors to an artifact, fetch and inspect that literal artifact directly rather than accepting a cross-referenced substitute as proof.

## LRN-2026-08-22-e: A function parameter honored on only one code path is a latent divergence bug, even when today's caller makes it harmless

```meta
date: 2026-08-22
project: arcade-api
stack: [python, fastapi, websockets]
req: [REQ-ARC-3]
auditor_run: backend/AUDIT_REPORT.md@2026-08-22
severity: warning
origin: crew-auditor
```

**What happened:** `routers/ws.py::_handle_move(raw, player_id, manager, session_factory)` takes a `manager` parameter and uses it for the success path (`broadcast_game_state(result, manager)`), but its error path (`_send_move_error`) pushes through the imported module-level `connection_manager` singleton directly, ignoring the parameter entirely. The only production caller always passes that same singleton as `manager`, so the two never diverge today — but the asymmetry was discovered only while writing a direct-dispatch test, and is now something every future test on this function must know and route around.

**Why it matters:** A parameter a function accepts but only partially honors is a contract the signature promises and the body breaks. It costs nothing to notice today because there is exactly one caller and one instance in the process; it becomes a real bug the first time a second instance exists (a scoped test harness, a per-tenant registry, a future multi-worker registry) and nobody remembers which half of the function reads the parameter and which half reads the global.

**Pattern to encode:** When reviewing a handler that both accepts a dependency as a parameter and could reach the same dependency via a module-level singleton, check that every code path uses the same source consistently. Flag (WARNING, not BLOCKER, if no caller currently diverges) a function where only some branches honor an injected parameter — it is a design smell worth fixing before the next REQ extends the same handler, not after a real divergence surfaces as a production bug.

## LRN-2026-08-22-h2: 100%/100% coverage cannot catch a cross-call-site ordering defect

```meta
date: 2026-08-22
project: arcade-api
stack: python, fastapi, asyncio
req: REQ-ARC-6
auditor_run: backend/AUDIT_REPORT.md@2026-08-22 (blocker-fix re-audit)
severity: MEDIUM
origin: crew-auditor
```

What happened: REQ-ARC-6's `services/joshua.py` reported 100% line and 100% branch coverage, yet shipped a real defect: a fire-and-forget task's caller released the task's own keyed cleanup state synchronously, before the task had run, silently defeating a budget check and leaking a dict entry per completed game. Every line and branch involved individually executed under test (both the caller's release call and the task's own accounting ran, just never in the order production needed), so no coverage gap pointed at it. It was found only by an auditor manually tracing the caller/callee sequencing against the module's own documented invariant, independent of coverage output, and reproduced with a standalone script before being trusted as real.

Why it matters: a coverage percentage is a claim about which statements/branches executed, not about the order two independently-covered call sites executed in relative to each other. Treating 100%/100% as evidence of correctness for concurrency/ordering-sensitive code (anything touching `asyncio.create_task`, shared mutable state, or two racing writers) is a category error the gate itself cannot flag.

Pattern to encode: when auditing any fire-and-forget/task-spawning code path, do not let a high coverage number substitute for manually tracing statement order across the spawn site and the task body — specifically check whether any caller-side code mutates state the spawned task itself is about to account for, and prefer reproducing the actual runtime ordering with a throwaway script over trusting that "every line ran" implies "ran in the right order."
