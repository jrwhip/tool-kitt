"""Tests for the scout-contract validator.

Covers the gate behavior the orchestrator skill relies on:

* Valid contracts return ``ok: true`` with parsed frontmatter and no
  errors.
* Missing required keys, malformed YAML, missing frontmatter
  delimiters, empty critical fields, and non-absolute / non-existent
  paths each surface specific errors so the operator can fix exactly
  the gap.
* Warnings (empty class inventory for a non-class REQ, very short
  body) do not flip ``ok`` to False; that decision belongs to the
  orchestrator's gate, not this helper.
"""

from __future__ import annotations

import json
from pathlib import Path

from wopr.tools import crew_contracts
from wopr.tools.crew_contracts import validate_scout_contract

# ``fake_mcp`` fixture lives in tests/conftest.py.


def _write_contract(
    contracts_dir: Path,
    req_id: str = "REQ-001",
    *,
    frontmatter_lines: list[str] | None = None,
    body: str = (
        "## Discovery notes\n\n"
        "The scout walked apps/billing/ and identified the invoice domain.\n"
        "Three entities are in scope: Invoice, LineItem, Customer.\n"
    ),
    include_frontmatter_delimiters: bool = True,
) -> Path:
    """Build a scout contract on disk and return its path.

    ``frontmatter_lines`` is the body of the frontmatter block (without
    the ``---`` delimiters). Defaults to a fully-populated contract.
    """
    if frontmatter_lines is None:
        frontmatter_lines = [
            f"req_id: {req_id}",
            "generated_at: 2026-05-18T14:00:00Z",
            "files_touched:",
            "  - apps/billing/src/main/java/com/example/Invoice.java",
            "  - apps/billing/src/main/java/com/example/InvoiceRepository.java",
            "class_inventory:",
            "  - name: Invoice",
            "    file: apps/billing/src/main/java/com/example/Invoice.java",
            "    signature: \"public class Invoice { ... }\"",
            "package_structure: |",
            "  com.example.billing",
            "    .Invoice",
            "    .InvoiceRepository",
        ]
    target_dir = contracts_dir / req_id
    target_dir.mkdir(parents=True, exist_ok=True)
    path = target_dir / "scout.md"
    parts: list[str] = []
    if include_frontmatter_delimiters:
        parts.append("---\n")
    parts.extend(line + "\n" for line in frontmatter_lines)
    if include_frontmatter_delimiters:
        parts.append("---\n")
    parts.append("\n")
    parts.append(body)
    path.write_text("".join(parts), encoding="utf-8")
    return path


# ---------------------------------------------------------------------------
# Happy path
# ---------------------------------------------------------------------------


class TestValidContract:
    def test_fully_populated_contract_is_ok(self, tmp_path: Path) -> None:
        path = _write_contract(tmp_path / "crew-contracts")
        result = json.loads(validate_scout_contract(str(path)))
        assert result["ok"] is True
        assert result["errors"] == []
        assert result["frontmatter"]["req_id"] == "REQ-001"
        assert len(result["frontmatter"]["files_touched"]) == 2
        assert result["body_length"] > 0

    def test_returns_absolute_resolved_path(self, tmp_path: Path) -> None:
        """``path`` in the result is the resolved absolute path so the
        operator and orchestrator can copy-paste it from the report."""
        path = _write_contract(tmp_path / "crew-contracts")
        result = json.loads(validate_scout_contract(str(path)))
        assert Path(result["path"]) == path.resolve()


# ---------------------------------------------------------------------------
# Path / I/O failures
# ---------------------------------------------------------------------------


class TestPathFailures:
    def test_relative_path_rejected(self) -> None:
        result = json.loads(validate_scout_contract("relative/scout.md"))
        assert result["ok"] is False
        assert any("not absolute" in e for e in result["errors"])

    def test_nonexistent_path_rejected(self, tmp_path: Path) -> None:
        missing = tmp_path / "crew-contracts" / "REQ-099" / "scout.md"
        result = json.loads(validate_scout_contract(str(missing)))
        assert result["ok"] is False
        assert any("does not exist" in e for e in result["errors"])


# ---------------------------------------------------------------------------
# Frontmatter shape failures
# ---------------------------------------------------------------------------


class TestFrontmatterFailures:
    def test_missing_frontmatter_delimiters_rejected(self, tmp_path: Path) -> None:
        """A markdown file with no ``---`` block at top is rejected;
        the orchestrator must not silently treat a body-only contract
        as valid."""
        path = _write_contract(
            tmp_path / "crew-contracts",
            include_frontmatter_delimiters=False,
        )
        result = json.loads(validate_scout_contract(str(path)))
        assert result["ok"] is False
        assert any("frontmatter" in e.lower() for e in result["errors"])

    def test_malformed_yaml_in_frontmatter(self, tmp_path: Path) -> None:
        path = _write_contract(
            tmp_path / "crew-contracts",
            frontmatter_lines=[
                "req_id: REQ-001",
                "files_touched: [unterminated",
            ],
        )
        result = json.loads(validate_scout_contract(str(path)))
        assert result["ok"] is False
        assert any("yaml" in e.lower() for e in result["errors"])

    def test_frontmatter_must_be_mapping(self, tmp_path: Path) -> None:
        """A YAML scalar or list at top level is not acceptable."""
        path = _write_contract(
            tmp_path / "crew-contracts",
            frontmatter_lines=["- just-a-list"],
        )
        result = json.loads(validate_scout_contract(str(path)))
        assert result["ok"] is False
        assert any("mapping" in e.lower() for e in result["errors"])


