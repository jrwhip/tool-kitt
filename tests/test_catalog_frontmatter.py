"""Catalog-wide guard: every shipped SKILL.md must expose usable frontmatter.

Not a nice-to-have. The skill ``name`` and ``description`` in this block are
what every CLI indexes for auto-selection, what ``to_copilot_skill`` requires
to be non-empty, and where the ``wopr-loading:`` tier declaration lives. YAML
that does not parse produces no error anywhere -- every consumer just sees a
skill with no name and no description.

That is not hypothetical: ``wopr-run-crew`` shipped with an unquoted colon
inside its description (``... configured with `wopr.yml`: net-new ...``),
which YAML reads as a nested mapping and rejects. The crew pack's flagship
skill was invisible to every frontmatter consumer, silently, until this test
existed.
"""

from __future__ import annotations

from pathlib import Path

from wopr.converters import parse_claude

REPO_ROOT = Path(__file__).resolve().parents[1]


class TestCatalogFrontmatterIsParseable:
    """Every shipped SKILL.md must expose name and description via YAML.

    Not a nice-to-have: the tier declaration, the resolver's one-liner,
    and every CLI's own skill index all come from this frontmatter. One
    catalog skill (``wopr-run-crew``) shipped with an unquoted colon in
    its description, which made the whole block unparseable YAML -- so
    every consumer saw a skill with no name and no description, silently.
    """

    def test_every_skill_has_parseable_name_and_description(self):
        broken: list[str] = []
        for skill_md in sorted((REPO_ROOT / "catalog").rglob("SKILL.md")):
            front = parse_claude(
                skill_md.read_text(encoding="utf-8", errors="replace")
            ).frontmatter
            name = front.get("name")
            description = front.get("description")
            if not isinstance(name, str) or not name.strip():
                broken.append(f"{skill_md}: missing/unparseable name")
            if not isinstance(description, str) or not description.strip():
                broken.append(f"{skill_md}: missing/unparseable description")
        assert not broken, "Unparseable skill frontmatter:\n" + "\n".join(broken)
