# RxJS & Signals in Angular

How reactive data flow actually works. Not the "Observable as Promise" pattern from Stack Overflow. The real thing.

## The One Rule

**Never bounce between signals and Observables.** You can convert once — Observable → Signal with `toSignal()`, or Signal → Observable with `toObservable()` — but that's a one-way door. You don't go back.

- Observable source → operators → `toSignal()` → template. **Done.** It's a signal now. Use `computed()` for any further derivation.
- Signal source → `computed()` → template. **Done.** It was never an Observable and it doesn't need to become one.

If you catch yourself writing `toSignal(toObservable(...))`, you've already failed.

## Mental Model

Two primitives. Different jobs. Pick one per data flow and stay in it.

| | Signals | Observables |
|---|---------|-------------|
| What | Synchronous reactive state | Asynchronous event streams |
| When | Data at rest | Data in motion |
| Read | Call it: `count()` | Let Angular subscribe (`toSignal`, `async`, `rxResource`) |
| Write | `set()`, `update()` | Push: `subject.next()` |
| Derive | `computed()` | `pipe()` with operators |
| Template | Direct: `{{ count() }}` | Convert once: `toSignal()` or `async` pipe |

Signals hold values. Observables describe what happens when values arrive. Operators define what to do between one value and the next.

## The Pipeline

Data flows in one direction. Source to template. No detours. No round-trips.

```
Observable source  -->  pipe(operators)  -->  toSignal()    -->  Template
Observable source  -->  pipe(operators)  -->  Template (via async pipe)
Signal source      -->  computed()       -->  Template
```

**Prioritize transformations in the original format.** If data is an Observable, prefer operators in the pipe. If it's a signal, prefer `computed()`. You can transform after conversion — combining two signals with `computed()` makes sense — but don't convert just to transform when an operator would have done the job.

## Reads

### `rxResource` / `httpResource`

For loading data that depends on reactive parameters. Angular manages the subscription, cancellation, loading state, and error state. The Observable goes in. Signals come out. One conversion.

```typescript
// In a service (singleton — shared across components)
private readonly resource = rxResource({
  stream: () => this.http.get<Item[]>('/api/items'),
});

readonly items = computed(() => this.resource.value() ?? []);
readonly loading = this.resource.isLoading;
readonly error = this.resource.error;
```

```typescript
// With reactive parameters — re-fetches when the signal changes
private readonly resource = rxResource({
  params: () => ({ id: this.userId() }),
  stream: ({ params }) => this.http.get<User>(`/api/users/${params.id}`),
});
```

`resource` and `rxResource` are **read-only by design**. Angular's docs: "resource is intended for read operations, not operations which perform mutations." It cancels in-progress loads when parameters change — that would abort mutations.

The component reads signals. No `subscribe()`. No `OnInit`. No `DestroyRef`.

```typescript
export class ItemList {
  private readonly itemService = inject(ItemService);

  protected readonly items = this.itemService.items;
  protected readonly loading = this.itemService.loading;
}
```

### `toSignal()` for Observable streams

When the source is an Observable and you need operators before it reaches the template. The Observable stays an Observable through the entire operator chain. At the end — once — it becomes a signal.

```typescript
// Source is already an Observable (valueChanges). Operators transform it.
// toSignal() at the end is the ONE conversion. No round-trips.
readonly results = toSignal(
  this.searchControl.valueChanges.pipe(
    debounceTime(300),
    distinctUntilChanged(),
    switchMap(query => this.searchService.search(query)),
  ),
  { initialValue: [] },
);
```

After `toSignal()`, it's a signal. Derive further with `computed()`. Never convert it back to an Observable.

## Mutations

`resource` / `rxResource` don't handle mutations. Something else does.

**Angular's official docs** (angular.dev/guide/http/making-requests) show `.subscribe()` for mutations: `http.post(...).subscribe()`. That's the documented baseline.

For anything beyond fire-and-forget — preventing double submits, handling concurrent requests, feeding results back to the template — operators are the tool:

```typescript
// Event source — represents "user clicked submit"
private readonly submit$ = new Subject<FormPayload>();

// Pipeline — submit events flow through operators to produce results
// The Observable stays an Observable through all operators.
// toSignal() at the end is the ONE conversion.
readonly submitResult = toSignal(
  this.submit$.pipe(
    exhaustMap(payload =>
      this.http.post<Item>('/api/items', payload).pipe(
        map(item => ({ status: 'success' as const, item })),
        catchError(err => of({ status: 'error' as const, err })),
      ),
    ),
  ),
);

// Template calls this — pushes into the stream
onSubmit(payload: FormPayload): void {
  this.submit$.next(payload);
}
```

The operator choice IS the concurrency strategy:

