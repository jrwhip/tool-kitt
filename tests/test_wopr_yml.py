"""Tests for the wopr.yml generator (propose + write split).

Covers the deterministic mapping from detection output to proposed YAML
text, the YAML round-trip safety check, and the write side's refusals
(no overwrite by default, no parent-dir auto-create).
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
import yaml

from wopr import _atomic_write
from wopr.tools import wopr_yml
from wopr.tools.stack_detect import detect_stack

# ``workspace`` and ``fake_mcp`` fixtures live in tests/conftest.py.
from wopr.tools.wopr_yml import (
    propose_wopr_yml,
    write_wopr_yml,
)


def _write_spring_boot(workspace: Path) -> None:
    (workspace / "pom.xml").write_text(
        """
<project>
  <groupId>com.example.app</groupId>
  <artifactId>cases</artifactId>
  <version>1.0.0</version>
  <properties>
    <java.version>21</java.version>
  </properties>
  <dependencies>
    <dependency>
      <groupId>org.springframework.boot</groupId>
      <artifactId>spring-boot-starter-web</artifactId>
    </dependency>
    <dependency>
      <groupId>org.springdoc</groupId>
      <artifactId>springdoc-openapi-starter-webmvc-ui</artifactId>
    </dependency>
  </dependencies>
</project>
        """.strip(),
        encoding="utf-8",
    )


def _write_angular_nx_app(workspace: Path) -> None:
    (workspace / "nx.json").write_text("{}", encoding="utf-8")
    (workspace / "pnpm-lock.yaml").write_text("lockfileVersion: 9.0", encoding="utf-8")
    (workspace / "package.json").write_text(
        json.dumps({
            "name": "root",
            "dependencies": {"@angular/core": "^21.0.0"},
            "devDependencies": {
                "@openapitools/openapi-generator-cli": "^7.21.0",
                "vitest": "^1.0.0",
                "typescript": "^5.0.0",
            },
        }),
        encoding="utf-8",
    )
    apps = workspace / "apps"
    apps.mkdir()
    app = apps / "example-app"
    app.mkdir()
    (app / "project.json").write_text(
        json.dumps({
            "name": "example-app",
            "projectType": "application",
            "targets": {"build": {"executor": "@angular/build:application"}},
        }),
        encoding="utf-8",
    )


def _write_fastapi_single_app(workspace: Path) -> None:
    (workspace / "pyproject.toml").write_text(
        """
