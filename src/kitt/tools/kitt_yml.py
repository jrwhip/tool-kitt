"""KITT `kitt.yml` generator.

Two MCP tools that turn a ``detect_stack`` result into a scaffolded
``kitt.yml`` for a specific target inside the workspace:

- ``propose_kitt_yml(detection_json, target_path)``: read-only. Returns
  the proposed YAML as a string. Operator confirms before any file
  lands on disk. ``target_path`` is relative to the workspace inside
  the detection.
- ``write_kitt_yml(target_dir, yaml_content, overwrite=False)``: writes
  the YAML to ``<target_dir>/kitt.yml``. ``target_dir`` is an absolute
  path resolved by the caller from the operator's working context.
  Refuses to overwrite existing files unless explicitly told to.
  Refuses to create parent directories; the caller decides whether the
  placement is real.

The skill ``/kitt-create-yml`` orchestrates: detect -> propose -> show
operator -> confirm -> write. The tools themselves are non-interactive.
"""

from __future__ import annotations

import json
import logging
import re
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import TYPE_CHECKING, Any, NamedTuple

import yaml

from .._atomic_write import atomic_create_text, atomic_write_text
from ..product import LOGGER_NAME
from ._data_paths import candidate_data_paths
from ._errors import ERROR_PREFIX
from ._kitt_yml_kind import (
    KIND_INVALID,
    KIND_WORKSPACE,
    classify_kitt_yml_data,
    kitt_yml_kind,
)
from ._target_paths import (
    find_profile as _find_profile,
)
from ._target_paths import (
    name_from_slug as _name_from_slug,
)
from ._target_paths import (
    normalize_target_path as _normalize_target_path,
)
from ._target_paths import (
    slug_from_target as _slug_from_target,
)

logger = logging.getLogger(LOGGER_NAME)

# Trust assumption: the pom.xml files this tool parses live inside the
# operator's own workspace. They are not adversarial input. If this
# tool is ever extended to scan arbitrary remote workspaces, replace
# the stdlib ``xml.etree.ElementTree`` parser below with
# ``defusedxml.ElementTree`` to neutralize billion-laughs / external-
# entity attacks.

if TYPE_CHECKING:
    from mcp.server.fastmcp import FastMCP


# -----------------------------------------------------------------------------
# Helpers: target resolution
# -----------------------------------------------------------------------------
#
# normalize_target_path / find_profile / slug_from_target / name_from_slug
# live in ``_target_paths`` so claude_md.py uses the same implementation.
# Imported at module top with private aliases (leading underscore) so
# call sites here keep the existing names.


def _resolve_target_dir(workspace_path: str, target_path: str) -> Path:
    """Return the absolute path to the target directory inside the workspace."""
    norm = _normalize_target_path(target_path)
    workspace = Path(workspace_path)
    return workspace if norm == "." else workspace / norm


def _localname(tag: str) -> str:
    """Strip the XML namespace prefix from an ElementTree tag.

    Maven pom files routinely carry an ``xmlns`` declaration; ElementTree
    prefixes every parsed tag with ``{namespace}localname``. We only
    care about the localname.
    """
    return tag.split("}", 1)[1] if tag.startswith("{") else tag


def _read_pom_groupid_artifactid(target_dir: Path) -> tuple[str | None, str | None]:
    """Return (groupId, artifactId) for the project, NOT its parent POM.

    Reads only direct children of the ``<project>`` root. This is
    structurally immune to the family of bugs that plagued the earlier
    regex implementation:

    - ``<parent>`` block (which carries the upstream POM's coordinates)
      is not a direct child match for groupId/artifactId; it owns its
      own subtree.
    - ``<dependencyManagement>`` and ``<dependencies>`` blocks routinely
      list groupId/artifactId for dependencies before the project
      declares its own coordinates. Direct-child filtering ignores them.
    - ``<profiles>``/``<profile>`` blocks may redeclare coordinates for
      profile-scoped overrides. Same filtering applies.
    - XML namespaces (``<pom:groupId>``) are normalized via
      :func:`_localname` so the tag check survives namespaced poms.

    A malformed or unreadable pom returns ``(None, None)`` quietly; the
    caller layers TODO comments on missing fields.
    """
    pom = target_dir / "pom.xml"
    if not pom.is_file():
        return None, None
    try:
        # ``with`` ensures the file handle closes even when ET.parse
        # raises mid-parse, where stdlib cleanup is implementation-
        # defined and historically has leaked the handle.
        with pom.open("rb") as fh:
            root = ET.parse(fh).getroot()
    except (OSError, ET.ParseError) as e:
        # Operator-visible failure mode: base_package falls back to TODO
        # because the pom did not parse. Log so a curious operator can
        # follow up; do not raise.
        logger.warning("doctor: failed to parse %s: %s", pom, e)
        return None, None
    group: str | None = None
    artifact: str | None = None
    for child in root:
        local = _localname(child.tag)
        if local == "groupId" and child.text:
            group = child.text.strip() or None
        elif local == "artifactId" and child.text:
            artifact = child.text.strip() or None
    return group, artifact