| Operator | Behavior | Use for |
|----------|----------|---------|
| `exhaustMap` | Ignores new events while one is in-flight | Submit buttons (prevents double-submit) |
| `switchMap` | Cancels in-flight, starts new | Search/typeahead (latest query wins) |
| `concatMap` | Queues and processes sequentially | Ordered operations (each must complete) |
| `mergeMap` | Fires all in parallel | Independent parallel operations |

The operator handles the "what happens when the next value arrives" question. No imperative `isSaving` flag. No `if (this.saving) return`. The operator defines the behavior declaratively.

### Template reads the result

```html
@if (submitResult(); as result) {
  @if (result.status === 'success') {
    <p>Saved: {{ result.item.name }}</p>
  }
  @if (result.status === 'error') {
    <p class="error">{{ result.err.message }}</p>
  }
}
```

The Subject is the source. The operators transform. `toSignal()` is the one conversion. The template reads the signal.

## Services

Thin. Stateless for mutations. Stateful only via `rxResource` for reads.

```typescript
@Injectable({ providedIn: 'root' })
export class ItemService {
  private readonly http = inject(HttpClient);

  // READ — rxResource manages the state
  // Observable goes in, signals come out. One conversion.
  private readonly resource = rxResource({
    stream: () => this.http.get<Item[]>('/api/items'),
  });

  readonly items = computed(() => this.resource.value() ?? []);
  readonly loading = this.resource.isLoading;
  readonly error = this.resource.error;

  reload(): void {
    this.resource.reload();
  }

  // MUTATIONS — return Observables. No state. No tap().
  // The component's pipeline handles the result.
  create(input: CreateItemInput): Observable<Item> {
    return this.http.post<Item>('/api/items', input);
  }

  update(id: string, input: UpdateItemInput): Observable<Item> {
    return this.http.put<Item>(`/api/items/${id}`, input);
  }

  delete(id: string): Observable<void> {
    return this.http.delete<void>(`/api/items/${id}`);
  }
}
```

Mutations return clean Observables. No `tap()`. No state management. The component's mutation pipeline calls `service.reload()` on success if the read cache needs refreshing.

## Transformations

**Transform data in its original format.** If data starts as an Observable, transform it with operators before converting to a signal. If data starts as a signal, transform it with `computed()`. Don't convert just to transform.

```typescript
// RIGHT — data starts as Observable, transform with operators, then convert once
readonly results = toSignal(
  this.searchControl.valueChanges.pipe(
    debounceTime(300),
    switchMap(query => this.searchService.search(query)),
  ),
  { initialValue: [] },
);

// RIGHT — data is already a signal, transform with computed()
readonly fullName = computed(() => `${this.firstName()} ${this.lastName()}`);

// WRONG — converting to Observable just to use operators, then back to signal
readonly fullName = toSignal(
  toObservable(this.firstName).pipe(
    map(first => `${first} ${this.lastName()}`),
  ),
);
```

After conversion, further derivation uses the destination format. Observable → `toSignal()` → `computed()` for further derivation. That's fine — one conversion happened, and `computed()` is the right tool in signal-land.

## Side Effects

Side effects are imperative actions — navigation, cache invalidation, external intents, localStorage writes, analytics. They aren't derived state and can't be expressed with `computed()`.

**Use the tool that matches the source:**

| Source | Side effect tool | Cleanup |
|--------|-----------------|---------|
| Observable stream | `subscribe()` | `takeUntilDestroyed()` |
| Signal | `effect()` | Automatic |

Don't convert between Observables and signals just to use the other side effect tool.

```typescript
// Observable source — subscribe() for side effects
this.provisionAction$.pipe(
  filter(r => r.status === 'success'),
  takeUntilDestroyed(),
).subscribe(() => this.userConfigService.reload());

// Signal source — effect() for side effects
effect(() => {
  const preference = this.darkMode();
  localStorage.setItem('darkMode', String(preference));
});
```

**Side effects should be rare.** Most reactive flows terminate at the template via `toSignal()`, `rxResource`, or `async` pipe. Side effects are for actions that leave the Angular rendering system — not for propagating state between signals or stuffing Observable values into signals.

## Signals

### `signal()` — Local mutable state

```typescript
readonly count = signal(0);
```

### `computed()` — Derived state (lazy, memoized)

```typescript
readonly doubleCount = computed(() => this.count() * 2);
```

Use for any value derived from other signals. Grouping, filtering, combining. This is where transformation logic lives for synchronous data that's already in signal form.

### `linkedSignal()` — Writable derived state

When state depends on another signal but the user can override it:

```typescript
// Recomputes from source when source changes.
// User can .set() to override until source changes again.
readonly selectedOption = linkedSignal(() => this.options()[0]);
```