[project]
name = "cases-api"
version = "0.1.0"
dependencies = ["fastapi>=0.110"]
        """.strip(),
        encoding="utf-8",
    )


class TestProposeWoprYml:
    def test_invalid_detection_json_returns_error(self, workspace: Path):
        result = propose_wopr_yml("not-json", ".")
        assert result.startswith("Error")

    def test_detection_must_be_a_json_object(self, workspace: Path):
        """A JSON document like `null` or `[]` parses cleanly but is
        not the dict shape detect_stack guarantees. Reject explicitly
        rather than letting `.get()` raise AttributeError."""
        for payload in ("null", "[]", '"a string"', "42"):
            result = propose_wopr_yml(payload, ".")
            assert result.startswith("Error"), payload
            assert "JSON object" in result, payload

    def test_missing_target_returns_error(self, workspace: Path):
        _write_spring_boot(workspace)
        detection = detect_stack(str(workspace))
        result = propose_wopr_yml(detection, "does-not-exist")
        assert result.startswith("Error")

    def test_spring_boot_root_target(self, workspace: Path):
        _write_spring_boot(workspace)
        detection = detect_stack(str(workspace))
        proposed = propose_wopr_yml(detection, ".")
        parsed = yaml.safe_load(proposed)
        assert parsed["project"]["slug"] == "ws"
        assert parsed["project"]["build_file"] == "pom.xml"
        # base_package derived from pom.xml groupId+artifactId.
        assert parsed["project"]["base_package"].startswith("com.example.app")
        # target_source_root reflects the derived package.
        assert parsed["project"]["target_source_root"].startswith("src/main/java/")
        assert parsed["project"]["test_root"] == "src/test/java"
        # OpenAPI producer defaults populated.
        assert parsed["openapi"]["spec_url"] == "/v3/api-docs"
        assert "springdoc-openapi" in parsed["openapi"]["pinned_generator_version"]

    def test_angular_nx_app_target(self, workspace: Path):
        _write_angular_nx_app(workspace)
        detection = detect_stack(str(workspace))
        proposed = propose_wopr_yml(detection, "apps/example-app")
        parsed = yaml.safe_load(proposed)
        assert parsed["project"]["slug"] == "example-app"
        assert parsed["project"]["build_file"] == "project.json"
        assert parsed["project"]["target_source_root"] == "src/app"
        # Angular target does not get a base_package.
        assert "base_package" not in parsed["project"]
        # Frontend consumer: openapi pin lifted from root package.json devDeps.
        assert parsed["openapi"]["pinned_generator_version"] == "openapi-generator-cli 7.21.0"

    def test_fastapi_single_app(self, workspace: Path):
        _write_fastapi_single_app(workspace)
        detection = detect_stack(str(workspace))
        proposed = propose_wopr_yml(detection, ".")
        parsed = yaml.safe_load(proposed)
        assert parsed["project"]["build_file"] == "pyproject.toml"
        assert parsed["project"]["test_root"] == "tests"
        # No openapi block for a fastapi project that doesn't declare a role.
        assert "openapi" not in parsed

    def test_output_round_trips_through_yaml_safe_load(self, workspace: Path):
        """Every proposed YAML must parse cleanly. No exotic escaping."""
        _write_spring_boot(workspace)
        detection = detect_stack(str(workspace))
        proposed = propose_wopr_yml(detection, ".")
        parsed = yaml.safe_load(proposed)
        assert isinstance(parsed, dict)
        assert "project" in parsed
        assert "specs" in parsed

    def test_output_includes_todo_comments(self, workspace: Path):
        _write_spring_boot(workspace)
        detection = detect_stack(str(workspace))
        proposed = propose_wopr_yml(detection, ".")
        assert "TODO" in proposed
        # Spec paths get TODO comments pointing at templates.
        assert "catalog/crew/templates/coder-spec.template.md" in proposed
        assert "catalog/crew/templates/tester-spec.template.md" in proposed

    def test_base_package_ignores_parent_pom_coordinates(self, workspace: Path):
        """Regression: pom.xml's <parent> block carries the upstream POM's
        groupId/artifactId. The proposer must read the project's OWN
        coordinates, not the parent's."""
        (workspace / "pom.xml").write_text(
            """
<project>
  <modelVersion>4.0.0</modelVersion>
  <parent>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-parent</artifactId>
    <version>3.2.0</version>
  </parent>
  <groupId>com.example.app</groupId>
  <artifactId>cases</artifactId>
  <version>1.0.0</version>
  <dependencies>
    <dependency>
      <groupId>org.springframework.boot</groupId>
      <artifactId>spring-boot-starter-web</artifactId>
    </dependency>
  </dependencies>
</project>
            """.strip(),
            encoding="utf-8",
        )
        detection = detect_stack(str(workspace))
        proposed = propose_wopr_yml(detection, ".")
        parsed = yaml.safe_load(proposed)
        assert parsed["project"]["base_package"].startswith("com.example.app")
        assert "spring_boot_starter_parent" not in parsed["project"]["base_package"]

    def test_pom_with_dependency_management_before_project_coords(self, workspace: Path):
        """Regression: pom.xml legally has <dependencyManagement> before the
        project's own <groupId>/<artifactId>. The ElementTree-based parser
        must read direct children of <project> only and ignore nested
        groupId/artifactId inside dependencyManagement entries."""
        (workspace / "pom.xml").write_text(
            """
<project>
  <modelVersion>4.0.0</modelVersion>
  <parent>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-parent</artifactId>
    <version>3.2.0</version>
  </parent>
  <dependencyManagement>
    <dependencies>
      <dependency>
        <groupId>org.junit</groupId>
        <artifactId>junit-bom</artifactId>
        <version>5.10.0</version>
        <type>pom</type>
        <scope>import</scope>
      </dependency>
    </dependencies>
  </dependencyManagement>
  <groupId>com.example.app</groupId>
  <artifactId>cases</artifactId>
  <version>1.0.0</version>
</project>
            """.strip(),
            encoding="utf-8",
        )
        detection = detect_stack(str(workspace))
        proposed = propose_wopr_yml(detection, ".")
        parsed = yaml.safe_load(proposed)
        # Project's own groupId wins, not the parent's and not junit-bom's.
        assert parsed["project"]["base_package"].startswith("com.example.app")
        assert "junit" not in parsed["project"]["base_package"]
        assert "spring_boot_starter_parent" not in parsed["project"]["base_package"]

    def test_pom_with_namespace_declarations(self, workspace: Path):
        """Regression: pom.xml with an explicit xmlns declaration prefixes
        every parsed tag with the namespace URI. The parser must strip
        the namespace when comparing local names."""
        (workspace / "pom.xml").write_text(
            """<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0">
  <modelVersion>4.0.0</modelVersion>
  <groupId>com.example.app</groupId>
  <artifactId>namespaced</artifactId>
  <version>1.0.0</version>
  <dependencies>
    <dependency>
      <groupId>org.springframework.boot</groupId>
      <artifactId>spring-boot-starter-web</artifactId>
    </dependency>
  </dependencies>
</project>
            """.strip(),
            encoding="utf-8",
        )
        detection = detect_stack(str(workspace))
        proposed = propose_wopr_yml(detection, ".")
        parsed = yaml.safe_load(proposed)
        assert parsed["project"]["base_package"].startswith("com.example.app")

    def test_base_package_falls_back_to_java_source_package(self, workspace: Path):
        """Step 3 of the base-package strategy: when pom.xml exists but
        neither <groupId> nor <artifactId> can be recovered, scan
        src/main/java for the first non-empty `package` declaration."""
        # Pom that parses but declares nothing usable for base_package.
        (workspace / "pom.xml").write_text(
            """
<project>
  <modelVersion>4.0.0</modelVersion>
  <parent>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-parent</artifactId>
    <version>3.2.0</version>
  </parent>
  <version>1.0.0</version>
</project>
            """.strip(),
            encoding="utf-8",
        )
        # First .java file is package-less (default package); second has
        # a real package declaration. The fallback must skip the first
        # and find the second.
        src = workspace / "src" / "main" / "java"
        src.mkdir(parents=True)
        (src / "Anonymous.java").write_text("public class Anonymous {}\n", encoding="utf-8")
        pkg_dir = src / "gov" / "example" / "fromsource"
        pkg_dir.mkdir(parents=True)
        (pkg_dir / "Real.java").write_text(
            "package gov.example.fromsource;\npublic class Real {}\n",
            encoding="utf-8",
        )
        detection = detect_stack(str(workspace))
        proposed = propose_wopr_yml(detection, ".")
        parsed = yaml.safe_load(proposed)
        assert parsed["project"]["base_package"] == "gov.example.fromsource"

    def test_base_package_step3_is_deterministic_across_multiple_packages(
        self, workspace: Path
    ):
        """rglob order is filesystem-dependent. The function sorts the
        iterator so multiple .java files with different packages produce
        the same result on every machine (sorted lexicographically by
        path, so `bar` wins over `foo`)."""
        # Pom that parses but has no recoverable coordinates -> step 3.
        (workspace / "pom.xml").write_text(
            "<project><modelVersion>4.0.0</modelVersion></project>",
            encoding="utf-8",
        )
        src = workspace / "src" / "main" / "java"
        # Two real packages. Lexicographic sort puts `bar` before `foo`,
        # so `gov.example.bar` is the expected winner regardless of how
        # the filesystem orders rglob.
        bar = src / "gov" / "example" / "bar"
        foo = src / "gov" / "example" / "foo"
        bar.mkdir(parents=True)
        foo.mkdir(parents=True)
        (bar / "Bar.java").write_text(
            "package gov.example.bar;\npublic class Bar {}\n", encoding="utf-8"
        )
        (foo / "Foo.java").write_text(
            "package gov.example.foo;\npublic class Foo {}\n", encoding="utf-8"
        )
        detection = detect_stack(str(workspace))
        proposed = propose_wopr_yml(detection, ".")
        parsed = yaml.safe_load(proposed)
        assert parsed["project"]["base_package"] == "gov.example.bar"

    def test_pom_that_is_a_directory_is_ignored(
        self, workspace: Path, caplog: pytest.LogCaptureFixture
    ):
        """A pom.xml entry that is a directory (hostile workspace, or a
        weird checkout) must not crash the parser AND must not even
        reach the parse step. ``pom.is_file()`` is the guard; this test
        pins that behavior in case the guard ever gets relaxed to
        ``exists()`` (which would then raise IsADirectoryError or log
        a ParseError warning)."""
        # Create a directory named pom.xml.
        (workspace / "pom.xml").mkdir()
        synthetic_detection: dict[str, Any] = {
            "workspace_path": str(workspace),
            "project_type": "single-app",
            "monorepo_type": None,
            "targets": [{
                "target_path": ".",
                "language": "java",
                "framework": "spring-boot",
                "framework_version": None,
                "package_manager": "maven",
                "libraries": [],
                "test_runner": None,
                "openapi_role": None,
            }],
            "wopr_yml_inventory": [],
            "detected_external_signals": [],
        }
        with caplog.at_level("WARNING", logger="wopr"):
            proposed = propose_wopr_yml(json.dumps(synthetic_detection), ".")
        # The parse path must short-circuit on ``pom.is_file()``, so no
        # WARNING-level "failed to parse" record should appear.
        parse_failures = [
            rec for rec in caplog.records
            if "failed to parse" in rec.message
        ]
        assert parse_failures == [], (
            "expected pom.is_file() to short-circuit; got: "
            f"{[r.message for r in parse_failures]}"
        )
        # base_package falls through to TODO because nothing parseable.
        base_line = next(
            line for line in proposed.splitlines() if "base_package" in line
        )
        assert "TODO" in base_line

    def test_base_package_todo_when_java_target_has_no_pom_and_no_sources(
        self, workspace: Path
    ):
        """Coverage for the empty path: language is java but neither
        pom.xml nor src/main/java exists. The function returns
        (None, False) and the proposer emits the TODO line."""
        synthetic_detection: dict[str, Any] = {
            "workspace_path": str(workspace),
            "project_type": "single-app",
            "monorepo_type": None,
            "targets": [{
                "target_path": ".",
                "language": "java",
                "framework": None,
                "framework_version": None,
                "package_manager": "maven",
                "libraries": [],
                "test_runner": None,
                "openapi_role": None,
            }],
            "wopr_yml_inventory": [],
            "detected_external_signals": [],
        }
        proposed = propose_wopr_yml(json.dumps(synthetic_detection), ".")
        base_line = next(
            line for line in proposed.splitlines() if "base_package" in line
        )
        assert "TODO" in base_line
        # Must not emit a literal empty value.
        assert "base_package:  " not in proposed

    def test_base_package_uses_group_when_artifact_matches_suffix(self, workspace: Path):
        """When the groupId already ends with the artifactId, the
        concatenated form `group.artifact` would duplicate the
        artifactId segment. The function returns groupId alone instead."""
        (workspace / "pom.xml").write_text(
            """
<project>
  <modelVersion>4.0.0</modelVersion>
  <groupId>com.example.app</groupId>
  <artifactId>app</artifactId>
  <version>1.0.0</version>
  <dependencies>
    <dependency>
      <groupId>org.springframework.boot</groupId>
      <artifactId>spring-boot-starter-web</artifactId>
    </dependency>
  </dependencies>
</project>
            """.strip(),
            encoding="utf-8",
        )
        detection = detect_stack(str(workspace))
        proposed = propose_wopr_yml(detection, ".")
        parsed = yaml.safe_load(proposed)
        assert parsed["project"]["base_package"] == "com.example.app"
        # Confirm no `com.example.app.app` duplication slipped in.
        assert "app.app" not in proposed

    def test_artifactId_with_hyphens_emits_todo(self, workspace: Path):
        """The hyphen-to-underscore artifactId transform is a guess.
        Surface a TODO so the operator confirms it matches the code."""
        (workspace / "pom.xml").write_text(
            """
<project>
  <groupId>com.example.app</groupId>
  <artifactId>example-program-api</artifactId>
  <version>1.0.0</version>
  <dependencies>
    <dependency>
      <groupId>org.springframework.boot</groupId>
      <artifactId>spring-boot-starter-web</artifactId>
    </dependency>
  </dependencies>
</project>
            """.strip(),
            encoding="utf-8",
        )
        detection = detect_stack(str(workspace))
        proposed = propose_wopr_yml(detection, ".")
        assert "example_program_api" in proposed
        # TODO comment must appear inline with the base_package line.
        base_line = next(
            line for line in proposed.splitlines() if line.startswith("  base_package:")
        )
        assert "TODO" in base_line
        assert "hyphens" in base_line or "underscore" in base_line

    def test_slug_folds_unicode_to_ascii(self, workspace: Path, tmp_path: Path):
        """Project at `apps/café` produces slug `cafe`, not `caf`. The
        prior regex stripped the accented glyph instead of folding it."""
        accented = workspace / "apps" / "café"
        accented.mkdir(parents=True)
        (workspace / "nx.json").write_text("{}", encoding="utf-8")
        (workspace / "pnpm-lock.yaml").write_text("lockfileVersion: 9.0", encoding="utf-8")
        (workspace / "package.json").write_text(
            json.dumps({"name": "root", "dependencies": {"@angular/core": "^21.0.0"}}),
            encoding="utf-8",
        )
        (accented / "project.json").write_text(
            json.dumps({
                "name": "cafe",
                "projectType": "application",
                "targets": {"build": {"executor": "@angular/build:application"}},
            }),
            encoding="utf-8",
        )
        detection = detect_stack(str(workspace))
        proposed = propose_wopr_yml(detection, "apps/café")
        parsed = yaml.safe_load(proposed)
        assert parsed["project"]["slug"] == "cafe"

    def test_pom_with_empty_groupid_and_artifactid_elements(self, workspace: Path):
        """`<groupId></groupId>` parses but is empty text. Treat empty as
        missing rather than emitting `""` as the base_package."""
        (workspace / "pom.xml").write_text(
            """
<project>
  <modelVersion>4.0.0</modelVersion>
  <groupId></groupId>
  <artifactId>  </artifactId>
  <version>1.0.0</version>
  <dependencies>
    <dependency>
      <groupId>org.springframework.boot</groupId>
      <artifactId>spring-boot-starter-web</artifactId>
    </dependency>
  </dependencies>
</project>
            """.strip(),
            encoding="utf-8",
        )
        detection = detect_stack(str(workspace))
        proposed = propose_wopr_yml(detection, ".")
        # No real coords + no Java sources to fall back to => base_package
        # surfaces a TODO instead of an empty string.
        base_line = next(
            line for line in proposed.splitlines() if "base_package" in line
        )
        assert "TODO" in base_line
        assert "base_package:  " not in proposed  # no empty value emitted

    def test_npm_version_with_garbage_prefix(
        self, workspace: Path, monkeypatch: pytest.MonkeyPatch
    ):
        """A devDependency value like `github:foo/bar#v1.2.3` must not be
        mangled by character-set lstripping. The version regex pulls the
        first version-shaped token cleanly."""
        (workspace / "nx.json").write_text("{}", encoding="utf-8")
        (workspace / "package.json").write_text(
            json.dumps({
                "name": "root",
                "dependencies": {"@angular/core": "^21.0.0"},
                "devDependencies": {
                    "@openapitools/openapi-generator-cli": "github:foo/bar#v1.2.3",
                },
            }),
            encoding="utf-8",
        )
        apps = workspace / "apps"
        apps.mkdir()
        app = apps / "consumer"
        app.mkdir()
        (app / "project.json").write_text(
            json.dumps({
                "name": "consumer",
                "projectType": "application",
                "targets": {"build": {"executor": "@angular/build:application"}},
            }),
            encoding="utf-8",
        )
        # Mark this profile as a consumer so the openapi block emits.
        detection_raw = detect_stack(str(workspace))
        detection = json.loads(detection_raw)
        consumer_profile = next(
            t for t in detection["targets"] if t["target_path"] == "apps/consumer"
        )
        consumer_profile["openapi_role"] = "consumer"
        proposed = propose_wopr_yml(json.dumps(detection), "apps/consumer")
        parsed = yaml.safe_load(proposed)
        # The version regex should pull `1.2.3` out of the github specifier
        # cleanly. Pin the exact output so future regex regressions do not
        # silently slip through (`openapi-generator-cli v1.2.3` or
        # `openapi-generator-cli 1.2.3-alpha` would have passed the
        # earlier `"1.2.3" in ...` assertion).
        assert (
            parsed["openapi"]["pinned_generator_version"]
            == "openapi-generator-cli 1.2.3"
        )

    def test_consumer_with_non_dict_package_json_emits_todo(self, workspace: Path):
        """Regression: a package.json that parses to a non-dict value
        (null, a JSON array, a scalar) must not raise AttributeError on
        `data.get(...)`. The function falls through to the TODO version
        marker so the proposer still produces a valid YAML document."""
        (workspace / "nx.json").write_text("{}", encoding="utf-8")
        # Valid JSON, invalid package.json shape.
        (workspace / "package.json").write_text("null", encoding="utf-8")
        apps = workspace / "apps"
        apps.mkdir()
        app = apps / "consumer"
        app.mkdir()
        (app / "project.json").write_text(
            json.dumps({
                "name": "consumer",
                "projectType": "application",
                "targets": {"build": {"executor": "@angular/build:application"}},
            }),
            encoding="utf-8",
        )
        # Force the profile to consumer role so the openapi block emits
        # (the detector would not set it without devDeps).
        detection = json.loads(detect_stack(str(workspace)))
        consumer = next(
            t for t in detection["targets"] if t["target_path"] == "apps/consumer"
        )
        consumer["openapi_role"] = "consumer"
        proposed = propose_wopr_yml(json.dumps(detection), "apps/consumer")
        # No crash. The version falls through to the TODO marker.
        assert proposed.startswith("# wopr.yml generated")
        parsed = yaml.safe_load(proposed)
        assert (
            parsed["openapi"]["pinned_generator_version"]
            == "openapi-generator-cli TODO"
        )

    def test_requirements_section_emitted_with_local_default(
        self, workspace: Path
    ):
        """Every proposed wopr.yml includes a `requirements:` section
        with `source: local` and a `local.path: requirements` default
        so the orchestrator has a deterministic place to read REQ
        bodies from on the first crew run.
        """
        _write_spring_boot(workspace)
        detection = detect_stack(str(workspace))
        proposed = propose_wopr_yml(detection, ".")
        parsed = yaml.safe_load(proposed)
        assert "requirements" in parsed
        assert parsed["requirements"]["source"] == "local"
        assert parsed["requirements"]["local"]["path"] == "requirements"

    def test_requirements_section_documents_jira_alternative(
        self, workspace: Path
    ):
        """The proposed YAML includes commented-out lines showing how
        to swap `local:` for `jira:`. Operators on a Jira-backed
        workflow uncomment and fill in `project_key`. The cloud_id is
        intentionally absent: the Atlassian site is resolved at
        runtime by the orchestrator via the MCP, not stored in the
        project's `wopr.yml`.
        """
        _write_spring_boot(workspace)
        detection = detect_stack(str(workspace))
        proposed = propose_wopr_yml(detection, ".")
        assert "jira:" in proposed
        assert "project_key:" in proposed
        assert "cloud_id" not in proposed, (
            "cloud_id must not appear in the proposed yml; "
            "the orchestrator resolves it from the MCP at runtime"
        )

    def test_requirements_section_round_trips_with_other_sections(
        self, workspace: Path
    ):
        """Adding the requirements block must not break the YAML
        parser for any of the surrounding sections.
        """
        _write_spring_boot(workspace)
        detection = detect_stack(str(workspace))
        proposed = propose_wopr_yml(detection, ".")
        parsed = yaml.safe_load(proposed)
        # All four top-level sections still present and parseable.
        assert "project" in parsed
        assert "specs" in parsed
        assert "openapi" in parsed
        assert "requirements" in parsed

    def test_legacy_migration_block_omitted_by_default(self, workspace: Path):
        _write_angular_nx_app(workspace)
        detection = detect_stack(str(workspace))
        proposed = propose_wopr_yml(detection, "apps/example-app")
        parsed = yaml.safe_load(proposed)
        assert "legacy-migration" not in parsed


