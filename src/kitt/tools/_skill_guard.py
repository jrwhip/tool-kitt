"""Static threat scanner for skill/plugin content before it's trusted.

Ported from — and a deliberately smaller subset of — the regex-based
scanner in Hermes Agent's ``tools/skills_guard.py``
(NousResearch/hermes-agent). Relevant here because neither Claude Code's
nor GitHub Copilot CLI's plugin marketplace mechanism reviews, signs, or
gatekeeps what gets published: anyone can register a marketplace pointing
at any repo, and there's no platform-level guarantee a skill's content is
safe before installation. This module is that missing gate, run locally
before an operator trusts a skill pulled from outside the org's own
catalog.

Same posture as Hermes's own docs describe it: **useful, not a boundary.**
Regex/AST static analysis over prose and scripts can't catch everything a
determined author could hide, and every pattern here has legitimate uses
in ordinary skill content too (a skill that teaches AWS credential
rotation legitimately mentions ``~/.aws``). Findings are a screening
signal for human review, not a verdict to trust blindly — same
disclaimer Hermes itself makes about its own scanner.

Scope, deliberately narrower than Hermes's ~80-pattern set: WOPR has no
skill-install pipeline of its own to gate (that's the marketplace's job),
so this ships as a standalone diagnostic an operator or agent runs
against any skill directory before trusting it, not a hard install-time
block. No trust-tiered install policy is implemented for the same reason
Hermes's exists — WOPR doesn't own the install step to enforce one at.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

from ._threat_patterns import SKILL_GUARD, for_scope

SCANNER_VERSION = "wopr-skill-guard-v1"

# File extensions worth scanning as text. Binary files are flagged
# structurally (see _check_structure), not pattern-scanned.
SCANNABLE_EXTENSIONS = {
    ".md", ".txt", ".py", ".sh", ".bash", ".js", ".ts", ".rb",
    ".yaml", ".yml", ".json", ".toml", ".cfg", ".ini", ".conf",
}

SUSPICIOUS_BINARY_EXTENSIONS = {
    ".exe", ".dll", ".so", ".dylib", ".bin", ".msi", ".dmg", ".deb", ".rpm",
}

MAX_FILE_COUNT = 50
MAX_TOTAL_SIZE_KB = 1024
MAX_SINGLE_FILE_KB = 256

# (regex, pattern_id, severity, category, description)
# A meaningfully-sized, real subset across every category Hermes covers,
# not an attempt to reproduce all ~80 of its patterns.
THREAT_PATTERNS: list[tuple[re.Pattern[str], str, str, str, str]] = [
    # -- Exfiltration --
    (re.compile(r"curl\s+[^\n]*\$\{?\w*(KEY|TOKEN|SECRET|PASSWORD|CREDENTIAL|API)"),
     "env_exfil_curl", "critical", "exfiltration",
     "curl command interpolating a secret-shaped environment variable"),
    (re.compile(r"\$HOME/\.ssh|~/\.ssh"),
     "ssh_dir_access", "high", "exfiltration",
     "references the user's SSH directory"),
    (re.compile(r"\$HOME/\.aws|~/\.aws"),
     "aws_dir_access", "high", "exfiltration",
     "references the user's AWS credentials directory"),
    (re.compile(r"printenv|env\s*\|"),
     "dump_all_env", "high", "exfiltration",
     "dumps all environment variables"),
    (re.compile(r"cat\s+(?!>)[^\n]*(\.env|credentials|\.netrc|\.pgpass|\.npmrc)"),
     "read_secrets_file", "critical", "exfiltration",
     "reads a known secrets file"),

    # -- Prompt injection --
    (re.compile(r"ignore\s+(?:\w+\s+)*(previous|all|above|prior)\s+instructions", re.IGNORECASE),
     "prompt_injection_ignore", "critical", "injection",
     "prompt injection: ignore previous instructions"),
    (re.compile(r"do\s+not\s+(?:\w+\s+)*tell\s+(?:\w+\s+)*the\s+user", re.IGNORECASE),
     "deception_hide", "critical", "injection",
     "instructs the agent to hide information from the user"),
    (re.compile(r"<!--[^>]*(?:ignore|override|system|secret|hidden)[^>]*-->", re.IGNORECASE),
     "html_comment_injection", "high", "injection",
     "hidden instructions in an HTML comment"),

    # -- Destructive operations --
    (re.compile(r"rm\s+-rf\s+/(?!\S)"),
     "destructive_root_rm", "critical", "destructive",
     "recursive delete from root"),
    (re.compile(r"chmod\s+777"),
     "insecure_perms", "medium", "destructive",
     "sets world-writable permissions"),
    (re.compile(r"\bmkfs\b"),
     "format_filesystem", "critical", "destructive",
     "formats a filesystem"),

    # -- Persistence --
    (re.compile(r"\bcrontab\b"),
     "persistence_cron", "medium", "persistence",
     "modifies cron jobs"),
    (re.compile(r"authorized_keys"),
     "ssh_backdoor", "critical", "persistence",
     "modifies SSH authorized_keys"),
    (re.compile(r"/etc/sudoers|visudo"),
     "sudoers_mod", "critical", "persistence",
     "modifies sudoers (privilege escalation)"),

    # -- Network --
    (re.compile(r"\bnc\s+-[lp]|ncat\s+-[lp]|\bsocat\b"),
     "reverse_shell", "critical", "network",
     "potential reverse shell listener"),
    (re.compile(r"\bngrok\b|\blocaltunnel\b|\bcloudflared\b"),
     "tunnel_service", "high", "network",
     "uses a tunneling service for external access"),

    # -- Obfuscation --
    (re.compile(r"\beval\s*\(\s*[\"']"),
     "eval_string", "high", "obfuscation",
     "eval() with a string argument"),
    (re.compile(r"base64\s+(-d|--decode)\s*\|"),
     "base64_decode_pipe", "high", "obfuscation",
     "base64-decodes and pipes to execution"),
    (re.compile(r"curl\s+[^\n]*\|\s*(ba)?sh"),
     "curl_pipe_shell", "critical", "supply_chain",
     "curl piped to shell (download-and-execute)"),
]

# -- Credential exposure (hardcoded secrets in the skill itself) --
# Sourced from the shared pattern library in _threat_patterns.py, which is
# the single place these regexes are defined — see that module's docstring
# for the scoping rationale and the 2026-08-03 coverage-gap closure record.
THREAT_PATTERNS.extend(
    (cp.pattern, cp.pattern_id, cp.severity, cp.category, cp.description)
    for cp in for_scope(SKILL_GUARD)
)


@dataclass
class Finding:
    pattern_id: str
    severity: str
    category: str
    file: str
    line: int
    match: str
    description: str


@dataclass
class ScanResult:
    skill_name: str
    verdict: str  # "safe" | "caution" | "dangerous"
    findings: list[Finding] = field(default_factory=list)
    summary: str = ""


def _truncate(text: str, max_len: int = 120) -> str:
    return text if len(text) <= max_len else text[: max_len - 3] + "..."


def scan_file(file_path: Path, rel_path: str = "") -> list[Finding]:
    """Scan one file for threat patterns. Empty list for non-scannable files."""
    if not rel_path:
        rel_path = file_path.name
    if file_path.suffix.lower() not in SCANNABLE_EXTENSIONS and file_path.name != "SKILL.md":
        return []
    try:
        content = file_path.read_text(encoding="utf-8")
    except (UnicodeDecodeError, OSError):
        return []

    findings: list[Finding] = []
    lines = content.split("\n")
    # Each pattern visits each line exactly once, so one finding per
    # (pattern, line) pair falls out of the loop structure — but two
    # DIFFERENT patterns matching the same line both report (e.g. the
    # strict and loose hardcoded-secret tiers), which is intentional.
    for pattern, pid, severity, category, description in THREAT_PATTERNS:
        for i, line in enumerate(lines, start=1):
            if pattern.search(line):
                findings.append(Finding(
                    pattern_id=pid, severity=severity, category=category,
                    file=rel_path, line=i, match=_truncate(line.strip()),
                    description=description,
                ))
    return findings


def _check_structure(skill_dir: Path) -> list[Finding]:
    findings: list[Finding] = []
    file_count = 0
    total_size = 0
    for f in skill_dir.rglob("*"):
        if not f.is_file():
            continue
        file_count += 1
        try:
            size = f.stat().st_size
        except OSError:
            continue
        total_size += size
        if size > MAX_SINGLE_FILE_KB * 1024:
            findings.append(Finding(
                pattern_id="oversized_file", severity="medium", category="structural",
                file=str(f.relative_to(skill_dir)), line=0, match=f"{size // 1024}KB",
                description=f"file is {size // 1024}KB (limit: {MAX_SINGLE_FILE_KB}KB)",
            ))
        if f.suffix.lower() in SUSPICIOUS_BINARY_EXTENSIONS:
            findings.append(Finding(
                pattern_id="binary_file", severity="critical", category="structural",
                file=str(f.relative_to(skill_dir)), line=0, match=f"binary: {f.suffix}",
                description=f"binary/executable file ({f.suffix}) should not be in a skill",
            ))
    if file_count > MAX_FILE_COUNT:
        findings.append(Finding(
            pattern_id="too_many_files", severity="medium", category="structural",
            file="(directory)", line=0, match=f"{file_count} files",
            description=f"skill has {file_count} files (limit: {MAX_FILE_COUNT})",
        ))
    if total_size > MAX_TOTAL_SIZE_KB * 1024:
        findings.append(Finding(
            pattern_id="oversized_skill", severity="high", category="structural",
            file="(directory)", line=0, match=f"{total_size // 1024}KB total",
            description=f"skill is {total_size // 1024}KB total (limit: {MAX_TOTAL_SIZE_KB}KB)",
        ))
    return findings


def _determine_verdict(findings: list[Finding]) -> str:
    if any(f.severity == "critical" for f in findings):
        return "dangerous"
    if any(f.severity == "high" for f in findings):
        return "caution"
    return "safe"


def scan_skill(skill_path: Path) -> ScanResult:
    """Scan a skill file or directory. Structural checks apply to directories only."""
    skill_name = skill_path.name
    findings: list[Finding] = []

    if skill_path.is_dir():
        findings.extend(_check_structure(skill_path))
        for f in sorted(skill_path.rglob("*")):
            if f.is_file():
                findings.extend(scan_file(f, str(f.relative_to(skill_path))))
    elif skill_path.is_file():
        findings.extend(scan_file(skill_path, skill_path.name))

    verdict = _determine_verdict(findings)
    if findings:
        categories = sorted({f.category for f in findings})
        summary = f"{skill_name}: {verdict} — {len(findings)} finding(s) in {', '.join(categories)}"
    else:
        summary = f"{skill_name}: clean scan, no threats detected"

    return ScanResult(skill_name=skill_name, verdict=verdict, findings=findings, summary=summary)


def format_scan_report(result: ScanResult) -> str:
    """Render a scan result as a compact, human-readable report."""
    lines = [f"Scan: {result.skill_name}  Verdict: {result.verdict.upper()}"]
    if result.findings:
        severity_order = {"critical": 0, "high": 1, "medium": 2, "low": 3}
        for f in sorted(result.findings, key=lambda x: severity_order.get(x.severity, 4)):
            loc = f"{f.file}:{f.line}" if f.line else f.file
            lines.append(
                f"  [{f.severity.upper()}] {f.category}: {loc} — "
                f"{f.description} ({f.match!r})"
            )
    else:
        lines.append("  No findings.")
    return "\n".join(lines)