def _derive_java_base_package(target_dir: Path) -> tuple[str | None, bool]:
    """Best-effort derivation of the project's base Java package.

    Strategy, in order:

    1. ``<groupId>.<artifactId>`` from pom.xml when both are present.
    2. ``<groupId>`` alone when artifactId could not be recovered (the
       group is still usually a meaningful package root, and the
       operator can refine it).
    3. The ``package`` declaration of the first ``.java`` file under
       ``src/main/java`` when neither groupId nor artifactId could be
       read from the pom.

    Returns:
        ``(package, transform_applied)``. ``transform_applied`` is True
        when the artifactId contained hyphens and had to be folded to
        underscores to form a valid Java identifier. The caller should
        surface a TODO comment in that case so the operator confirms
        the guess.
    """
    group, artifact = _read_pom_groupid_artifactid(target_dir)
    if group and artifact:
        # Common pattern in KITT-adjacent projects: groupId already includes
        # the project segment. Concatenate only when artifactId does not
        # collide with the groupId's trailing segment.
        if group.endswith(artifact):
            return group, False
        had_hyphen = "-" in artifact
        return f"{group}.{artifact.replace('-', '_')}", had_hyphen
    if group:
        return group, False

    java_root = target_dir / "src" / "main" / "java"
    if java_root.is_dir():
        # ``rglob`` order is unspecified across platforms and
        # filesystems; sort so the first-match-wins behavior is
        # reproducible across machines (otherwise the same project can
        # produce different base_package values on different CI agents).
        # Continue past files without a package declaration (default
        # package, comment-only files, files we cannot decode as UTF-8);
        # each candidate read is bounded to 4 KiB and uses
        # ``errors="replace"`` so a UTF-16 or otherwise non-UTF-8 Java
        # source does not raise mid-scan. The replacement characters
        # break the package-line regex, which is the right fail-quiet
        # behavior: that file gets skipped and the next candidate wins,
        # falling through to a TODO if no decodable file declares a
        # package.
        for java_file in sorted(java_root.rglob("*.java")):
            try:
                head = java_file.read_text(encoding="utf-8", errors="replace")[:4096]
            except OSError:
                continue
            m = re.search(r"^package\s+([\w\.]+)\s*;", head, re.MULTILINE)
            if m:
                return m.group(1), False
    return None, False


def _derive_target_source_root(profile: dict[str, Any], base_package: str | None) -> str:
    """Convention-driven source-root path relative to kitt.yml location."""
    language = profile.get("language")
    framework = profile.get("framework")
    package_manager = profile.get("package_manager")

    if language == "java":
        if base_package:
            return f"src/main/java/{base_package.replace('.', '/')}"
        return "src/main/java"
    if framework == "angular":
        return "src/app"
    if framework in {"react", "vue", "next"} or language in {"typescript", "javascript"}:
        return "src"
    if language == "python":
        return "src"
    if language == "rust":
        return "src"
    if language == "go":
        return "."
    if language == "csharp":
        return "."
    # Fallback when nothing matched but we still have a build file.
    if package_manager == "maven":
        return "src/main/java"
    return "src"


def _derive_test_root(profile: dict[str, Any]) -> str:
    language = profile.get("language")
    test_runner = profile.get("test_runner")
    if language == "java":
        return "src/test/java"
    if test_runner in {"vitest", "jest", "playwright"}:
        # Frontend test files commonly co-locate next to sources; this is
        # the most generic safe choice that still resolves on a search.
        return "src"
    if language == "python":
        return "tests"
    if language == "rust":
        return "tests"
    if language == "go":
        return "."
    return "src"


def _derive_build_file(profile: dict[str, Any], target_dir: Path) -> str:
    """Return the build-file path. Prefer the profile, then disk evidence."""
    package_manager = profile.get("package_manager")
    if package_manager == "maven" and (target_dir / "pom.xml").is_file():
        return "pom.xml"
    if package_manager == "gradle":
        if (target_dir / "build.gradle.kts").is_file():
            return "build.gradle.kts"
        if (target_dir / "build.gradle").is_file():
            return "build.gradle"
    if (target_dir / "project.json").is_file():
        return "project.json"
    if (target_dir / "package.json").is_file():
        return "package.json"
    if (target_dir / "pyproject.toml").is_file():
        return "pyproject.toml"
    if (target_dir / "Cargo.toml").is_file():
        return "Cargo.toml"
    if (target_dir / "go.mod").is_file():
        return "go.mod"
    # Fallback to a string that signals to the operator something is off.
    return "TODO"