Use case: a form field initialized from loaded data but editable by the user.

### `effect()` — Imperative side effects for signals

For reacting to signal changes with imperative actions that aren't derived state:

- localStorage / sessionStorage
- Canvas rendering
- Third-party libraries
- Navigation, analytics, logging

**Not for**: state propagation between signals, orchestration, "componentDidUpdate" behavior, bridging signals to reactive forms. If the result can be expressed as `computed()`, it's not a side effect.

`effect()` is the signal-world equivalent of `subscribe()` on Observables. Use whichever matches the source — don't convert between them just to use the other tool.

Angular's docs: "There are no situations where effect is good, only situations where it is appropriate."

## Anti-Patterns

### Round-tripping between signals and Observables

```typescript
// WRONG — signal to Observable and back to signal
readonly results = toSignal(
  toObservable(this.searchQuery).pipe(
    debounceTime(300),
    switchMap(query => this.searchService.search(query)),
  ),
  { initialValue: [] },
);
```

If the source is a signal, it stays a signal. Use `computed()` for derivation. If you need Observable operators (debounce, switchMap), the source should have been an Observable from the start — like `formControl.valueChanges`.

### Observable as Promise

```typescript
// WRONG — treating Observable as a fancy Promise
this.service.getData().subscribe(data => {
  this.mySignal.set(data);
  this.loading = false;
});
```

The Observable exists solely to extract a value and stuff it somewhere. This is `fetch().then()` with extra steps. Use `toSignal()` or `rxResource()` instead.

### `tap()` for state mutation

```typescript
// WRONG — side effects hiding in the pipeline
return this.http.get<Data>('/api/data').pipe(
  tap(data => this.dataSignal.set(data)),
  tap(() => this.loading.set(false)),
);
```

`tap()` is for logging and debugging. If you're setting state in `tap()`, you've left the reactive pipeline and are doing imperative work inside a declarative structure. The destination (`toSignal`, `rxResource`, `async` pipe) is where the value lands. If you need a side effect (navigation, cache invalidation), that happens in `subscribe()` at the end — not in `tap()` in the middle.

### Wrapping Observables in Signals manually

```typescript
// WRONG — reimplementing what toSignal/rxResource already do
ngOnInit() {
  this.service.list().pipe(
    takeUntilDestroyed(this.destroyRef),
  ).subscribe(items => this.items.set(items));
}
```

Manual subscription management. `rxResource` or `toSignal` handles subscription lifecycle, initial values, and cleanup.

### `effect()` for orchestration or state propagation

```typescript
// WRONG — effect as componentDidUpdate
effect(() => {
  const id = this.userId();
  this.service.loadUser(id).subscribe(user => this.user.set(user));
});

// WRONG — effect to propagate state between signals
effect(() => {
  this.fullName.set(`${this.firstName()} ${this.lastName()}`);
});
```

The first example combines two anti-patterns — `effect()` for data loading and `subscribe()` to stuff values. Use `rxResource` with a reactive `params`. The second example is derived state — use `computed()` instead. `effect()` is for imperative side effects that leave the Angular system (localStorage, navigation, analytics), not for wiring signals together.

### Collapsing Observables to Promises

```typescript
// WRONG — Observable to Promise conversion
const result = await firstValueFrom(this.service.create(input));
```

Collapses the stream into a single value extraction. You lose cancellation, backpressure, and composability. Stay in one paradigm.

## Quick Reference

| I need to... | Use |
|---|---|
| Load data for a component | `rxResource` in service, `computed()` in component |
| Load data based on a signal | `rxResource` with `params` |
| Transform signal data for display | `computed()` — stays in signal world |
| Transform Observable data before conversion | Operators in `pipe()` — transform before `toSignal()` |
| Handle a form submission | `Subject` + operator + `toSignal()` — stays in Observable world until the one conversion |
| Prevent double-submit | `exhaustMap` operator |
| Cancel previous request | `switchMap` operator |
| Debounce user input | `formControl.valueChanges.pipe(debounceTime())` + `toSignal()` — source is Observable, stays Observable |
| Side effect on Observable event | `subscribe()` + `takeUntilDestroyed()` (navigation, cache reload, external intent) |
| Side effect on signal change | `effect()` (localStorage, analytics, third-party sync) |
| Form fields from loaded data | `linkedSignal()` — derives from source, user can override |
| Create writable derived state | `linkedSignal()` |
| Expose read-only state | `signal.asReadonly()` or `computed()` |

## Reference

- [Signals](https://angular.dev/guide/signals)
- [Resource API](https://angular.dev/guide/signals/resource)
- [RxJS Interop](https://angular.dev/ecosystem/rxjs-interop)
- [HTTP Requests](https://angular.dev/guide/http/making-requests)