# ---------------------------------------------------------------------------
# Required-key failures
# ---------------------------------------------------------------------------


class TestRequiredKeys:
    def test_missing_req_id(self, tmp_path: Path) -> None:
        path = _write_contract(
            tmp_path / "crew-contracts",
            frontmatter_lines=[
                "generated_at: 2026-05-18T14:00:00Z",
                "files_touched:",
                "  - x.java",
                "class_inventory: []",
                "package_structure: pkg",
            ],
        )
        result = json.loads(validate_scout_contract(str(path)))
        assert result["ok"] is False
        assert any("`req_id`" in e for e in result["errors"])

    def test_empty_req_id_rejected(self, tmp_path: Path) -> None:
        path = _write_contract(
            tmp_path / "crew-contracts",
            frontmatter_lines=[
                "req_id: \"\"",
                "generated_at: 2026-05-18T14:00:00Z",
                "files_touched:",
                "  - x.java",
                "class_inventory: []",
                "package_structure: pkg",
            ],
        )
        result = json.loads(validate_scout_contract(str(path)))
        assert result["ok"] is False
        assert any("`req_id`" in e and "non-empty" in e for e in result["errors"])

    def test_empty_files_touched_rejected(self, tmp_path: Path) -> None:
        """files_touched is the load-bearing field for the downstream
        agents; an empty list means scout under-populated and the
        coder/tester would have nothing to consult."""
        path = _write_contract(
            tmp_path / "crew-contracts",
            frontmatter_lines=[
                "req_id: REQ-001",
                "generated_at: 2026-05-18T14:00:00Z",
                "files_touched: []",
                "class_inventory: []",
                "package_structure: pkg",
            ],
        )
        result = json.loads(validate_scout_contract(str(path)))
        assert result["ok"] is False
        assert any(
            "`files_touched` is empty" in e for e in result["errors"]
        )

    def test_files_touched_must_be_list_of_strings(self, tmp_path: Path) -> None:
        path = _write_contract(
            tmp_path / "crew-contracts",
            frontmatter_lines=[
                "req_id: REQ-001",
                "generated_at: 2026-05-18T14:00:00Z",
                "files_touched:",
                "  - 42",
                "class_inventory: []",
                "package_structure: pkg",
            ],
        )
        result = json.loads(validate_scout_contract(str(path)))
        assert result["ok"] is False
        assert any(
            "`files_touched`" in e and "non-empty strings" in e
            for e in result["errors"]
        )

    def test_class_inventory_entry_missing_subkeys(self, tmp_path: Path) -> None:
        path = _write_contract(
            tmp_path / "crew-contracts",
            frontmatter_lines=[
                "req_id: REQ-001",
                "generated_at: 2026-05-18T14:00:00Z",
                "files_touched:",
                "  - x.java",
                "class_inventory:",
                "  - name: Invoice",
                "package_structure: pkg",
            ],
        )
        result = json.loads(validate_scout_contract(str(path)))
        assert result["ok"] is False
        assert any(
            "`class_inventory[0]`" in e and "file" in e and "signature" in e
            for e in result["errors"]
        )

    def test_empty_package_structure_rejected(self, tmp_path: Path) -> None:
        path = _write_contract(
            tmp_path / "crew-contracts",
            frontmatter_lines=[
                "req_id: REQ-001",
                "generated_at: 2026-05-18T14:00:00Z",
                "files_touched:",
                "  - x.java",
                "class_inventory: []",
                "package_structure: \"\"",
            ],
        )
        result = json.loads(validate_scout_contract(str(path)))
        assert result["ok"] is False
        assert any("`package_structure`" in e for e in result["errors"])


# ---------------------------------------------------------------------------
# Warnings (do not flip ok)
# ---------------------------------------------------------------------------


class TestAdvisoryWarnings:
    def test_empty_class_inventory_is_warning_not_error(
        self, tmp_path: Path
    ) -> None:
        """A REQ that is genuinely not class-shaped (a config edit, a
        documentation REQ) can legitimately have an empty class
        inventory. Surface as advisory; do not block."""
        path = _write_contract(
            tmp_path / "crew-contracts",
            frontmatter_lines=[
                "req_id: REQ-002",
                "generated_at: 2026-05-18T14:00:00Z",
                "files_touched:",
                "  - README.md",
                "class_inventory: []",
                "package_structure: docs only",
            ],
        )
        result = json.loads(validate_scout_contract(str(path)))
        assert result["ok"] is True
        assert any("class_inventory" in w for w in result["warnings"])

    def test_very_short_body_is_warning(self, tmp_path: Path) -> None:
        path = _write_contract(
            tmp_path / "crew-contracts",
            body="ok\n",
        )
        result = json.loads(validate_scout_contract(str(path)))
        assert result["ok"] is True
        assert any("body" in w for w in result["warnings"])


# ---------------------------------------------------------------------------
# Registration
# ---------------------------------------------------------------------------


class TestRegister:
    def test_register_registers_expected_tools(self, fake_mcp) -> None:
        crew_contracts.register(fake_mcp)
        assert sorted(fake_mcp.registered) == ["validate_scout_contract"]