def _derive_api_contract_section(
    profile: dict[str, Any], workspace_path: str
) -> tuple[str | None, str | None, str | None]:
    """Return (spec_url, pinned_generator_version, todo_comment) for `api_contract`.

    Detection only recognises OpenAPI producers (springdoc) and consumers
    (openapi-generator-cli), so every derived block is ``kind: openapi``.
    GraphQL projects declare the block by hand; see kitt-yml-schema.md.
    The todo_comment is set when the field needs human review.
    """
    role = profile.get("openapi_role")
    if role == "producer":
        return (
            "/v3/api-docs",
            "springdoc-openapi 2.7.0",
            "Confirm `springdoc-openapi` version matches `pom.xml` or `build.gradle`.",
        )
    if role == "consumer":
        # Read the workspace-root package.json devDependencies to pin
        # the generator version. This is intentional for Nx-style
        # monorepos, where each app's project.json inherits deps from
        # the workspace root. A future maintainer working on a non-Nx
        # layout might "fix" this by joining the target_path; don't.
        # The detector classifies non-Nx targets via per-app
        # package.json and the workspace-root profile separately, so
        # the right `workspace_path` is already in hand.
        pkg = Path(workspace_path) / "package.json"
        version: str | None = None
        try:
            data = json.loads(pkg.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            data = None
        # ``json.loads`` returns whatever the JSON document evaluates to,
        # which includes ``null``, lists, scalars. A misconfigured
        # ``package.json`` at root could be any of those. Guard the dict
        # assumption rather than rely on ``data.get`` to raise, which
        # would surface as an AttributeError mid-propose.
        if isinstance(data, dict):
            dev = data.get("devDependencies") or {}
            if isinstance(dev, dict):
                raw = dev.get("@openapitools/openapi-generator-cli")
                if isinstance(raw, str):
                    # Extract the first version-shaped token rather
                    # than ``lstrip``-ing characters, which silently
                    # mangles specifiers like ``github:foo/bar#v1.2.3``.
                    # Use search (not match) so prefixes from non-
                    # standard specifiers are skipped over rather than
                    # blocking the parse.
                    m = re.search(r"\d+(?:\.\d+){1,2}[\w\.\-]*", raw)
                    if m:
                        version = m.group(0) or None
        pinned = (
            f"openapi-generator-cli {version}"
            if version
            else "openapi-generator-cli TODO"
        )
        # spec_url is emitted as ``null`` rather than a TODO string. A
        # YAML value containing a literal ``TODO:`` is invalid because the
        # second colon starts a nested mapping. Use null + a TODO comment.
        todo = (
            "Set `spec_url` to the backend's openapi.json path or URL. "
            "Pin must match the backend's `spec_version`."
        )
        return None, pinned, todo
    return None, None, None


# -----------------------------------------------------------------------------
# Public: propose_kitt_yml
# -----------------------------------------------------------------------------


_BACKEND_FRAMEWORKS = frozenset({"spring-boot", "fastapi", "flask", "django"})
_FRONTEND_FRAMEWORKS = frozenset({"angular", "react", "vue", "next"})

_ROLE_TODO = "could not infer; set one of backend | frontend | tests | other."

# Directory names that mean "test suite" on their own, for a member no
# stack detector recognizes (a repo of Playwright specs and shell
# scripts has no build file to classify).
_TEST_SUITE_DIRNAMES = frozenset({"tests", "test", "e2e", "qa", "acceptance"})


def _infer_member_role(profile: dict[str, Any]) -> tuple[str, str | None]:
    """Guess a workspace member's role from its stack profile.

    Returns ``(role, todo)``; ``todo`` is set when the guess is the
    ``other`` fallback and the operator has to decide. The API-contract
    role is the strongest signal (a producer IS the backend, a consumer
    IS the frontend); the framework family comes next; a directory with
    a test runner and no framework is a test suite, and so is an
    unrecognized directory whose name says so (``tests/``, ``e2e/``).
    """
    contract_role = profile.get("openapi_role")
    if contract_role == "producer":
        return "backend", None
    if contract_role == "consumer":
        return "frontend", None
    framework = profile.get("framework")
    if framework in _BACKEND_FRAMEWORKS:
        return "backend", None
    if framework in _FRONTEND_FRAMEWORKS:
        return "frontend", None
    if profile.get("test_runner") and not framework:
        return "tests", None
    basename = Path(_normalize_target_path(str(profile.get("target_path") or ""))).name
    if not framework and basename.lower() in _TEST_SUITE_DIRNAMES:
        return "tests", None
    return "other", _ROLE_TODO


_PLAIN_SCALAR = re.compile(r"[A-Za-z0-9_./-][A-Za-z0-9_./ -]*")


def _yaml_scalar(value: str) -> str:
    """Emit ``value`` as a YAML scalar, quoting it when it needs quoting.

    Member paths and names come from directory names and operator
    edits. A colon or a leading special character would turn the line
    into a nested mapping or a parse error, and a directory named
    ``2024``, ``true``, ``no`` or ``null`` would come back from the
    parser as a number, a boolean or nothing at all. The regex is only
    the fast path; PyYAML itself has the final say, by round-tripping
    the bare value and checking it comes back as the same string. JSON
    double-quoted strings are valid YAML double-quoted scalars.
    """
    if _PLAIN_SCALAR.fullmatch(value):
        try:
            if yaml.safe_load(value) == value:
                return value
        except yaml.YAMLError:
            pass
    return json.dumps(value)


class _ProposedMember(NamedTuple):
    path: str
    slug: str
    role: str
    todo: str | None


def _propose_workspace_yml(detection: dict[str, Any]) -> str:
    """The proposed root ``kitt.yml`` for a container of sibling projects.

    Called by :func:`propose_kitt_yml` when the target is ``.`` and the
    detection classified the root as a ``container`` (no root file yet)
    or a ``workspace`` (a root file already declares members). Every
    target in the detection becomes a member; declared roles and slugs
    are kept when the root file already has them, otherwise the role is
    inferred from the member's stack. Children the scan found but the
    root file omits are appended with a TODO; declared members missing
    on disk are emitted commented out so the operator sees the gap.
    """
    workspace_path = detection.get("workspace_path") or "."
    slug = _slug_from_target(".", workspace_path)
    name = _name_from_slug(slug)

    declared_roles: dict[str, str] = {}
    declared_slugs: dict[str, str] = {}
    undeclared: list[str] = []
    missing: list[str] = []
    workspace_block = detection.get("workspace")
    if isinstance(workspace_block, dict):
        if isinstance(workspace_block.get("slug"), str) and workspace_block["slug"]:
            slug = workspace_block["slug"]
            declared_name = workspace_block.get("name")
            name = declared_name if isinstance(declared_name, str) and declared_name else name
        for member in workspace_block.get("members") or []:
            if not isinstance(member, dict) or not member.get("path"):
                continue
            path = _normalize_target_path(str(member["path"]))
            if isinstance(member.get("role"), str):
                declared_roles[path] = member["role"]
            if isinstance(member.get("slug"), str):
                declared_slugs[path] = member["slug"]
        undeclared = [
            _normalize_target_path(str(child))
            for child in workspace_block.get("undeclared_children") or []
        ]
        missing = [
            _normalize_target_path(str(child))
            for child in workspace_block.get("missing_children") or []
        ]

    members: list[_ProposedMember] = []
    seen: set[str] = set()
    for profile in detection.get("targets") or []:
        if not isinstance(profile, dict) or not profile.get("target_path"):
            continue
        path = _normalize_target_path(str(profile["target_path"]))
        if path == "." or path in seen:
            continue
        seen.add(path)
        if path in declared_roles:
            role, todo = declared_roles[path], None
        else:
            role, todo = _infer_member_role(profile)
        member_slug = declared_slugs.get(path) or _slug_from_target(path, workspace_path)
        members.append(_ProposedMember(path, member_slug, role, todo))

    # A workspace file needs at least one member; the writer rejects an
    # empty list, so refuse here rather than show a preview that cannot
    # land. Missing declared members are not members on disk.
    if not members and not [path for path in undeclared if path not in seen]:
        gone = f" Declared but missing on disk: {', '.join(missing)}." if missing else ""
        return (
            f"Error: no member projects found under {workspace_path}; a workspace "
            f"kitt.yml needs at least one child directory that is a project or a git "
            f"repository.{gone}"
        )

    lines: list[str] = []
    lines.append(f"# kitt.yml generated by /kitt-create-yml for the {slug} workspace.")
    lines.append("# Schema: kitt-yml-schema.md (KITT crew pack; mcp get_pack_template)")
    lines.append(
        "# This is a WORKSPACE file: it names the sibling projects under this "
        "directory. Each member keeps its own project kitt.yml."
    )
    lines.append(
        "# Review every TODO comment; the generator guesses roles from the "
        "stack it detected and may be wrong."
    )
    lines.append("")
    lines.append("workspace:")
    lines.append(f"  slug: {_yaml_scalar(slug)}")
    lines.append(f"  name: {_yaml_scalar(name)}  # TODO: confirm the human-readable name.")
    lines.append("  projects:")
    for member in members:
        lines.append(f"    - path: {_yaml_scalar(member.path)}")
        lines.append(f"      slug: {_yaml_scalar(member.slug)}")
        role_line = f"      role: {member.role}"
        if member.todo:
            role_line += f"  # TODO: {member.todo}"
        lines.append(role_line)
    for path in undeclared:
        if path in seen:
            continue
        seen.add(path)
        lines.append(f"    - path: {_yaml_scalar(path)}")
        lines.append(f"      slug: {_yaml_scalar(_slug_from_target(path, workspace_path))}")
        lines.append(
            "      role: other  # TODO: found on disk but not declared; "
            "keep this entry or remove it."
        )
    for path in missing:
        if path in seen:
            continue
        lines.append(
            f"    # - path: {_yaml_scalar(path)}  # TODO: declared but not found on disk."
        )
    lines.append("")
    lines.append("# Optional. Semantic-search configuration for the ROOT corpus")
    lines.append("# (searches from here also read every member's LEARNINGS.md).")
    lines.append("# learnings:")
    lines.append("#   embeddings:")
    lines.append("#     provider: local  # local | bedrock | none")
    lines.append("")
    return "\n".join(lines)


def propose_kitt_yml(detection_json: str, target_path: str) -> str:
    """Generate the proposed `kitt.yml` text for a target inside a workspace.

    Args:
        detection_json: Output of ``detect_stack``. JSON string.
        target_path: Path of the target inside the workspace (``.`` for
            the workspace root, ``apps/example-app`` for an Nx app).
            When the target is ``.`` and the detection classified the
            root as a ``container`` or ``workspace``, the proposal is a
            workspace file (a ``workspace:`` block naming the child
            projects as members) rather than a project file.

    Returns:
        The proposed YAML as a string with TODO comments next to fields
        that need operator review. Returns an ``Error:`` string on
        invalid input. Read-only; no file writes.
    """
    try:
        detection = json.loads(detection_json)
    except json.JSONDecodeError as e:
        return f"Error: invalid detection JSON: {e}"
    # ``json.loads`` returns whatever the document represents, including
    # ``null``, lists, scalars. The documented contract is that callers
    # pass the output of ``detect_stack`` which is always a JSON object,
    # but a malformed caller could hand us a non-dict and ``.get`` would
    # raise AttributeError. Reject explicitly.
    if not isinstance(detection, dict):
        return (
            "Error: detection JSON must be a JSON object "
            f"(got {type(detection).__name__})."
        )
    if detection.get("error"):
        return f"Error: detection reports an error: {detection['error']}"

    # The root of a container of sibling projects gets a workspace
    # file, not a project file. Before this branch the same call
    # dead-ended with "target '.' not found", because a container
    # root is never itself a target.
    if (
        _normalize_target_path(target_path) == "."
        and detection.get("project_type") in ("container", "workspace")
    ):
        return _propose_workspace_yml(detection)

    workspace_path = detection.get("workspace_path") or "."
    profile = _find_profile(detection, target_path)
    if profile is None:
        return (
            f"Error: target_path {target_path!r} not found in detection. "
            f"Available: {[p.get('target_path') for p in detection.get('targets') or []]}"
        )

    target_dir = _resolve_target_dir(workspace_path, target_path)
    slug = _slug_from_target(target_path, workspace_path)
    name = _name_from_slug(slug)
    language = profile.get("language")
    framework = profile.get("framework")

    base_package: str | None = None
    base_package_transformed = False
    if language == "java":
        base_package, base_package_transformed = _derive_java_base_package(target_dir)
    source_root = _derive_target_source_root(profile, base_package)
    test_root = _derive_test_root(profile)
    build_file = _derive_build_file(profile, target_dir)
    spec_url, pinned_version, contract_todo = _derive_api_contract_section(
        profile, workspace_path
    )

    coder_spec_todo = "# TODO: copy from catalog/crew/templates/coder-spec.template.md"
    tester_spec_todo = "# TODO: copy from catalog/crew/templates/tester-spec.template.md"

    lines: list[str] = []
    lines.append(f"# kitt.yml generated by /kitt-create-yml for {slug}.")
    lines.append("# Schema: kitt-yml-schema.md (KITT crew pack; mcp get_pack_template)")
    lines.append(
        "# Review every TODO comment before the first crew run; the "
        "generator fills in defaults that may not match this project."
    )
    lines.append("")
    lines.append("project:")
    lines.append(f"  slug: {slug}")
    lines.append(f"  name: {name}  # TODO: confirm the human-readable name.")
    lines.append(f"  target_source_root: {source_root}")
    lines.append(f"  test_root: {test_root}")
    lines.append(f"  build_file: {build_file}")
    if base_package:
        if base_package_transformed:
            base_package_todo = (
                "# TODO: artifactId hyphens were folded to underscores; "
                "confirm the package matches your code."
            )
            lines.append(f"  base_package: {base_package}  {base_package_todo}")
        else:
            lines.append(f"  base_package: {base_package}")
    elif language == "java":
        no_pom_todo = "# could not derive; check pom.xml or first .java file."
        lines.append(f"  base_package: TODO  {no_pom_todo}")
    lines.append("")
    lines.append("specs:")
    lines.append(f"  coder_spec: specs/coder-spec.md  {coder_spec_todo}")
    lines.append(f"  tester_spec: specs/tester-spec.md  {tester_spec_todo}")
    lines.append("  audit_report: AUDIT_REPORT.md")

    if spec_url is not None or pinned_version is not None:
        lines.append("")
        lines.append("api_contract:")
        lines.append("  kind: openapi")
        # Always emit spec_url when the api_contract block exists; use
        # `null` plus a TODO comment when the value could not be derived.
        if spec_url is not None:
            lines.append(f"  spec_url: {spec_url}")
        else:
            lines.append("  spec_url: null")
        if pinned_version is not None:
            lines.append(f"  pinned_generator_version: {pinned_version}")
        if contract_todo:
            lines.append(f"  # TODO: {contract_todo}")

    # Requirements source: where the orchestrator pulls the active REQ
    # body from at crew dispatch. Default is `local` so existing
    # projects without this section keep working unchanged (the parser
    # also defaults absent sections to local). Operators on a Jira-
    # backed workflow swap the `local:` sub-block for `jira:`. The
    # Atlassian site (cloud_id) is resolved at runtime by the
    # orchestrator via the Atlassian MCP's
    # ``getAccessibleAtlassianResources`` call, not stored here; it is
    # machine-level state, not project-level.
    lines.append("")
    lines.append("requirements:")
    lines.append("  source: local  # TODO: confirm; \"local\" or \"jira\"")
    lines.append("  local:")
    lines.append(
        "    path: requirements  # directory of <REQ-ID>.md files, "
        "relative to this kitt.yml"
    )
    lines.append("  # When source: jira, replace local: above with:")
    lines.append("  #   jira:")
    lines.append("  #     project_key: <PROJECT-KEY>  # optional sanity check")

    if framework == "angular" or language == "typescript":
        lines.append("")
        lines.append(
            "# legacy-migration block intentionally omitted. Add it by hand "
            "when migrating from a legacy stack; see kitt.example.yml."
        )

    lines.append("")
    return "\n".join(lines)


# -----------------------------------------------------------------------------
# Public: write_kitt_yml
# -----------------------------------------------------------------------------


def write_kitt_yml(
    target_dir: str, yaml_content: str, overwrite: bool = False
) -> str:
    """Write ``yaml_content`` to ``<target_dir>/kitt.yml``.

    Args:
        target_dir: Absolute path of the directory where ``kitt.yml``
            should be created. Must already exist. The caller (a skill
            running in the operator's session) is responsible for
            resolving this from the operator's actual working context.
            This function does NOT join the path onto any pinned
            workspace; relying on a server-side default produced silent
            foot-guns when the MCP server's workspace and the operator's
            actual project were in different places.
        yaml_content: Final YAML to write. Validated by parsing through
            ``yaml.safe_load`` before any disk write.
        overwrite: When ``False`` (default), refuses to overwrite an
            existing ``kitt.yml``. When ``True``, replaces the file.

    Returns:
        Status string. Begins with ``Wrote`` on success or ``Error:`` on
        failure. The function never creates parent directories. The
        target directory IS the project root and must already exist;
        creating it server-side would hide the operator's misnamed
        path. Contrast with :func:`_write_pack_template` (used by the
        stub writers), which DOES create intermediate directories
        because its destination is a sub-path INSIDE the project (e.g.
        ``docs/implementation-tracking.md``) where the leaf directory
        may not yet exist by design.
    """
    if not target_dir:
        return (
            "Error: target_dir is required. Pass the absolute path of the "
            "directory where kitt.yml should be written."
        )
    dest_dir = Path(target_dir).expanduser()
    if not dest_dir.is_absolute():
        return (
            f"Error: target_dir {target_dir!r} is not absolute. Pass the "
            "fully-resolved path to the target directory."
        )
    dest_dir = dest_dir.resolve()

    if not dest_dir.exists():
        return (
            f"Error: target directory does not exist: {dest_dir}. "
            "Create it manually before running the generator."
        )
    if not dest_dir.is_dir():
        return f"Error: target path is not a directory: {dest_dir}"

    # Guard against the operator pasting a proposer error string into
    # write. ``propose_kitt_yml`` returns ``Error: ...`` on failure; if
    # that string ever gets handed to write, surface a clearer message
    # than the YAML parser's complaint about ``:`` mid-value.
    if yaml_content.lstrip().startswith(ERROR_PREFIX):
        return (
            "Error: yaml_content looks like a propose_kitt_yml error "
            "string; pass the proposed YAML, not the error message."
        )

    # Defense in depth: PyYAML currently rejects NUL in plain scalars,
    # but accepts NUL in quoted strings and some block contexts. NUL has
    # no business in a kitt.yml regardless of YAML grammar specifics, so
    # reject it explicitly before parsing. Makes the rejection part of
    # this function's contract rather than a PyYAML implementation
    # detail that a future release could relax.
    if "\x00" in yaml_content:
        return "Error: yaml_content contains NUL bytes; refusing to write."

    # A UTF-8 BOM at the head of ``yaml_content`` passes through this
    # function verbatim: PyYAML strips it for the parse but we write
    # the raw string. Most downstream YAML readers tolerate a BOM; some
    # text tools (``grep ^project:``, strict line-oriented parsers) do
    # not. We do not strip the BOM because doing so silently rewrites
    # operator-supplied content; if the operator passed it in, they get
    # it back out.

    # YAML must not just parse; it must be a mapping that declares a
    # ``project`` block (a project file) or a ``workspace`` block (a
    # container root). The classifier owns that rule. Without this
    # gate, callers can write empty strings, bare scalars (``"x"``),
    # or lists and the function would cheerfully accept them.
    try:
        parsed = yaml.safe_load(yaml_content)
    except yaml.YAMLError as e:
        return f"Error: yaml_content failed to parse: {e}"
    if not isinstance(parsed, dict):
        return (
            "Error: yaml_content must be a mapping (got "
            f"{type(parsed).__name__})."
        )
    info = classify_kitt_yml_data(parsed)
    if info.kind == KIND_INVALID:
        return f"Error: yaml_content is not a valid kitt.yml: {info.error}"
    # Non-fatal classifier findings (a project-only section beside a
    # workspace block) ride along on the success string so the operator
    # sees them at write time, the same way detect_stack surfaces them.
    warning_suffix = "".join(f"\nWarning: {warning}" for warning in info.warnings)

    dest = dest_dir / "kitt.yml"
    # Two paths with different durability properties:
    #
    # * no-overwrite: open(dest, "x") gates create-or-fail at the
    #   filesystem level (no exists()+write race window). The file's
    #   bytes are fsync'd before this function returns, so a successful
    #   return implies the content is durable on disk. A crash mid-write
    #   may leave a partial file that blocks future creates; the operator
    #   resolves that by deleting the partial and re-running. An fsync
    #   that itself fails (rare; some network filesystems) returns an
    #   error AFTER the partial file has already been created, so the
    #   operator may also need to clean up in that case.
    # * overwrite: stage to a per-call temp name beside the destination,
    #   fsync, then os.replace. The replace is atomic on POSIX and on
    #   Windows when the temp file is on the same volume. A crash
    #   anywhere before the replace leaves the original file intact and
    #   orphans the temp; best-effort cleanup runs on error.
    #
    # Note: the containing directory is NOT fsync'd. A crash between the
    # rename and the directory metadata flush could lose the rename on a
    # power failure, but the workspace config file is trivially
    # regenerable by the operator, so the cost is acceptable.
    # Durability notes for both branches below:
    # * The create-or-fail branch uses ``atomic_create_text``, which
    #   opens the file with the "x" flag so the existence check and the
    #   create are a single filesystem operation with no exists+write
    #   race window. A crash mid-write may leave a partial file that
    #   blocks future creates; the operator resolves that by deleting
    #   the partial and re-running.
    # * The overwrite branch uses ``atomic_write_text``, which stages
    #   to a per-call temp file beside the destination, fsyncs the
    #   temp, then ``os.replace``s into place. The replace is atomic
    #   on POSIX and on Windows when the temp and destination live on
    #   the same volume.
    #
    # Caveats both branches share, documented once on
    # ``_atomic_write``: no directory fsync, no signal handler, no
    # cross-process lock. Acceptable for an operator-driven config
    # writer; the helper docstring spells out the trade-off.
    if not overwrite:
        try:
            atomic_create_text(dest, yaml_content)
        except FileExistsError:
            return (
                f"Error: {dest} already exists. Pass overwrite=True to replace it."
            )
        except OSError as e:
            return f"Error: failed to write {dest}: {e}"
    else:
        try:
            atomic_write_text(dest, yaml_content)
        except OSError as e:
            return f"Error: failed to write {dest}: {e}"

    return f"Wrote {dest}{warning_suffix}"


# -----------------------------------------------------------------------------
# Public: write_spec_stubs
# -----------------------------------------------------------------------------


_KNOWN_STACK_PROFILES = {"angular", "spring-boot", "fastapi"}


def _select_stack_template_sources(
    detection: dict[str, Any], target_path: str
) -> tuple[str, Path, Path]:
    """Pick the spec template sources for the target.

    Returns ``(stack, coder_src, tester_src)``. Stack-specific
    directories under ``catalog/crew/templates/by-stack/`` (``angular``,
    ``spring-boot``, ``fastapi``) carry ``coder-spec.md`` /
    ``tester-spec.md``. When the detected stack has no shipped
    directory, or the stack is unknown, fall back to the top-level
    generic skeletons ``coder-spec.template.md`` /
    ``tester-spec.template.md`` in ``catalog/crew/templates/`` — they
    are the single source the by-stack files specialize. Path
    resolution is centralized in :mod:`._data_paths`.
    """
    profile = _find_profile(detection, target_path)
    framework = (profile or {}).get("framework") or ""
    if framework in _KNOWN_STACK_PROFILES:
        for candidate in candidate_data_paths(
            "crew", "templates", "by-stack", framework,
        ):
            if candidate.is_dir():
                return (
                    framework,
                    candidate / "coder-spec.md",
                    candidate / "tester-spec.md",
                )
    generic_candidates = candidate_data_paths("crew", "templates")
    for candidate in generic_candidates:
        if candidate.is_dir():
            return (
                "generic",
                candidate / "coder-spec.template.md",
                candidate / "tester-spec.template.md",
            )
    fallback = generic_candidates[0]
    return (
        "generic",
        fallback / "coder-spec.template.md",
        fallback / "tester-spec.template.md",
    )


def _workspace_root_refusal(
    dest_dir: Path, detection: dict[str, Any], target_path: str
) -> str | None:
    """Why spec stubs must not land in ``dest_dir``, or ``None`` to proceed.

    Coder and tester specs are per-stack documents; a workspace root has
    no stack. Landing the generic skeletons there would hand the crew a
    "spec" for a REQ that actually lives in a member. Two signals catch
    it: a workspace-kind ``kitt.yml`` already on disk, or a detection
    that classified the root as a workspace while the target is ``.``
    (the pre-write case, before the root file exists).
    """
    members: list[str] = []
    on_disk = kitt_yml_kind(dest_dir) == KIND_WORKSPACE
    in_detection = (
        detection.get("project_type") == "workspace"
        and _normalize_target_path(target_path) == "."
    )
    if not (on_disk or in_detection):
        return None
    workspace_block = detection.get("workspace")
    if isinstance(workspace_block, dict):
        members = [
            str(member.get("path"))
            for member in workspace_block.get("members") or []
            if isinstance(member, dict) and member.get("path")
        ]
    listed = ", ".join(members) if members else "each member listed in its kitt.yml"
    return (
        f"Error: {dest_dir} is a workspace root (kitt.yml declares workspace:); "
        f"spec stubs belong to member projects. Run write_spec_stubs against "
        f"each member: {listed}."
    )


def write_spec_stubs(
    target_dir: str,
    detection_json: str,
    target_path: str,
    overwrite: bool = False,
) -> str:
    """Copy stack-appropriate spec stubs into ``<target_dir>/specs/``.

    Args:
        target_dir: Absolute path of the project directory where the
            ``specs/`` subdir should land. Must already exist.
        detection_json: Output of ``detect_stack``. Used to pick the
            right per-stack template (Angular, Spring Boot, FastAPI, or
            generic fallback).
        target_path: Path of the target inside the workspace, as it
            appears in the detection's ``targets`` list.
        overwrite: When ``False`` (default), refuses to overwrite
            existing spec files.

    Returns:
        Status string. Begins with ``Wrote`` listing the spec files
        landed, or ``Error:`` on failure.
    """
    if not target_dir:
        return "Error: target_dir is required."
    dest_dir = Path(target_dir).expanduser()
    if not dest_dir.is_absolute():
        return f"Error: target_dir {target_dir!r} is not absolute."
    dest_dir = dest_dir.resolve()
    if not dest_dir.is_dir():
        return f"Error: target directory does not exist: {dest_dir}"

    try:
        detection = json.loads(detection_json)
    except json.JSONDecodeError as e:
        return f"Error: invalid detection JSON: {e}"
    if not isinstance(detection, dict):
        return (
            "Error: detection JSON must be an object "
            f"(got {type(detection).__name__})."
        )

    refusal = _workspace_root_refusal(dest_dir, detection, target_path)
    if refusal is not None:
        return refusal

    stack, coder_src, tester_src = _select_stack_template_sources(
        detection, target_path
    )
    if not coder_src.is_file() or not tester_src.is_file():
        return (
            f"Error: template dir {coder_src.parent} is missing "
            f"{coder_src.name} or {tester_src.name}."
        )

    specs_dir = dest_dir / "specs"
    try:
        specs_dir.mkdir(exist_ok=True)
    except OSError as e:
        return f"Error: failed to create {specs_dir}: {e}"

    written: list[str] = []
    for src, dst_name in (
        (coder_src, "coder-spec.md"),
        (tester_src, "tester-spec.md"),
    ):
        dst = specs_dir / dst_name
        if dst.exists() and not overwrite:
            return (
                f"Error: {dst} already exists. Pass overwrite=True to "
                "replace it (or delete it and re-run)."
            )
        try:
            content = src.read_text(encoding="utf-8")
        except OSError as e:
            return f"Error: failed to read {src}: {e}"
        try:
            atomic_write_text(dst, content)
        except OSError as e:
            return f"Error: failed to write {dst}: {e}"
        written.append(str(dst))

    return (
        f"Wrote {len(written)} spec stubs (stack: {stack}): "
        f"{', '.join(written)}"
    )



# -----------------------------------------------------------------------------
# Registration
# -----------------------------------------------------------------------------


# Re-export the stub writers under their original names so existing
# callers and tests that reach ``kitt_yml.write_tracking_doc_stub`` (etc.)
# keep working after the split.
from .stub_writers import (  # noqa: E402, F401  re-export
    write_handoff_contract_stub,
    write_tracking_doc_stub,
)


def register(mcp: FastMCP) -> None:
    """Register `kitt.yml` generator tools with the KITT MCP server.

    Stub writers (``write_tracking_doc_stub``,
    ``write_handoff_contract_stub``) used to live here too.
    They have moved to :mod:`tools.stub_writers`; ``server.py``
    registers both modules. Tests that previously imported them
    from ``tools.kitt_yml`` should now import from
    ``tools.stub_writers`` directly.
    """
    mcp.tool()(propose_kitt_yml)
    mcp.tool()(write_kitt_yml)
    mcp.tool()(write_spec_stubs)