class TestWriteWoprYml:
    def test_writes_file_when_dir_exists(self, workspace: Path):
        result = write_wopr_yml(str(workspace), "project:\n  slug: test\n")
        assert result.startswith("Wrote")
        assert (workspace / "wopr.yml").is_file()
        assert (workspace / "wopr.yml").read_text(encoding="utf-8").startswith("project:")

    def test_refuses_to_overwrite_by_default(self, workspace: Path):
        (workspace / "wopr.yml").write_text("existing: true\n", encoding="utf-8")
        result = write_wopr_yml(str(workspace), "project:\n  slug: test\n")
        assert result.startswith("Error")
        # Existing file untouched.
        assert (workspace / "wopr.yml").read_text(encoding="utf-8") == "existing: true\n"

    def test_overwrites_when_explicitly_allowed(self, workspace: Path):
        (workspace / "wopr.yml").write_text("existing: true\n", encoding="utf-8")
        result = write_wopr_yml(
            str(workspace), "project:\n  slug: test\n", overwrite=True
        )
        assert result.startswith("Wrote")
        assert (workspace / "wopr.yml").read_text(encoding="utf-8").startswith("project:")

    def test_refuses_when_target_dir_missing(self, workspace: Path):
        result = write_wopr_yml(str(workspace / "apps/nonexistent"), "project:\n  slug: test\n")
        assert result.startswith("Error")
        # Did not create the parent dir.
        assert not (workspace / "apps").exists()

    def test_rejects_relative_target_dir(self, workspace: Path):
        """The caller passes an absolute path; the function does not
        join onto any pinned workspace. A relative path is a contract
        violation rather than a path resolved against a default."""
        result = write_wopr_yml("apps/example-app", "project:\n  slug: x\n")
        assert result.startswith("Error")
        assert "not absolute" in result

    def test_rejects_empty_target_dir(self):
        """Empty target_dir is a contract violation surfaced as an
        explicit error rather than a silent fallback to anything."""
        result = write_wopr_yml("", "project:\n  slug: x\n")
        assert result.startswith("Error")
        assert "required" in result.lower()

    def test_refuses_when_target_is_file_not_dir(self, workspace: Path):
        (workspace / "afile").write_text("x", encoding="utf-8")
        result = write_wopr_yml(str(workspace / "afile"), "project:\n  slug: test\n")
        assert result.startswith("Error")

    def test_rejects_invalid_yaml(self, workspace: Path):
        result = write_wopr_yml(str(workspace), "not: valid: yaml: : :\n")
        assert result.startswith("Error")
        assert not (workspace / "wopr.yml").exists()

    def test_rejects_empty_yaml(self, workspace: Path):
        """Empty string parses through safe_load as None. Reject it."""
        result = write_wopr_yml(str(workspace), "")
        assert result.startswith("Error")
        assert not (workspace / "wopr.yml").exists()

    def test_rejects_scalar_yaml(self, workspace: Path):
        """`"x"` is technically valid YAML (a bare string). Not a wopr.yml."""
        result = write_wopr_yml(str(workspace), "x\n")
        assert result.startswith("Error")
        assert "mapping" in result.lower() or "must be" in result.lower()
        assert not (workspace / "wopr.yml").exists()

    def test_rejects_list_yaml(self, workspace: Path):
        """A YAML list is valid YAML but not a wopr.yml document."""
        result = write_wopr_yml(str(workspace), "- a\n- b\n")
        assert result.startswith("Error")
        assert not (workspace / "wopr.yml").exists()

    def test_rejects_dict_without_project_block(self, workspace: Path):
        """Top-level mapping is required to declare the `project` block."""
        result = write_wopr_yml(str(workspace), "specs:\n  coder_spec: foo\n")
        assert result.startswith("Error")
        assert "project" in result.lower()
        assert not (workspace / "wopr.yml").exists()

    def test_writes_into_subdir(self, workspace: Path):
        sub = workspace / "apps" / "example-app"
        sub.mkdir(parents=True)
        result = write_wopr_yml(
            str(workspace / "apps/example-app"),
            "project:\n  slug: example-app\n",
        )
        assert result.startswith("Wrote")
        assert (sub / "wopr.yml").is_file()

    def test_overwrite_failure_preserves_original_and_cleans_temp(
        self, workspace: Path, monkeypatch: pytest.MonkeyPatch
    ):
        """If os.replace raises mid-overwrite, the original wopr.yml must
        survive untouched and the staging temp file must not linger.
        Verifies the temp file genuinely existed at the moment of
        failure so a future refactor cannot satisfy this test vacuously."""
        original = "project:\n  slug: original\n"
        (workspace / "wopr.yml").write_text(original, encoding="utf-8")

        observed_temps: list[Path] = []

        def _raise(*_args, **_kwargs):
            # Snapshot the workspace before the cleanup runs, so the
            # assertion can prove a temp file was actually staged.
            observed_temps.extend(
                p for p in workspace.iterdir()
                if p.name.startswith(".wopr.yml") and p.name.endswith(".tmp")
            )
            raise OSError("simulated rename failure")

        # os.replace lives in the shared _atomic_write helper since
        # DEMO-123 extracted the atomic-write pattern. Patch it there.
        monkeypatch.setattr(_atomic_write.os, "replace", _raise)

        result = write_wopr_yml(
            str(workspace), "project:\n  slug: replacement\n", overwrite=True
        )
        assert result.startswith("Error")
        # The temp file must have existed at the moment os.replace fired.
        assert observed_temps, "expected a staging temp file before os.replace"
        # The original is untouched.
        assert (workspace / "wopr.yml").read_text(encoding="utf-8") == original
        # No stray temp files left behind for the operator to clean up.
        leftover_temps = [
            p.name for p in workspace.iterdir()
            if p.name.startswith(".wopr.yml") and p.name.endswith(".tmp")
        ]
        assert leftover_temps == []

    def test_accepts_yaml_with_utf8_bom(self, workspace: Path):
        """UTF-8 BOM at the start of yaml_content is harmless and should
        round-trip through safe_load (PyYAML strips it). The file lands
        on disk with the BOM preserved; downstream YAML readers tolerate
        it. The BOM is spelled `"\\ufeff"` rather than embedded as a
        literal character so editors that strip BOMs on save cannot
        silently corrupt the test."""
        bom = "\ufeff"
        content = bom + "project:\n  slug: bom\n"
        result = write_wopr_yml(str(workspace), content)
        assert result.startswith("Wrote")
        written = (workspace / "wopr.yml").read_text(encoding="utf-8")
        assert written.startswith(bom)
        parsed = yaml.safe_load(written)
        assert parsed["project"]["slug"] == "bom"

    def test_rejects_yaml_with_embedded_null_bytes(self, workspace: Path):
        """NUL bytes do not belong in a wopr.yml. The function rejects
        them explicitly via a `"\\x00" in yaml_content` check before
        the parse, so the rejection is part of this function's contract
        and not dependent on PyYAML's grammar quirks (NUL is rejected
        in plain scalars but accepted in some quoted contexts)."""
        # NUL inside a plain scalar; PyYAML would reject anyway.
        result = write_wopr_yml(str(workspace), "project:\n  slug: te\x00st\n")
        assert result.startswith("Error")
        assert "NUL" in result
        assert not (workspace / "wopr.yml").exists()

    def test_rejects_yaml_with_null_byte_in_quoted_value(self, workspace: Path):
        """Defense-in-depth check: PyYAML accepts NUL inside a double-
        quoted scalar. Our explicit NUL gate rejects it regardless of
        whether PyYAML's grammar would let it through."""
        # NUL inside a double-quoted value; PyYAML accepts this.
        result = write_wopr_yml(str(workspace), 'project:\n  slug: "te\x00st"\n')
        assert result.startswith("Error")
        assert "NUL" in result
        assert not (workspace / "wopr.yml").exists()

    def test_rejects_proposer_error_string(self, workspace: Path):
        """If the operator pastes the proposer's `Error: ...` output
        into write, surface a targeted message rather than the YAML
        parser's complaint about a stray colon."""
        result = write_wopr_yml(
            str(workspace),
            "Error: target_path 'apps/nope' not found in detection.",
        )
        assert result.startswith("Error")
        assert "propose_wopr_yml error" in result
        assert not (workspace / "wopr.yml").exists()


