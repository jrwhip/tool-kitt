# Perpetual learning: the LEARNINGS system and its corrective-RAG loop

Current design as shipped. The original (pre-slimming) design this evolved from lives in the source archive; every behavioral difference here was eval-gated (`evals/golden-req*/results/`).

## Corpora and workspace resolution

- **Workspace corpus:** `LEARNINGS.md` at a workspace root, intended to be committed with the project.
- **System corpus:** `~/.kitt/LEARNINGS.md`, machine-local, used only when a call names no target at all.
- **Registry:** `~/.kitt/workspaces.txt`, consulted for outside-workspace aggregated reads.

A workspace root is resolved by one shared function, `find_workspace_root` (`src/kitt/tools/_workspace_root.py`): walk up from the target, nearest directory containing `kitt.yml` **or** `LEARNINGS.md` wins, bounded by the git toplevel. Seed, append, search, and curate all use it, so reads and writes address the same file by construction. A named target that resolves to nothing is an **error naming every searched path**, never a silent fallback. Multi-package repos resolve per package (nearest `kitt.yml`), so each package carries its own corpus; a root corpus exists only where one was deliberately seeded, and the seeded file itself becomes the root marker.

## Entry format and writers

Entries are `## LRN-YYYY-MM-DD-<letter>: <title>` with a fenced `meta` block (date, project, stack tags, req list, provenance, severity, optional `seed: true`) and three labeled paragraphs: What happened / Why it matters / Pattern to encode. Append-only; the format is validated on write.

Writers: the **crew auditor** (sole writer during crew runs, 0-3 distilled entries per gate, distillation gates in its agent spec), `seed_learnings` (curated starter entries at project init, `catalog/crew/data/learnings-seed/`), and `kitt learnings append` (CLI, for Bash-capable agents and operators). Seed entries carry verified post-cutoff facts on purpose: carrying facts the model cannot know is the corpus's highest-value job.

## Retrieval and the CRAG pre-step

`learnings_search` runs a deterministic prefilter (REQ-ID match, stack-tag intersection, recency scoring; defaults 180 days, limit 20) plus an optional semantic path (fastembed sidecar, `[embeddings]` extra; a `.npz` derived file, rebuildable, auto-gitignored). The crew orchestrator runs the pre-step **once per crew run**:

1. Empty result: empty `relevant_learnings` to every agent; no evaluator.
2. Five or fewer candidates: inject all, marked advisory; no evaluator. At this corpus size every agent sees everything anyway; selection adds nothing.
3. More than five: the independent `crew-evaluator` agent grades HIGH/MEDIUM/LOW; only HIGH+MEDIUM are injected.

The evaluator is a **loop-topology circuit breaker**, not a verification step: the auditor writes the corpus and every agent reads it, so an independent grader prevents the loop from feeding its own biases back (the model-collapse argument). That argument is about topology, not model capability, which is why the evaluator survived the era of models that self-verify: it engages only above the threshold where selection pressure exists. Specs always win over learnings on conflict.

## Curation

`curate_learnings` is deterministic and LLM-free: entries past the staleness window (default 365 days) are archived to a sibling file, never deleted; `seed: true` entries are never touched. The design is a partial port of hermes-agent's curator (`agent/curator.py`) with the LLM consolidation pass deliberately not ported; provenance credited per file, not paraphrased.

## Why this shape

Injected-context selection exists because of lost-in-the-middle degradation and context rot; append-only plus a single gated writer exists because self-improvement loops amplify their own bias; deterministic curation exists because an LLM rewriting its own memory is the exact failure the independent evaluator guards against elsewhere.
