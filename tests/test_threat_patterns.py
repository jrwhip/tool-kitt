"""Tests for ``kitt.tools._threat_patterns``.

This is the shared credential/secret pattern library behind both
``_skill_guard.py`` and ``_leak_vet.py`` (item 12 of the cannibalize plan).
The two consumer modules already have thorough behavioral tests
(``test_skill_guard.py``, ``test_leak_vet.py``) that exercise these
patterns end-to-end; this file covers the library's own contract —
scoping, uniqueness, and the "shared pattern is defined once" property —
so a future edit that breaks scoping fails here instead of only showing up
as a mysterious regression in one of the consumers.
"""

from __future__ import annotations

from kitt.tools._threat_patterns import (
    CREDENTIAL_PATTERNS,
    LEAK_VET,
    SKILL_GUARD,
    for_scope,
)


class TestScoping:
    def test_every_pattern_has_at_least_one_scope(self):
        for cp in CREDENTIAL_PATTERNS:
            assert cp.scopes, f"{cp.pattern_id} has no scope"

    def test_every_scope_is_known(self):
        known = {SKILL_GUARD, LEAK_VET}
        for cp in CREDENTIAL_PATTERNS:
            assert cp.scopes <= known, f"{cp.pattern_id} has unknown scope {cp.scopes}"

    def test_pattern_ids_are_unique(self):
        ids = [cp.pattern_id for cp in CREDENTIAL_PATTERNS]
        assert len(ids) == len(set(ids))

    def test_for_scope_skill_guard_returns_only_skill_guard_patterns(self):
        for cp in for_scope(SKILL_GUARD):
            assert SKILL_GUARD in cp.scopes

    def test_for_scope_leak_vet_returns_only_leak_vet_patterns(self):
        for cp in for_scope(LEAK_VET):
            assert LEAK_VET in cp.scopes

    def test_for_scope_unknown_returns_empty(self):
        assert for_scope("nonexistent") == []


class TestSharedPatterns:
    """Patterns genuinely used by both consumers should exist exactly once."""

    def test_aws_key_pattern_is_shared_not_duplicated(self):
        aws_patterns = [
            cp for cp in CREDENTIAL_PATTERNS if cp.pattern_id == "aws_access_key_leaked"
        ]
        assert len(aws_patterns) == 1
        assert aws_patterns[0].scopes == {SKILL_GUARD, LEAK_VET}

    def test_github_token_pattern_is_shared_not_duplicated(self):
        gh_patterns = [cp for cp in CREDENTIAL_PATTERNS if cp.pattern_id == "github_token_leaked"]
        assert len(gh_patterns) == 1
        assert gh_patterns[0].scopes == {SKILL_GUARD, LEAK_VET}

    def test_shared_aws_pattern_matches_sample_key(self):
        cp = next(cp for cp in CREDENTIAL_PATTERNS if cp.pattern_id == "aws_access_key_leaked")
        assert cp.pattern.search("AKIAIOSFODNN7EXAMPLE")

    def test_shared_github_pattern_matches_both_token_shapes(self):
        cp = next(cp for cp in CREDENTIAL_PATTERNS if cp.pattern_id == "github_token_leaked")
        assert cp.pattern.search("ghp_" + "a" * 36)
        assert cp.pattern.search("github_pat_" + "a" * 80)


class TestGapClosuresStayClosed:
    """Pin the 2026-08-03 closure of the three original coverage gaps.

    Item 12 shipped with three documented asymmetries between the two
    consumers; the operator decided to err on the side of detection and
    skill-guard was widened. If one of these fails, skill-guard's
    credential coverage has silently regressed to the pre-closure state.
    """

    def test_bare_api_key_patterns_are_shared(self):
        for pid in ("anthropic_api_key", "generic_api_key"):
            cp = next(cp for cp in CREDENTIAL_PATTERNS if cp.pattern_id == pid)
            assert cp.scopes == {SKILL_GUARD, LEAK_VET}

    def test_generic_key_pattern_matches_current_provider_formats(self):
        cp = next(cp for cp in CREDENTIAL_PATTERNS if cp.pattern_id == "generic_api_key")
        # Legacy alnum-only, plus formats the 2023-era class missed.
        assert cp.pattern.search("sk-" + "a1" * 12)
        assert cp.pattern.search("sk-proj-" + "a1_b2" * 8)
        assert cp.pattern.search("sk-or-v1-" + "0af1" * 8)

    def test_generic_key_pattern_rejects_hyphenated_identifiers(self):
        cp = next(cp for cp in CREDENTIAL_PATTERNS if cp.pattern_id == "generic_api_key")
        # Without the leading \b these all matched, and any skill
        # mentioning a Notion slug or container name scanned "caution".
        for text in (
            "task-23f4a6b7c8d9e0f1a2b3c4d5e6f7a8b9",
            "desk-1234567890abcdefghij",
            "kiosk-0a1b2c3d4e5f6a7b8c9d0e1f",
        ):
            assert not cp.pattern.search(text), text

    def test_anthropic_keys_report_once_not_twice(self):
        # The widened generic body class would match sk-ant- keys too;
        # the (?!ant-) exclusion keeps one key -> one finding, at the
        # critical Anthropic severity.
        anthropic = next(
            cp for cp in CREDENTIAL_PATTERNS if cp.pattern_id == "anthropic_api_key"
        )
        generic = next(cp for cp in CREDENTIAL_PATTERNS if cp.pattern_id == "generic_api_key")
        key = "sk-ant-" + "a" * 90
        assert anthropic.pattern.search(key)
        assert not generic.pattern.search(key)

    def test_single_broad_private_key_pattern_is_shared(self):
        # The narrow BEGIN (RSA )?PRIVATE KEY variant was retired; both
        # consumers share the broad pattern.
        assert not any(
            cp.pattern_id in ("embedded_private_key_narrow", "embedded_private_key_broad")
            for cp in CREDENTIAL_PATTERNS
        )
        cp = next(cp for cp in CREDENTIAL_PATTERNS if cp.pattern_id == "embedded_private_key")
        assert cp.scopes == {SKILL_GUARD, LEAK_VET}
        for variant in ("", "RSA ", "EC ", "DSA ", "OPENSSH ", "ENCRYPTED "):
            header = f"-----BEGIN {variant}PRIVATE KEY-----"
            assert cp.pattern.search(header), header

    def test_hardcoded_secret_check_is_two_tiered(self):
        strict = next(cp for cp in CREDENTIAL_PATTERNS if cp.pattern_id == "hardcoded_secret")
        loose = next(
            cp for cp in CREDENTIAL_PATTERNS if cp.pattern_id == "credential_assignment"
        )
        # Both tiers now apply to skill_guard; the strict tier stays
        # critical (verdict "dangerous"), the loose tier stays high
        # (verdict "caution") so placeholder-shaped examples don't read
        # as malicious.
        assert strict.scopes == {SKILL_GUARD}
        assert loose.scopes == {SKILL_GUARD, LEAK_VET}
        assert strict.severity == "critical"
        assert loose.severity == "high"
        # A short, unquoted assignment trips only the loose tier.
        short_unquoted = "password: abc12345"
        assert loose.pattern.search(short_unquoted)
        assert not strict.pattern.search(short_unquoted)