class TestPropose_to_WriteRoundTrip:
    """Operator-flow check: propose, then write the proposed string."""

    def test_spring_boot_round_trip(self, workspace: Path):
        _write_spring_boot(workspace)
        detection = detect_stack(str(workspace))
        proposed = propose_wopr_yml(detection, ".")
        result = write_wopr_yml(str(workspace), proposed)
        assert result.startswith("Wrote")
        parsed = yaml.safe_load((workspace / "wopr.yml").read_text(encoding="utf-8"))
        assert parsed["project"]["build_file"] == "pom.xml"

    def test_angular_nx_round_trip(self, workspace: Path):
        _write_angular_nx_app(workspace)
        detection = detect_stack(str(workspace))
        proposed = propose_wopr_yml(detection, "apps/example-app")
        result = write_wopr_yml(str(workspace / "apps/example-app"), proposed)
        assert result.startswith("Wrote")
        parsed = yaml.safe_load(
            (workspace / "apps" / "example-app" / "wopr.yml").read_text(encoding="utf-8")
        )
        assert parsed["project"]["slug"] == "example-app"
        assert parsed["project"]["build_file"] == "project.json"


class TestWriteSpecStubs:
    def _angular_detection(self, workspace: Path) -> str:
        """Synthesize a detection payload for an Angular Nx app target."""
        return json.dumps({
            "workspace_path": str(workspace),
            "project_type": "monorepo",
            "monorepo_type": "nx",
            "targets": [
                {
                    "target_path": "apps/example-app",
                    "language": "typescript",
                    "framework": "angular",
                    "framework_version": "21.0.0",
                    "package_manager": "pnpm",
                    "libraries": ["ag-grid"],
                    "test_runner": "vitest",
                    "openapi_role": None,
                },
            ],
            "wopr_yml_inventory": [],
            "detected_external_signals": [],
        })

    def test_rejects_relative_target_dir(self, workspace: Path):
        result = wopr_yml.write_spec_stubs(
            "apps/example-app",
            self._angular_detection(workspace),
            "apps/example-app",
        )
        assert result.startswith("Error")
        assert "not absolute" in result

    def test_rejects_empty_target_dir(self, workspace: Path):
        result = wopr_yml.write_spec_stubs(
            "", self._angular_detection(workspace), "apps/example-app"
        )
        assert result.startswith("Error")
        assert "required" in result.lower()

    def test_writes_angular_specs_when_framework_is_angular(self, workspace: Path):
        app_dir = workspace / "apps" / "example-app"
        app_dir.mkdir(parents=True)
        result = wopr_yml.write_spec_stubs(
            str(app_dir),
            self._angular_detection(workspace),
            "apps/example-app",
        )
        assert result.startswith("Wrote")
        assert "angular" in result
        coder = (app_dir / "specs" / "coder-spec.md").read_text(encoding="utf-8")
        tester = (app_dir / "specs" / "tester-spec.md").read_text(encoding="utf-8")
        # Angular-specific content shipped, not the generic template.
        assert "Vitest" in coder or "vitest" in coder
        assert "Vitest" in tester or "vitest" in tester
        # DEMO-123 regression guard. The Angular coder-spec used to
        # claim `pnpm nx run-many --target=lint --all` performed
        # type-checking. It does not. The default `@nx/eslint:lint`
        # executor runs ESLint, not tsc. The row was dropped because
        # the existing build rows already cover type-checking
        # (`pnpm nx build <app>` invokes tsc via @angular/build).
        assert "Type-check only" not in coder, (
            "Angular coder-spec must not carry the DEMO-123 type-check "
            "row. The 'Nx's lint includes tsc' claim was factually wrong."
        )
        assert "Nx's lint includes tsc" not in coder

    def test_writes_spring_boot_specs_when_framework_matches(self, workspace: Path):
        detection = json.dumps({
            "workspace_path": str(workspace),
            "project_type": "single-app",
            "monorepo_type": None,
            "targets": [{
                "target_path": ".",
                "language": "java",
                "framework": "spring-boot",
                "framework_version": "21",
                "package_manager": "maven",
                "libraries": [],
                "test_runner": None,
                "openapi_role": "producer",
            }],
            "wopr_yml_inventory": [],
            "detected_external_signals": [],
        })
        result = wopr_yml.write_spec_stubs(str(workspace), detection, ".")
        assert result.startswith("Wrote")
        assert "spring-boot" in result
        coder = (workspace / "specs" / "coder-spec.md").read_text(encoding="utf-8")
        # Spring-Boot-specific content shipped.
        assert "Maven" in coder or "mvn" in coder
        assert "Spring Boot" in coder

    def test_falls_back_to_generic_for_unknown_stack(self, workspace: Path):
        detection = json.dumps({
            "workspace_path": str(workspace),
            "project_type": "single-app",
            "monorepo_type": None,
            "targets": [{
                "target_path": ".",
                "language": "rust",
                "framework": None,
                "framework_version": None,
                "package_manager": "cargo",
                "libraries": [],
                "test_runner": None,
                "openapi_role": None,
            }],
            "wopr_yml_inventory": [],
            "detected_external_signals": [],
        })
        result = wopr_yml.write_spec_stubs(str(workspace), detection, ".")
        assert result.startswith("Wrote")
        assert "generic" in result
        # The generic fallback is the top-level skeleton with
        # ``[STACK: ...]`` markers, landed under the canonical name.
        coder = (workspace / "specs" / "coder-spec.md").read_text(encoding="utf-8")
        assert "[STACK:" in coder

    def test_refuses_to_overwrite_existing_spec(self, workspace: Path):
        specs_dir = workspace / "specs"
        specs_dir.mkdir()
        (specs_dir / "coder-spec.md").write_text("custom content", encoding="utf-8")
        result = wopr_yml.write_spec_stubs(
            str(workspace), self._angular_detection(workspace), "apps/example-app"
        )
        # The propose targets apps/example-app so the angular fallback
        # would pick angular; but the target_dir is the workspace
        # itself, so coder-spec.md already exists.
        assert result.startswith("Error")
        assert "already exists" in result
        # Existing content untouched.
        assert (specs_dir / "coder-spec.md").read_text(encoding="utf-8") == "custom content"

    def test_overwrite_true_replaces_specs(self, workspace: Path):
        specs_dir = workspace / "specs"
        specs_dir.mkdir()
        sentinel = "UNIQUE_TEST_SENTINEL_E3X4Z9"
        (specs_dir / "coder-spec.md").write_text(sentinel, encoding="utf-8")
        (specs_dir / "tester-spec.md").write_text(sentinel, encoding="utf-8")
        result = wopr_yml.write_spec_stubs(
            str(workspace),
            self._angular_detection(workspace),
            "apps/example-app",
            overwrite=True,
        )
        assert result.startswith("Wrote")
        new_coder = (specs_dir / "coder-spec.md").read_text(encoding="utf-8")
        assert sentinel not in new_coder
        assert "Angular" in new_coder


