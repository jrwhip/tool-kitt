# Workspace Tooling

Build tooling and supply chain conventions for Angular projects.

## NX Monorepo (When Applicable)

Some projects use an NX monorepo. When working in one, follow NX conventions:

### Structure

```
├── apps/          # Applications (each app may have a matching *-e2e project)
├── libs/          # Shared libraries (grouped by app or domain)
├── tools/         # Build tooling and scripts
```

### Running Tasks

Always run tasks through NX, invoked via the project's package manager (e.g. `npx nx`, `pnpm nx`, `yarn nx`). The workspace may alias `ng` to `nx`.

```bash
npx nx serve <app>                           # Dev server
npx nx build <app>                           # Build
npx nx test <app>                            # Unit tests
npx nx lint <app>                            # Lint
npx nx e2e <app>-e2e                         # E2E tests
npx nx affected -t test                      # Test only what changed
npx nx graph                                 # Dependency graph
```

### Generators

Use NX generators instead of bare `ng generate` for consistency with the workspace structure. Check `nx.json` for workspace-level generator defaults before scaffolding.

```bash
npx nx generate @nx/angular:application my-app
npx nx generate @nx/angular:library my-lib
npx nx generate @nx/angular:component my-component --project=my-app
```

### Non-Monorepo Projects

For standalone Angular projects (no NX), use the Angular CLI directly:

```bash
ng serve
ng build
ng test
ng generate component my-component
```

Check the project's `package.json` scripts for any custom commands.

## Package Manager and Supply Chain Protection

Use whichever package manager the project has standardized on (npm, pnpm, yarn, bun). Do not switch package managers mid-project without a documented reason.

Some package managers offer additional supply-chain protections worth knowing about. PNPM is used below as a concrete example; check whether the project's chosen package manager has equivalent settings.

### Minimum Release Age

PNPM supports a `minimumReleaseAge` setting in `pnpm-workspace.yaml` (requires PNPM >= 10.16.0). When configured, no package version published less than the specified window can be installed. This guards against typosquatting, account takeover, and malicious new versions.

```yaml
# Example: 30-day maturity window
minimumReleaseAge: 43200 # minutes (approximately 30 days)
```

Trusted or frequently updated packages (like `@angular/*`) can be excluded:

```yaml
minimumReleaseAgeExclude:
  - '@angular/*'
  - '@angular-devkit/*'
```

### Version Enforcement

Projects may enforce strict PNPM version matching:

```yaml
packageManagerStrict: true
packageManagerStrictVersion: true
```

This means the exact PNPM version declared in `package.json`'s `packageManager` field must match the invoked version.

### Version Overrides

The `pnpm.overrides` section in `package.json` can pin specific dependency versions to mitigate known CVEs. When adding or updating overrides, document the CVE and the date the safe version clears the release age window.

## API Service Generation (OpenAPI)

API services can be auto-generated from OpenAPI specifications using tools like Swagger CodeGen or OpenAPI Generator with the `typescript-angular` language target. When a project uses generated API services:

### Rules

- **Never modify generated files by hand.** The next codegen run will overwrite your changes.
- **If the generated service is wrong, fix the OpenAPI spec**, not the generated TypeScript.
- **Consume generated services directly.** Components and feature services import from the generated API library. Do not duplicate HTTP calls with `HttpClient` for endpoints that have a generated service.
- **Check the project for the generated service location.** They typically live in a dedicated library directory (e.g., under `libs/` in a monorepo, or a specific `src/api/` directory in standalone projects).

### What This Looks Like

```typescript
// Use the generated service
import { ItemsApiService } from '@my-org/api-client';

@Injectable({ providedIn: 'root' })
export class ItemService {
  private readonly api = inject(ItemsApiService);

  private readonly resource = rxResource({
    stream: () => this.api.getItems(),
  });

  readonly items = computed(() => this.resource.value() ?? []);
}
```

Do not hand-write `HttpClient` calls for endpoints covered by a generated service.
