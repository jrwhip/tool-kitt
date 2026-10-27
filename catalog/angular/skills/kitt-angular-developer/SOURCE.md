# Source Attribution

**Origin:** https://github.com/angular/skills/tree/main/angular-developer
**License:** MIT (Copyright 2026 Google LLC)
**Date Downloaded:** 2026-03-30

These files are copied from the official Angular skills repository maintained by the Angular team at Google. KITT-specific modifications:

- The skill directory (and `name` frontmatter) is renamed from `angular-developer` to `kitt-angular-developer`.
- `routing-eval.jsonl` is a KITT addition (routing-eval fixtures for `check_routing_evals`); it does not exist upstream.
- Routing cues in the skill description have been edited for KITT's skill-routing conventions.

The reference content itself is otherwise unmodified from upstream.

## Checking for Updates

Compare against the upstream repo:
```bash
# View latest commits
curl -s https://api.github.com/repos/angular/skills/commits?path=angular-developer | jq '.[0].commit.message, .[0].commit.author.date'
```

Or browse: https://github.com/angular/skills/commits/main/angular-developer