class TestStubWriters:
    """The two DEMO-123 stub writers that drop pack-shipped
    templates into a project at init time so role agents never have
    to filesystem-search for them. Each writer reads the project's
    ``wopr.yml`` to honor an operator-declared destination path and
    falls back to a sensible default.
    """

    # ------------------------------------------------------------------
    # write_tracking_doc_stub
    # ------------------------------------------------------------------

    def test_tracking_doc_stub_uses_default_when_yml_omits_path(self, workspace: Path):
        """No declared ``legacy-migration.tracking_doc`` -> default
        filename at the target root."""
        (workspace / "wopr.yml").write_text(
            "project:\n  slug: api\n", encoding="utf-8"
        )
        result = wopr_yml.write_tracking_doc_stub(str(workspace))
        assert result.startswith("Wrote")
        dest = workspace / "implementation-tracking.md"
        assert dest.is_file()
        assert "Implementation Tracking" in dest.read_text(encoding="utf-8")

    def test_tracking_doc_stub_honors_yml_declared_path(self, workspace: Path):
        """Operator-declared ``tracking_doc`` lands at the declared
        path. One migration project used ``CURRENT_REQUIREMENTS.md`` as its
        tracking doc filename; pin that this works."""
        (workspace / "wopr.yml").write_text(
            "project:\n  slug: example\n"
            "legacy-migration:\n"
            "  tracking_doc: CURRENT_REQUIREMENTS.md\n",
            encoding="utf-8",
        )
        result = wopr_yml.write_tracking_doc_stub(str(workspace))
        assert result.startswith("Wrote")
        assert (workspace / "CURRENT_REQUIREMENTS.md").is_file()
        assert not (workspace / "implementation-tracking.md").exists(), (
            "default should NOT be created when the yml declares a path"
        )

    def test_tracking_doc_stub_refuses_to_overwrite_by_default(
        self, workspace: Path
    ):
        (workspace / "wopr.yml").write_text(
            "project:\n  slug: api\n", encoding="utf-8"
        )
        (workspace / "implementation-tracking.md").write_text(
            "pre-existing content", encoding="utf-8"
        )
        result = wopr_yml.write_tracking_doc_stub(str(workspace))
        assert result.startswith("Error")
        assert "already exists" in result
        assert (workspace / "implementation-tracking.md").read_text(
            encoding="utf-8"
        ) == "pre-existing content"

    def test_tracking_doc_stub_overwrite_true_replaces(self, workspace: Path):
        (workspace / "wopr.yml").write_text(
            "project:\n  slug: api\n", encoding="utf-8"
        )
        (workspace / "implementation-tracking.md").write_text("old", encoding="utf-8")
        result = wopr_yml.write_tracking_doc_stub(str(workspace), overwrite=True)
        assert result.startswith("Wrote")
        new_content = (workspace / "implementation-tracking.md").read_text(
            encoding="utf-8"
        )
        assert "old" not in new_content
        assert "Implementation Tracking" in new_content

    def test_tracking_doc_stub_requires_wopr_yml(self, workspace: Path):
        """Init flow guarantees wopr.yml exists before the stub
        writers are called; if missing, fail loudly rather than write
        with default-everything assumptions."""
        result = wopr_yml.write_tracking_doc_stub(str(workspace))
        assert result.startswith("Error")
        assert "wopr.yml not found" in result

    def test_tracking_doc_stub_rejects_relative_target_dir(self):
        result = wopr_yml.write_tracking_doc_stub("relative/path")
        assert result.startswith("Error")
        assert "not absolute" in result

    # ------------------------------------------------------------------
    # write_handoff_contract_stub
    # ------------------------------------------------------------------

    def test_handoff_contract_stub_default_path(self, workspace: Path):
        (workspace / "wopr.yml").write_text(
            "project:\n  slug: api\n", encoding="utf-8"
        )
        result = wopr_yml.write_handoff_contract_stub(str(workspace))
        assert result.startswith("Wrote")
        assert (workspace / "frontend-handoff-contract.md").is_file()

    def test_handoff_contract_stub_honors_yml_path(self, workspace: Path):
        (workspace / "wopr.yml").write_text(
            "project:\n  slug: api\n"
            "legacy-migration:\n"
            "  handoff_contract: docs/handoff.md\n",
            encoding="utf-8",
        )
        result = wopr_yml.write_handoff_contract_stub(str(workspace))
        assert result.startswith("Wrote")
        # Subdirs auto-created.
        assert (workspace / "docs" / "handoff.md").is_file()

class TestRegister:
    def test_register_registers_expected_tools(self, fake_mcp):
        wopr_yml.register(fake_mcp)
        # Stub writers live in tools.stub_writers.
        assert sorted(fake_mcp.registered) == [
            "propose_wopr_yml",
            "write_spec_stubs",
            "write_wopr_yml",
        ]

    def test_stub_writers_register_registers_expected_tools(self, fake_mcp):
        from wopr.tools import stub_writers

        stub_writers.register(fake_mcp)
        # ``write_extracted_requirements_stub`` landed the
        # legacy-migration pack's template; neither crosses over.
        assert sorted(fake_mcp.registered) == [
            "write_handoff_contract_stub",
            "write_tracking_doc_stub",
        ]
