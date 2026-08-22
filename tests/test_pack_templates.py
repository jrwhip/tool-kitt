"""Tests for the pack-template read tools (DEMO-123).

Covers `get_pack_template` and `list_pack_templates`. The tools resolve
paths server-side via `resolve_data_path`, so the tests exercise the
real crew pack's templates (`implementation-tracking.template.md`
et al) that already ship in `catalog/crew/templates/`. No
fixtures need to fake the catalog layout.
"""

from __future__ import annotations

import json

from wopr.tools import pack_templates
from wopr.tools.pack_templates import (
    get_pack_template,
    list_pack_templates,
)

# ``fake_mcp`` fixture lives in tests/conftest.py.


# ---------------------------------------------------------------------------
# get_pack_template
# ---------------------------------------------------------------------------


class TestGetPackTemplate:
    def test_returns_crew_implementation_tracking_template(self):
        """The agent-observed brute-force search target. Lock in the
        canonical path so agents reach it via the MCP tool instead of
        filesystem walk."""
        result = get_pack_template(
            "crew", "implementation-tracking.template.md"
        )
        # Real template content from the crew pack.
        assert "# Implementation Tracking" in result or "tracking" in result.lower()
        assert not result.startswith("Error")

    def test_returns_crew_coder_spec_template(self):
        result = get_pack_template("crew", "coder-spec.template.md")
        assert "coder" in result.lower()
        assert not result.startswith("Error")

    def test_returns_crew_frontend_handoff_template(self):
        result = get_pack_template(
            "crew", "frontend-handoff-contract.template.md"
        )
        assert "handoff" in result.lower() or "contract" in result.lower()
        assert not result.startswith("Error")

    # ----- error paths -----

    def test_empty_pack_returns_error(self):
        result = get_pack_template("", "anything.md")
        assert result.startswith("Error")
        assert "pack is required" in result

    def test_empty_name_returns_error(self):
        result = get_pack_template("crew", "")
        assert result.startswith("Error")
        assert "name is required" in result

    def test_unknown_pack_returns_error(self):
        result = get_pack_template("not-a-real-pack", "any.template.md")
        assert result.startswith("Error")
        assert "not found" in result.lower()

    def test_unknown_template_in_real_pack_returns_error(self):
        result = get_pack_template("crew", "no-such-template.md")
        assert result.startswith("Error")
        assert "not found" in result.lower()
        # Operator gets a hint at how to discover what's available.
        assert "list_pack_templates" in result

    def test_path_traversal_in_pack_rejected(self):
        """`../` segments must be rejected so a caller cannot escape
        the templates directory to read arbitrary files. The MCP
        server runs with the operator's permissions; surfacing
        anything outside `<pack>/templates/` would be a confused-
        deputy bug."""
        result = get_pack_template("../etc", "passwd")
        assert result.startswith("Error")
        assert "no path separators" in result.lower()

    def test_path_traversal_in_name_rejected(self):
        result = get_pack_template("crew", "../../../etc/passwd")
        assert result.startswith("Error")
        assert "no path separators" in result.lower()

    def test_slash_in_pack_rejected(self):
        result = get_pack_template("crew/templates", "x.md")
        assert result.startswith("Error")
        assert "no path separators" in result.lower()

    def test_backslash_in_name_rejected(self):
        result = get_pack_template("crew", "templates\\file.md")
        assert result.startswith("Error")
        assert "no path separators" in result.lower()


# ---------------------------------------------------------------------------
# list_pack_templates
# ---------------------------------------------------------------------------


class TestListPackTemplates:
    def test_lists_crew_pack_templates(self):
        result = list_pack_templates("crew")
        data = json.loads(result)
        assert data["pack"] == "crew"
        assert "templates_dir" in data
        names = [t["name"] for t in data["templates"]]
        # All the load-bearing crew templates ship today.
        assert "implementation-tracking.template.md" in names
        assert "coder-spec.template.md" in names
        assert "tester-spec.template.md" in names
        assert "frontend-handoff-contract.template.md" in names

    def test_each_entry_carries_resolved_path(self):
        """The ``path`` field must be an absolute resolved path so
        operators can audit which dev-tree-vs-bundled copy the server
        served from."""
        result = list_pack_templates("crew")
        data = json.loads(result)
        for entry in data["templates"]:
            assert entry["path"].startswith("/")
            assert entry["name"] in entry["path"]

    def test_subdirectories_not_recursed(self):
        """`templates/by-stack/` is intentionally NOT enumerated.
        Per-stack stubs are discovered via `write_spec_stubs` instead;
        listing them here would surface internal layout that consumers
        do not need.
        """
        result = list_pack_templates("crew")
        data = json.loads(result)
        names = [t["name"] for t in data["templates"]]
        # No `by-stack` entry in the flat listing.
        assert "by-stack" not in names

    # ----- error paths -----

    def test_empty_pack_returns_error(self):
        result = list_pack_templates("")
        assert result.startswith("Error")
        assert "pack is required" in result

    def test_unknown_pack_returns_error(self):
        result = list_pack_templates("not-a-real-pack")
        assert result.startswith("Error")
        assert "not found" in result.lower()
        # The error message names the candidate paths so the operator
        # can debug a dev-vs-bundled-install mismatch.
        assert "Checked:" in result

    def test_path_traversal_rejected(self):
        result = list_pack_templates("../etc")
        assert result.startswith("Error")
        assert "no path separators" in result.lower()


# ---------------------------------------------------------------------------
# Registration
# ---------------------------------------------------------------------------


class TestRegister:
    def test_register_registers_expected_tools(self, fake_mcp):
        pack_templates.register(fake_mcp)
        assert sorted(fake_mcp.registered) == [
            "get_pack_template",
            "list_pack_templates",
        ]
