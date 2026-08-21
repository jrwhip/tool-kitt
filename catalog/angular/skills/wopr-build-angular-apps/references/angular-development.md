# Angular Development Guide

Standards and conventions for all Angular projects in this workspace.

Reference: [Angular Style Guide](https://angular.dev/style-guide)

## TypeScript

- Use strict type checking
- Prefer type inference when the type is obvious
- Avoid the `any` type; use `unknown` when type is uncertain
- **No for loops.** Use functional methods: `forEach()`, `map()`, `reduce()`, `filter()`, etc. This is a hard rule with no exceptions. If an algorithm requires nested iteration, use nested `forEach`. Functional methods are more readable, less error-prone, and the microsecond performance difference is irrelevant.

## Angular

- Always use standalone components, directives, and pipes over NgModules
- Do NOT set `standalone: true` in `@Component`, `@Directive`, or `@Pipe` decorators — it's the default in Angular 20+
- Use [signals](https://angular.dev/guide/signals) for state management
- Implement lazy loading for feature routes
- Do not use `@HostBinding` or `@HostListener` — use the `host` object in the `@Component` or `@Directive` decorator
- Use `NgOptimizedImage` for all static images (does not work for inline base64 images)

## Accessibility

- Must pass all AXE checks
- Must meet WCAG AA minimums: focus management, color contrast, ARIA attributes

## Components

- Keep components small and single-responsibility
- Use [`input()`](https://angular.dev/guide/components/inputs) and [`output()`](https://angular.dev/guide/components/outputs) functions instead of decorators
- Use [`computed()`](https://angular.dev/guide/signals) for derived state
- Set `changeDetection: ChangeDetectionStrategy.OnPush`
- Prefer inline templates for small components
- For larger components, separate logic (TS), styles (CSS), and template (HTML) into their own files
- Prefer reactive forms over template-driven
- Use [`class` bindings](https://angular.dev/guide/templates/binding#css-class-and-style-property-bindings) instead of `ngClass`
- Use [`style` bindings](https://angular.dev/guide/templates/binding#css-class-and-style-property-bindings) instead of `ngStyle`
- External templates/styles use paths relative to the component TS file

### Example Component

```ts
import { ChangeDetectionStrategy, Component, signal } from '@angular/core';

@Component({
  selector: 'app-server-status',
  templateUrl: 'server-status.html',
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class ServerStatus {
  protected readonly isServerRunning = signal(true);

  toggleServerStatus() {
    this.isServerRunning.update(isServerRunning => !isServerRunning);
  }
}
```

```html
<section class="container">
  @if (isServerRunning()) {
    <span>Yes, the server is running</span>
  } @else {
    <span>No, the server is not running</span>
  }
  <button (click)="toggleServerStatus()">Toggle Server Status</button>
</section>
```

## State Management

- Use signals for local component state
- Use `computed()` for derived state
- Keep state transformations pure and predictable
- Do not use `mutate` on signals — use `update` or `set`

## Templates

- Keep templates simple, avoid complex logic
- Use native control flow (`@if`, `@for`, `@switch`) instead of `*ngIf`, `*ngFor`, `*ngSwitch`
- Use the async pipe to handle observables
- Import and use [built-in pipes](https://angular.dev/guide/templates/pipes) when applicable
- Do not assume globals like `new Date()` are available
- Arrow functions are not supported in templates

## Services

- Design services around a single responsibility
- Use `providedIn: 'root'` for singleton services
- Use [`inject()`](https://angular.dev/essentials/dependency-injection) instead of constructor injection

## Anti-Patterns

### Don't Mix Async Patterns
- **Wrong**: Service returns Promise, component uses Observable
- **Wrong**: Some methods async/await, some return Observable
- **Right**: Everything async returns Observable

### Don't Mix Imperative and Reactive
```typescript
// Wrong - work happens BEFORE the Observable
let result = transformText(input);
return of(result).pipe(delay(1000));

// Right - work happens IN the Observable stream
return of(input).pipe(
  map(text => transformText(text)),
  delay(1000)
);
```

### Don't Create Unnecessary Layers
- **Wrong**: Callback wrapper around Observable wrapper around Promise
- **Wrong**: Service A calls Service B calls Service C for one simple thing
- **Right**: Direct, simple flow. If a layer isn't adding value, it's adding complexity.

### Don't Use `tap()` for State Mutation
- `tap()` is for logging/debugging only
- Data transformations happen in operators (`map`, `switchMap`, etc.) while the data is still an Observable
- The value lands at its destination via `toSignal()`, `rxResource`, or `async` pipe — not via `tap()` stuffing it into a signal

### Side Effects: `subscribe()` for Observables, `effect()` for Signals
Side effects are imperative actions that aren't derived state: navigation, cache invalidation, opening external intents, writing to localStorage. Each reactive primitive has its own tool:

- **Observable streams** → `subscribe()` with `takeUntilDestroyed()` for cleanup
- **Signals** → `effect()` with automatic cleanup

`computed()` must be pure — no side effects. Never convert an Observable to a signal just to use `effect()` on it, and never convert a signal to an Observable just to use `subscribe()` on it. Use whichever tool matches the source.

```typescript
// RIGHT — Observable stream, use subscribe() for imperative side effect
this.deleteAction$.pipe(
  filter(r => r.status === 'success'),
  takeUntilDestroyed(),
).subscribe(() => {
  this.prospectService.reload();
  this.router.navigate(['/prospects']);
});

// RIGHT — Signal source, use effect() for imperative side effect
effect(() => {
  const theme = this.themePreference();
  localStorage.setItem('theme', theme);
});

// WRONG — converting just to use the other tool
effect(() => {
  const result = this.submitResult(); // was already an Observable, converted to signal
  if (result?.status === 'success') this.router.navigate(['/done']); // should have stayed in subscribe()
});
```

**What side effects are NOT for:** setting Angular state that could be derived. If the result of an action should update a signal or computed value, that's derived state — express it with `computed()` or as part of the Observable pipeline. Don't use `subscribe()` or `effect()` to propagate state between signals or between Observables.

### Don't Abuse `effect()`
- **Wrong**: Using `effect()` to propagate state between signals, update services, or as "componentDidUpdate"
- **Right**: `effect()` for imperative side effects that can't be expressed as derived state — syncing to external systems (localStorage, third-party libraries, analytics), triggering navigation, or logging

### Don't Use `subscribe()` to Extract Values
- **Wrong**: Subscribing to an Observable to stuff a value into a signal
- **Right**: Use `toSignal()` to convert Observable to Signal, or `rxResource` for async data loading, or `async` pipe in templates
- **Legitimate**: `subscribe()` with `takeUntilDestroyed()` for imperative side effects (navigation, cache invalidation, external intents) on Observable streams

### No Signal/Observable Round-Trips
- **Wrong**: `toSignal(toObservable(mySignal))` — pointless round-trip
- **Right**: `toSignal()` converts Observable → Signal (one direction). `toObservable()` converts Signal → Observable (one direction). Use `resource()` for async operations that depend on signal values.

### Think About Production
Before writing any service method, ask:
- What will this be when it's an HTTP call?
- Would I do this transformation on the client or server?
- Is this mock mimicking what the real API will return?

Mocks should return what the API will return. Services should be thin wrappers around `http.post()`.

## Summary

- Angular has opinions. Follow them.
- RxJS is the async paradigm, not something sprinkled on top
- Signals are the state management system, not "like useState"
- Stay in one paradigm: reactive OR imperative, not both
- Don't build unnecessary abstractions — direct and simple beats clever and layered

## Reference Links

- [Components](https://angular.dev/essentials/components)
- [Signals](https://angular.dev/essentials/signals)
- [Templates](https://angular.dev/essentials/templates)
- [Dependency Injection](https://angular.dev/essentials/dependency-injection)
- [Style Guide](https://angular.dev/style-guide)
