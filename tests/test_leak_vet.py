"""Tests for ``kitt.tools._leak_vet``.

Mirrors the standalone-module test style used for other ``tools/_*.py``
helpers (e.g. ``test_embeddings.py``): unit tests directly against the
module's public functions, independent of the ``append_learnings`` wiring
covered separately in ``test_learnings.py``.
"""

from __future__ import annotations

from kitt.tools._leak_vet import find_leak_indicators, format_leak_report


class TestFindLeakIndicators:
    def test_clean_text_has_no_findings(self):
        text = (
            "When a coder retries after a validation failure, mock the "
            "boundary at the SDK client, not the HTTP layer."
        )
        assert find_leak_indicators(text) == []

    def test_flags_aws_access_key(self):
        findings = find_leak_indicators("uses AKIAIOSFODNN7EXAMPLE for staging")
        assert any(f.kind == "secret" for f in findings)

    def test_flags_github_token(self):
        findings = find_leak_indicators("auth with ghp_" + "a" * 36)
        assert any(f.kind == "secret" for f in findings)

    def test_flags_private_key_block(self):
        text = "-----BEGIN RSA PRIVATE KEY-----\nMIIEow...\n"
        findings = find_leak_indicators(text)
        assert any(f.kind == "secret" for f in findings)

    def test_flags_credential_assignment(self):
        findings = find_leak_indicators('client_secret: "z9x8y7w6v5u4t3s2"')
        assert any(f.kind == "secret" for f in findings)

    def test_flags_macos_home_dir(self):
        findings = find_leak_indicators("fix landed in /Users/jsmith/Projects/foo")
        assert any(f.kind == "identity" and "macOS" in f.detail for f in findings)

    def test_flags_linux_home_dir(self):
        findings = find_leak_indicators("script lives at /home/jsmith/tools/run.sh")
        assert any(f.kind == "identity" and "Linux" in f.detail for f in findings)

    def test_flags_windows_home_dir(self):
        findings = find_leak_indicators(r"config at C:\Users\jsmith\AppData\config.yaml")
        assert any(f.kind == "identity" and "Windows" in f.detail for f in findings)

    def test_flags_email_address(self):
        findings = find_leak_indicators("reported by jane.doe@example-corp.com")
        assert any(f.kind == "identity" and "email" in f.detail for f in findings)

    def test_flags_non_allowlisted_ip(self):
        findings = find_leak_indicators("service reachable at 172.31.4.19 internally")
        assert any(f.kind == "identity" and "IP" in f.detail for f in findings)

    def test_allows_loopback_ip(self):
        findings = find_leak_indicators("the dev server listens on 127.0.0.1:8080")
        assert not any(f.detail == "IP address" for f in findings)

    def test_allows_documentation_range_ip(self):
        findings = find_leak_indicators("example config points at 203.0.113.5")
        assert not any(f.detail == "IP address" for f in findings)

    def test_multiple_findings_all_reported(self):
        text = (
            "Debugged with jane.doe@example-corp.com from /Users/jsmith/repo, "
            "key was AKIAIOSFODNN7EXAMPLE"
        )
        findings = find_leak_indicators(text)
        kinds = {f.kind for f in findings}
        assert "identity" in kinds
        assert "secret" in kinds
        assert len(findings) >= 3

    def test_empty_text_has_no_findings(self):
        assert find_leak_indicators("") == []
        assert find_leak_indicators(None) == []


class TestFormatLeakReport:
    def test_report_lists_every_finding(self):
        findings = find_leak_indicators(
            "contact jane.doe@example-corp.com about /Users/jsmith/notes"
        )
        report = format_leak_report(findings)
        assert report.startswith("Error:")
        assert "email address" in report
        assert "macOS home directory path" in report

    def test_report_instructs_generic_rewrite(self):
        findings = find_leak_indicators("email jane.doe@example-corp.com")
        report = format_leak_report(findings)
        assert "generically" in report.lower()
