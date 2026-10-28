"""Single source of truth for credential/secret-shaped regex patterns.

``_skill_guard.py`` (scans third-party skill content for prompt-injection
and dangerous instructions before an operator trusts it) and ``_leak_vet.py``
(scans learnings entries headed into a committable corpus for secret/PII
leakage) each independently grew a small set of "does this look like a
leaked credential" patterns. This module is where those patterns live now,
so there is exactly one place that defines what an AWS access key or a
GitHub token looks like as a regex.

Ported idea, narrower scope than the source
--------------------------------------------
Modeled on Hermes Agent's ``tools/threat_patterns.py``, which centralizes
its *entire* prompt-injection/exfiltration/C2 pattern set behind an
``"all"/"context"/"strict"`` scope system shared by several scanners. KITT's
two consumers don't need that: skill-guard's injection/destructive/
persistence/network/obfuscation patterns have no leak-vet equivalent
(leak-vet isn't scanning for reverse shells), and leak-vet's identity
patterns (home directories, email addresses, IP addresses) have no
skill-guard equivalent (skill-guard isn't scanning for whose laptop a skill
was authored on). Only the credential/secret-shaped patterns are
conceptually shared, so that's what's centralized here — everything else
stays local to the module that needs it.

Scoping
-------
Each :class:`CredentialPattern` declares which consumer(s) use it via
``scopes`` (a subset of ``{"skill_guard", "leak_vet"}``). A pattern used by
both is defined exactly once and both consumers pull the same compiled
regex — that's the actual duplication this module removes. A pattern used
by only one consumer is *still* defined here rather than inline in that
consumer's module, so the full inventory of credential-shaped detectors
KITT ships is visible in one file even though today only one caller applies
each of them.

Coverage gaps closed 2026-08-03 (operator decision)
---------------------------------------------------
Consolidating both lists side by side originally surfaced three places
where the two consumers' coverage differed; the item-12 refactor recorded
them without changing behavior. The operator has since decided to err on
the side of detection, and all three were closed by widening skill-guard:

1. **Bare API-key formats** — the Anthropic (``sk-ant-...``) and generic
   (``sk-...``) key patterns now also carry the ``skill_guard`` scope, so
   a raw leaked key in skill content trips credential_exposure. Pointing
   the generic pattern at arbitrary skill prose exposed two regex defects,
   fixed at the same time: a leading ``\b`` (hyphenated identifiers like
   ``task-<hash>`` matched without it) and ``-``/``_`` in the body class
   (the 2023-era alnum-only class missed current formats like
   ``sk-proj-...`` and ``sk-or-v1-...``). Widening the body made
   ``sk-ant-`` keys match both patterns, so the generic one excludes them
   via ``(?!ant-)`` — one key, one finding, at the higher severity.
2. **Private-key variants** — the narrow ``BEGIN PRIVATE KEY`` /
   ``BEGIN RSA PRIVATE KEY`` pattern was retired; both consumers share the
   broad pattern, which also catches ``EC``, ``DSA``, ``OPENSSH``, and
   ``ENCRYPTED`` headers.
3. **Hardcoded-secret threshold** — skill-guard now applies BOTH tiers:
   its original strict pattern (quoted, 20+ chars) stays ``critical`` and
   drives a "dangerous" verdict, while leak-vet's looser
   ``credential_assignment`` (optionally quoted, 8+ chars, extra key
   names) is additionally applied at ``high``, driving only "caution".
   The tiering is deliberate: placeholder-shaped config examples in
   legitimate skills land at "caution" (a prompt for human review, which
   is skill-guard's whole job) without inflating everything to
   "dangerous". A long quoted secret matches both patterns and reports
   twice on the same line; the critical finding drives the verdict.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

SKILL_GUARD = "skill_guard"
LEAK_VET = "leak_vet"


@dataclass(frozen=True)
class CredentialPattern:
    """One secret/credential-shaped regex plus per-consumer presentation.

    ``severity``/``category``/``description`` are skill-guard's finding
    fields; ``label`` is leak-vet's finding field. A pattern scoped to only
    one consumer still fills in both, since the counterfactual ("what would
    the other consumer call this") costs nothing and keeps the dataclass
    uniform.
    """

    pattern_id: str
    pattern: re.Pattern[str]
    scopes: frozenset[str]
    severity: str
    category: str
    description: str
    label: str


CREDENTIAL_PATTERNS: tuple[CredentialPattern, ...] = (
    # -- Shared: identical regex, used by both consumers --
    CredentialPattern(
        pattern_id="aws_access_key_leaked",
        pattern=re.compile(r"AKIA[0-9A-Z]{16}"),
        scopes=frozenset({SKILL_GUARD, LEAK_VET}),
        severity="critical",
        category="credential_exposure",
        description="AWS access key ID in skill content",
        label="AWS access key",
    ),
    CredentialPattern(
        pattern_id="github_token_leaked",
        pattern=re.compile(r"ghp_[A-Za-z0-9]{36}|github_pat_[A-Za-z0-9_]{80,}"),
        scopes=frozenset({SKILL_GUARD, LEAK_VET}),
        severity="critical",
        category="credential_exposure",
        description="GitHub personal access token in skill content",
        label="GitHub token",
    ),
    CredentialPattern(
        pattern_id="embedded_private_key",
        pattern=re.compile(r"-----BEGIN[^-]*PRIVATE KEY-----"),
        scopes=frozenset({SKILL_GUARD, LEAK_VET}),
        severity="critical",
        category="credential_exposure",
        description="embedded private key",
        label="embedded private key",
    ),
    CredentialPattern(
        pattern_id="credential_assignment",
        pattern=re.compile(
            r'(?i)(?:api[_-]?key|token|secret|password|passwd|client[_-]?secret)'
            r'\s*[=:]\s*["\']?[A-Za-z0-9+/_.\-]{8,}'
        ),
        scopes=frozenset({SKILL_GUARD, LEAK_VET}),
        severity="high",
        category="credential_exposure",
        description="credential-shaped assignment",
        label="credential-shaped assignment",
    ),
    CredentialPattern(
        pattern_id="anthropic_api_key",
        pattern=re.compile(r"\bsk-ant-[A-Za-z0-9_-]{90,}"),
        scopes=frozenset({SKILL_GUARD, LEAK_VET}),
        severity="critical",
        category="credential_exposure",
        description="Anthropic API key",
        label="Anthropic API key",
    ),
    # \b: without a left boundary, hyphenated identifiers ending in "sk"
    # (task-..., desk-..., kiosk-...) match and verdict innocent skills
    # "caution". (?!ant-): sk-ant- keys must report once, as the critical
    # Anthropic finding above, not twice. The -/_ in the body class are
    # required for current provider formats (sk-proj-..., sk-or-v1-...).
    CredentialPattern(
        pattern_id="generic_api_key",
        pattern=re.compile(r"\bsk-(?!ant-)[A-Za-z0-9_-]{20,}"),
        scopes=frozenset({SKILL_GUARD, LEAK_VET}),
        severity="high",
        category="credential_exposure",
        description="API key",
        label="API key",
    ),
    # -- skill_guard only --
    # The strict tier of the hardcoded-secret check: quoted, 20+ chars,
    # critical. credential_assignment above is the loose tier (optionally
    # quoted, 8+, high) — strict hits verdict "dangerous", loose-only hits
    # verdict "caution", so placeholder-shaped config examples in
    # legitimate skills prompt review without reading as malicious.
    CredentialPattern(
        pattern_id="hardcoded_secret",
        pattern=re.compile(
            r'(?:api[_-]?key|token|secret|password)\s*[=:]\s*'
            r'["\'][A-Za-z0-9+/=_-]{20,}',
            re.IGNORECASE,
        ),
        scopes=frozenset({SKILL_GUARD}),
        severity="critical",
        category="credential_exposure",
        description="possible hardcoded API key, token, or secret",
        label="hardcoded secret",
    ),
)


def for_scope(scope: str) -> list[CredentialPattern]:
    """Return the patterns applicable to ``scope``, in definition order."""
    return [p for p in CREDENTIAL_PATTERNS if scope in p.scopes]
