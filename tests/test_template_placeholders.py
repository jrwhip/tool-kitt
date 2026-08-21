"""Placeholder / baked-default validator for the catalog's template packs.

Guards two inverse invariants over ``catalog/crew`` and
``catalog/legacy-migration``:

1. Every ``*.template.md`` under the packs' ``templates/`` dirs contains
   at least one placeholder token. A template with nothing left to fill
   in is suspicious — it has probably been baked with a real project's
   content and will silently ship that content to the next consumer.
2. Non-template catalog files (the packs' agents, skills, and commands)
   contain NO leftover placeholder tokens. A placeholder that leaks into
   an agent prompt or skill body reaches the model as literal text.

Recognized placeholder shapes::

    [STACK: ...]          stack-specific fill-in marker
    [PROJECT NAME]        project name marker
    <PLACEHOLDER_KEY>     angle-bracketed UPPER_SNAKE key
    TODO:                 unresolved work marker

Prose that *documents* the marker convention (e.g. the crew orchestrator
explaining that specs must have "zero unresolved ``TODO:`` markers")
does so inside backtick code spans or fenced code blocks; those are
stripped before the non-template scan so documentation of a marker is
never confused with a leak of one. Templates are scanned raw — a
placeholder counts wherever it appears.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

CATALOG_ROOT = Path(__file__).resolve().parents[1] / "catalog"

# Packs whose templates/ dirs are in scope, per pack: (template dir,
# non-template asset dirs to sweep). Missing asset dirs are skipped.
# ``legacy-migration`` was the other in-scope pack; it does not cross
# over, so ``crew`` is the whole scope today.
_PACKS = ("crew",)
_ASSET_DIR_NAMES = ("agents", "skills", "commands")

# The <PLACEHOLDER_KEY> alternative requires at least one underscore so
# UPPER_SNAKE keys match while generics (<T>) and HTML/XML tags do not.
PLACEHOLDER_RE = re.compile(
    r"\[STACK:[^\]]*\]"
    r"|\[PROJECT NAME\]"
    r"|<[A-Z][A-Z0-9]*(?:_[A-Z0-9]+)+>"
    r"|TODO:"
)

_INLINE_CODE_RE = re.compile(r"`[^`\n]+`")


def _strip_code(markdown: str) -> str:
    """Remove fenced code blocks and inline code spans from markdown.

    Fence detection is line-based (a line whose stripped form starts
    with ``` toggles fenced state), which matches how the catalog's
    markdown actually uses fences and avoids regex-over-document
    pathologies.
    """
    kept_lines: list[str] = []
    in_fence = False
    for line in markdown.splitlines():
        if line.lstrip().startswith("```"):
            in_fence = not in_fence
            continue
        if not in_fence:
            kept_lines.append(line)
    return _INLINE_CODE_RE.sub("", "\n".join(kept_lines))


def _template_files() -> list[Path]:
    files: list[Path] = []
    for pack in _PACKS:
        files.extend(sorted((CATALOG_ROOT / pack / "templates").rglob("*.template.md")))
    return files


def _non_template_files() -> list[Path]:
    files: list[Path] = []
    for pack in _PACKS:
        for asset_dir_name in _ASSET_DIR_NAMES:
            asset_dir = CATALOG_ROOT / pack / asset_dir_name
            if asset_dir.is_dir():
                files.extend(sorted(asset_dir.rglob("*.md")))
    return files


def _rel_id(path: Path) -> str:
    return str(path.relative_to(CATALOG_ROOT))


class TestScanScope:
    """The scan must be looking at something real.

    Parametrized tests silently pass when discovery returns nothing
    (e.g. after a catalog re-layout); these guards fail loudly instead.
    """

    def test_template_dirs_contain_templates(self):
        for pack in _PACKS:
            templates_dir = CATALOG_ROOT / pack / "templates"
            assert templates_dir.is_dir(), f"missing templates dir: {templates_dir}"
            found = list(templates_dir.rglob("*.template.md"))
            assert found, f"no *.template.md files under {templates_dir}"

    def test_non_template_scan_is_not_empty(self):
        assert _non_template_files(), (
            "no agent/skill/command markdown found in any scanned pack; "
            "the leftover-placeholder scan is not covering anything"
        )


@pytest.mark.parametrize(
    "template_path", _template_files(), ids=_rel_id
)
def test_template_contains_placeholders(template_path: Path):
    """Invariant 1: a *.template.md with zero placeholders is baked."""
    text = template_path.read_text(encoding="utf-8")
    assert PLACEHOLDER_RE.search(text), (
        f"{_rel_id(template_path)} contains no placeholder tokens "
        "([STACK: ...], [PROJECT NAME], <PLACEHOLDER_KEY>, TODO:). "
        "A template with nothing to fill in has probably been baked "
        "with real project content."
    )


@pytest.mark.parametrize(
    "asset_path", _non_template_files(), ids=_rel_id
)
def test_non_template_has_no_leftover_placeholders(asset_path: Path):
    """Invariant 2: agents/skills/commands must carry no unfilled markers."""
    text = _strip_code(asset_path.read_text(encoding="utf-8"))
    leftovers = sorted(set(PLACEHOLDER_RE.findall(text)))
    assert not leftovers, (
        f"{_rel_id(asset_path)} contains leftover placeholder tokens "
        f"outside code spans: {leftovers}"
    )
