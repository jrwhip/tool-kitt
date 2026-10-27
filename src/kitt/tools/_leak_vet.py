"""Identity/leak vet for content headed into a committable, cross-project corpus.

``LEARNINGS.md`` is meant to hold generic, reusable lessons — the whole point
of CRAG retrieval is that an entry captured on one project is useful on
another. An entry that embeds one developer's home directory, email address,
an internal IP, or a secret-shaped string is both a leak risk (this file gets
committed) and a *bad lesson* — it won't generalize to the next project or
developer who retrieves it.

Modeled on the identity-leak guard in a colleague's ``harvest.py``
(an internal scaffolding project), adapted for a write-time gate rather than a
promote-up gate: this runs on every ``append_learnings`` call, not just at
some future promotion step, because the corpus is committable from the
moment an entry lands.

Unlike ``_embeddings.py``-style soft degrade-on-missing-dependency modules,
this has no optional dependency — it's pure regex, always available.

Deliberately a *reject-and-explain*, not a silent-rewrite. Auto-redacting a
leaked path inside what's supposed to be a reusable lesson would just as
often mangle the lesson's content as fix it (e.g. a path that is itself the
subject of the lesson). Better to hand the caller a specific, fixable
complaint and require a genericized rewrite.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from ._threat_patterns import LEAK_VET, for_scope

# Secret-shaped patterns — a learning entry should never need to contain an
# actual secret to be useful; if a lesson is about a credential, it should
# describe the credential's *role*, not its value. Reuses the shape of
# checks in prompt-log-hook.py's scrub(), applied here as reject rather than
# redact.
#
# Sourced from the shared pattern library in _threat_patterns.py, which is
# the single place these regexes are defined — see that module's docstring
# for the scoping rationale and the 2026-08-03 coverage-gap closure record.
_SECRET_PATTERNS = [(cp.pattern, cp.label) for cp in for_scope(LEAK_VET)]

# Identity/path leaks — real local machine or personal identity fragments
# that don't belong in a corpus meant to generalize across projects and
# developers.
_HOME_DIR_PATTERNS = [
    (re.compile(r"/Users/([A-Za-z0-9_.\-]+)/"), "macOS home directory path"),
    (re.compile(r"/home/([A-Za-z0-9_.\-]+)/"), "Linux home directory path"),
    (re.compile(r"C:\\Users\\([A-Za-z0-9_.\-]+)\\"), "Windows home directory path"),
]

_EMAIL_PATTERN = re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b")

_IPV4_PATTERN = re.compile(r"\b(?:\d{1,3}\.){3}\d{1,3}\b")

# Loopback/documentation/example ranges are legitimate in a generic lesson
# (e.g. "the service listens on 127.0.0.1:8080") and are not flagged.
_IP_ALLOWLIST_PREFIXES = ("127.", "0.0.0.0", "10.0.0.", "192.0.2.", "198.51.100.", "203.0.113.")


@dataclass(frozen=True)
class LeakFinding:
    kind: str
    detail: str
    excerpt: str


def find_leak_indicators(text: str | None) -> list[LeakFinding]:
    """Scan ``text`` for identity/secret leaks. Returns an empty list when clean.

    Accepts ``None`` and treats it the same as empty. The current call site
    (``append_learnings``) already guards against an empty/missing entry
    before reaching this function, so the ``None`` case isn't hit in
    production today, but the signature matches actual runtime behavior
    (``if not text``) rather than promising a guarantee no caller relies on.
    """
    if not text:
        return []

    findings: list[LeakFinding] = []

    for pattern, label in _SECRET_PATTERNS:
        m = pattern.search(text)
        if m:
            findings.append(LeakFinding("secret", label, _excerpt(text, m)))

    for pattern, label in _HOME_DIR_PATTERNS:
        m = pattern.search(text)
        if m:
            findings.append(LeakFinding("identity", label, _excerpt(text, m)))

    m = _EMAIL_PATTERN.search(text)
    if m:
        findings.append(LeakFinding("identity", "email address", _excerpt(text, m)))

    for m in _IPV4_PATTERN.finditer(text):
        ip = m.group(0)
        if any(ip.startswith(prefix) for prefix in _IP_ALLOWLIST_PREFIXES):
            continue
        findings.append(LeakFinding("identity", "IP address", _excerpt(text, m)))
        break  # one IP finding is enough signal; don't spam the report

    return findings


def _excerpt(text: str, match: re.Match[str]) -> str:
    start = max(0, match.start() - 20)
    end = min(len(text), match.end() + 20)
    snippet = text[start:end].replace("\n", " ")
    return f"...{snippet}..." if start > 0 or end < len(text) else snippet


def format_leak_report(findings: list[LeakFinding]) -> str:
    """Render findings as a rejection message for the tool caller to act on."""
    lines = [
        "Error: entry rejected — looks like it contains identifying or secret "
        "content that doesn't belong in a cross-project learnings corpus:",
    ]
    for f in findings:
        lines.append(f"  - {f.kind}: {f.detail} (near: {f.excerpt!r})")
    lines.append(
        "Rewrite the entry to describe the lesson generically — no real "
        "hostnames, paths, emails, IPs, or credential values — then retry."
    )
    return "\n".join(lines)
