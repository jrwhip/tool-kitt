"""Stack detection: identify a project's language, framework, and layout.

Deterministic and read-only. Inspects a workspace directory, identifies
the stack via well-known marker files, enumerates monorepo apps, and
inventories any existing ``kitt.yml`` files.

Its JSON output is the required input to :mod:`.kitt_yml`'s
``propose_kitt_yml`` / ``write_kitt_yml``, which is why it ships here.
In the prior toolset this lived inside a larger ``doctor`` module
alongside a recommendation-and-dismissal engine; that engine does not
cross over, so only the detector did.
"""

from __future__ import annotations

import json
import logging
import re
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any

import yaml

from ..product import CONFIG_FILENAME, LOGGER_NAME
from ._kitt_yml_kind import (
    KIND_INVALID,
    WorkspaceSection,
    classify_kitt_yml_data,
    describe_members,
    load_kitt_yml,
)
from ._safe_load import safe_load_json as _safe_load_json
from ._safe_load import safe_load_yaml as _safe_load_yaml
from ._workspace_root import GIT_DIR_NAME

if TYPE_CHECKING:
    from mcp.server.fastmcp import FastMCP

logger = logging.getLogger(LOGGER_NAME)


# -----------------------------------------------------------------------------
# Typed detection output
# -----------------------------------------------------------------------------


@dataclass
class StackProfile:
    """Detected stack signals for a single target (app or root)."""

    target_path: str
    language: str | None = None
    framework: str | None = None
    framework_version: str | None = None
    package_manager: str | None = None
    libraries: list[str] = field(default_factory=list)
    test_runner: str | None = None
    openapi_role: str | None = None


@dataclass
class KittYmlInventory:
    """A `kitt.yml` file found in the workspace.

    ``summary`` is a small subset of the parsed file that the recommender
    needs (specs paths, API contract pin, base_package). Operator-facing
    skills surface these so the report shows what each kitt.yml
    declares, not just that it exists.
    """

    path: str
    parse_ok: bool
    parse_error: str | None = None
    summary: dict[str, Any] | None = None


@dataclass
class WorkspaceMemberDetection:
    """One declared member of a workspace root, as detection saw it.

    :class:`._kitt_yml_kind.DescribedMember` serialized the same way
    ``get_workspace_info`` serializes it, plus ``detected``: whether a
    stack detector recognized the directory. Built explicitly in
    :func:`_detect_workspace_members`, field by field, so the two
    shapes are checked against each other by mypy rather than by a
    comment.
    """

    path: str
    abs_path: str
    slug: str
    role: str
    exists: bool
    has_kitt_yml: bool
    kitt_yml_kind: str | None
    has_learnings: bool
    detected: bool


@dataclass
class WorkspaceDetection:
    """The workspace block of a root ``kitt.yml``, cross-checked with disk."""

    slug: str
    name: str | None
    members: list[WorkspaceMemberDetection] = field(default_factory=list)
    #: Immediate children the container scan recognizes as projects (a
    #: stack marker file, or a ``.git`` of their own) that the root file
    #: does not list. Surfaced so the operator can declare or ignore them.
    undeclared_children: list[str] = field(default_factory=list)
    #: Declared member paths that are not directories on disk.
    missing_children: list[str] = field(default_factory=list)


@dataclass
class StackDetection:
    """Top-level detection result for a workspace."""

    workspace_path: str
    project_type: str  # "single-app", "monorepo", "container", or "workspace"
    monorepo_type: str | None = None
    targets: list[StackProfile] = field(default_factory=list)
    kitt_yml_inventory: list[KittYmlInventory] = field(default_factory=list)
    detected_external_signals: list[str] = field(default_factory=list)
    #: Set only when ``project_type`` is ``"workspace"``.
    workspace: WorkspaceDetection | None = None


# -----------------------------------------------------------------------------
# Helpers: marker-file parsers
# -----------------------------------------------------------------------------


# The ``_safe_*`` family below is the detection-hot-path read API.
# Each helper returns ``None`` on any failure (missing file, bad
# permission, parse error) so callers can write straight-line probe
# code. The asymmetry the audit flagged was that ALL failures were
# silent, including "exists but unreadable" and "exists but malformed"
# which are legitimate operator-facing problems.
#
# _safe_load_json/_safe_load_yaml themselves live in ._safe_load
# (imported above) so other tool modules can share them. Posture:
# missing or unreadable is logged at DEBUG (expected hot-path noise during a full
# workspace scan); a parse failure on a file the caller specifically
# asked for is logged at WARNING because the operator usually wants to
# know their pom.xml or package.json is malformed. The return contract
# is unchanged.


def _safe_read_text(path: Path) -> str | None:
    try:
        return path.read_text(encoding="utf-8")
    except OSError as e:
        logger.debug("Cannot read %s as text: %s", path, e)
        return None


def _detect_node_target(target_path: Path, workspace: Path) -> StackProfile | None:
    """Parse package.json and classify the target."""
    pkg_path = target_path / "package.json"
    if not pkg_path.is_file():
        return None
    pkg = _safe_load_json(pkg_path)
    if not pkg:
        return None

    deps: dict[str, str] = {}
    deps.update(pkg.get("dependencies") or {})
    deps.update(pkg.get("devDependencies") or {})

    # Framework detection. Order matters: more specific frameworks first.
    framework: str | None = None
    framework_version: str | None = None
    if "@angular/core" in deps:
        framework = "angular"
        framework_version = deps["@angular/core"]
    elif "react" in deps:
        framework = "react"
        framework_version = deps["react"]
    elif "vue" in deps:
        framework = "vue"
        framework_version = deps["vue"]
    elif "next" in deps:
        framework = "next"
        framework_version = deps["next"]

    # Libraries.
    libraries: list[str] = []
    for lib_key, label in [
        ("ag-grid-angular", "ag-grid"),
        ("ag-grid-react", "ag-grid"),
        ("ag-grid-vue3", "ag-grid"),
        ("ag-grid-community", "ag-grid"),
        ("ag-grid-enterprise", "ag-grid-enterprise"),
    ]:
        if lib_key in deps and label not in libraries:
            libraries.append(label)

    # Test runner.
    test_runner: str | None = None
    if "vitest" in deps:
        test_runner = "vitest"
    elif "jest" in deps:
        test_runner = "jest"
    elif "@playwright/test" in deps:
        test_runner = "playwright"

    # Package manager: heuristic by lockfile presence. Check the
    # target's own dir first (for container children that have their
    # own lockfile at the child level), then fall back to the workspace
    # root (for monorepo apps where the lockfile lives at the workspace
    # root and apps inherit it).
    package_manager: str | None = None
    for lockfile_dir in (target_path, workspace):
        if (lockfile_dir / "pnpm-lock.yaml").is_file():
            package_manager = "pnpm"
            break
        if (lockfile_dir / "yarn.lock").is_file():
            package_manager = "yarn"
            break
        if (lockfile_dir / "package-lock.json").is_file():
            package_manager = "npm"
            break
        if (lockfile_dir / "bun.lockb").is_file():
            package_manager = "bun"
            break

    # OpenAPI role: frontend consumer if generator-cli present.
    openapi_role: str | None = None
    if "@openapitools/openapi-generator-cli" in deps:
        openapi_role = "consumer"

    rel = target_path.relative_to(workspace).as_posix() if target_path != workspace else "."
    has_typescript = any(k == "typescript" or k.startswith("typescript") for k in deps)
    return StackProfile(
        target_path=rel,
        language="typescript" if has_typescript else "javascript",
        framework=framework,
        framework_version=framework_version,
        package_manager=package_manager,
        libraries=libraries,
        test_runner=test_runner,
        openapi_role=openapi_role,
    )


def _detect_java_target(target_path: Path, workspace: Path) -> StackProfile | None:
    """Parse pom.xml or build.gradle*."""
    pom = target_path / "pom.xml"
    gradle = target_path / "build.gradle"
    gradle_kts = target_path / "build.gradle.kts"

    if pom.is_file():
        text = _safe_read_text(pom) or ""
        framework = "spring-boot" if "spring-boot-starter" in text else None
        java_version = None
        m = re.search(r"<java\.version>([^<]+)</java\.version>", text)
        if m:
            java_version = m.group(1).strip()
        else:
            m = re.search(r"<maven\.compiler\.source>([^<]+)</maven\.compiler\.source>", text)
            if m:
                java_version = m.group(1).strip()
        openapi_role = "producer" if "springdoc-openapi" in text else None
        rel = target_path.relative_to(workspace).as_posix() if target_path != workspace else "."
        return StackProfile(
            target_path=rel,
            language="java",
            framework=framework,
            framework_version=java_version,
            package_manager="maven",
            openapi_role=openapi_role,
        )
    if gradle.is_file() or gradle_kts.is_file():
        text = (_safe_read_text(gradle) or "") + (_safe_read_text(gradle_kts) or "")
        framework = "spring-boot" if "spring-boot" in text else None
        openapi_role = "producer" if "springdoc-openapi" in text else None
        rel = target_path.relative_to(workspace).as_posix() if target_path != workspace else "."
        return StackProfile(
            target_path=rel,
            language="java",
            framework=framework,
            package_manager="gradle",
            openapi_role=openapi_role,
        )
    return None


def _detect_python_target(target_path: Path, workspace: Path) -> StackProfile | None:
    pyproject = target_path / "pyproject.toml"
    requirements = target_path / "requirements.txt"
    deps_text = ""
    if pyproject.is_file():
        deps_text += _safe_read_text(pyproject) or ""
    if requirements.is_file():
        deps_text += "\n" + (_safe_read_text(requirements) or "")
    if not deps_text:
        return None

    framework: str | None = None
    if re.search(r"\bfastapi\b", deps_text):
        framework = "fastapi"
    elif re.search(r"\bflask\b", deps_text):
        framework = "flask"
    elif re.search(r"\bdjango\b", deps_text):
        framework = "django"

    rel = target_path.relative_to(workspace).as_posix() if target_path != workspace else "."
    return StackProfile(
        target_path=rel,
        language="python",
        framework=framework,
        package_manager="pip",
    )


def _detect_rust_target(target_path: Path, workspace: Path) -> StackProfile | None:
    cargo = target_path / "Cargo.toml"
    if not cargo.is_file():
        return None
    rel = target_path.relative_to(workspace).as_posix() if target_path != workspace else "."
    return StackProfile(
        target_path=rel,
        language="rust",
        package_manager="cargo",
    )


def _detect_go_target(target_path: Path, workspace: Path) -> StackProfile | None:
    if not (target_path / "go.mod").is_file():
        return None
    rel = target_path.relative_to(workspace).as_posix() if target_path != workspace else "."
    return StackProfile(
        target_path=rel,
        language="go",
        package_manager="go",
    )


def _detect_dotnet_target(target_path: Path, workspace: Path) -> StackProfile | None:
    csproj = list(target_path.glob("*.csproj"))
    if not csproj:
        return None
    rel = target_path.relative_to(workspace).as_posix() if target_path != workspace else "."
    return StackProfile(
        target_path=rel,
        language="csharp",
        package_manager="dotnet",
    )


def _detect_nx_app(app_path: Path, workspace: Path) -> StackProfile | None:
    """Detect an Nx-style app whose deps live in the workspace root.

    Nx apps own their own ``project.json`` and ``tsconfig.app.json`` but
    typically inherit ``package.json`` from the workspace root. Plain
    ``_detect_node_target`` misses these because it expects a per-app
    ``package.json``. This helper reads the app's ``project.json`` for
    framework hints (build executor) and falls back to the workspace
    root's package.json for library and test-runner detection.
    """
    project_json = app_path / "project.json"
    if not project_json.is_file():
        return None
    project = _safe_load_json(project_json)
    if not project:
        return None

    # Framework from the build executor when available; Angular Nx apps
    # use @angular/build:* or @angular-devkit/build-angular:*.
    framework: str | None = None
    targets_block = project.get("targets") or {}
    for target_def in targets_block.values():
        if not isinstance(target_def, dict):
            continue
        executor = target_def.get("executor") or ""
        if not isinstance(executor, str):
            continue
        is_angular = executor.startswith("@angular/build") or executor.startswith(
            "@angular-devkit/build-angular"
        )
        if is_angular:
            framework = "angular"
            break
        if executor.startswith("@nx/react"):
            framework = "react"
            break
        if executor.startswith("@nx/vue"):
            framework = "vue"
            break

    # Inherit library + test-runner + package-manager from the workspace
    # root package.json. The workspace-root profile already does this
    # work; we replicate the relevant fields here.
    root_profile = _detect_node_target(workspace, workspace)
    libraries = list(root_profile.libraries) if root_profile else []
    test_runner = root_profile.test_runner if root_profile else None
    package_manager = root_profile.package_manager if root_profile else None
    openapi_role = root_profile.openapi_role if root_profile else None

    rel = app_path.relative_to(workspace).as_posix()
    return StackProfile(
        target_path=rel,
        language="typescript",
        framework=framework,
        package_manager=package_manager,
        libraries=libraries,
        test_runner=test_runner,
        openapi_role=openapi_role,
    )


def _detect_target(target_path: Path, workspace: Path) -> StackProfile | None:
    """Run all language detectors on a target dir; first hit wins.

    Order: Node first (most common in KITT-adjacent work), then Java,
    Python, Rust, Go, .NET. A target with both `package.json` and a
    backend marker is unusual but resolved by Node priority. Nx apps
    (``project.json`` only, no per-app ``package.json``) are handled by
    a dedicated helper.
    """
    for detector in (
        _detect_node_target,
        _detect_java_target,
        _detect_python_target,
        _detect_rust_target,
        _detect_go_target,
        _detect_dotnet_target,
    ):
        profile = detector(target_path, workspace)
        if profile:
            return profile
    return None


# -----------------------------------------------------------------------------
# Helpers: monorepo and workspace-level signals
# -----------------------------------------------------------------------------


def _detect_monorepo_type(workspace: Path) -> str | None:
    if (workspace / "nx.json").is_file():
        return "nx"
    if (workspace / "pnpm-workspace.yaml").is_file():
        return "pnpm-workspaces"
    if (workspace / "lerna.json").is_file():
        return "lerna"
    if (workspace / "turbo.json").is_file():
        return "turbo"
    return None


def _enumerate_monorepo_apps(workspace: Path, monorepo_type: str) -> list[Path]:
    """Return per-app directories for known monorepo layouts."""
    candidates: list[Path] = []
    apps_dir = workspace / "apps"
    if apps_dir.is_dir():
        candidates.extend(p for p in apps_dir.iterdir() if p.is_dir())
    if monorepo_type == "pnpm-workspaces":
        ws_file = workspace / "pnpm-workspace.yaml"
        data = _safe_load_yaml(ws_file)
        if isinstance(data, dict):
            packages = data.get("packages") or []
            for glob in packages:
                if not isinstance(glob, str):
                    continue
                for match in workspace.glob(glob):
                    if match.is_dir() and match not in candidates:
                        candidates.append(match)
    return sorted(set(candidates))


_CONTAINER_SCAN_SKIP_DIRS = frozenset({
    "node_modules", ".git", "target", "build", "dist", ".venv", "venv",
    "__pycache__", ".idea", ".vscode", ".gradle", ".mvn", ".pytest_cache",
    ".ruff_cache", ".mypy_cache", ".turbo", ".next", ".nuxt", ".cache",
    "coverage", "out", ".angular",
})


def _detect_container_children(
    workspace: Path, *, skip_paths: frozenset[str] = frozenset()
) -> list[StackProfile]:
    """Scan immediate children for sub-project marker files.

    ``skip_paths`` names children (relative POSIX paths) the caller has
    already profiled; they are not read again.

    When the workspace path itself has no recognizable marker files and
    is not a known monorepo, treat it as a container directory and
    classify each immediate child that looks like a project. This makes
    ``detect_stack /path/to/parent`` produce useful output when the
    path is a parent dir holding ``example-frontend/``,
    ``example-webapp/``, and ``example-api/`` rather than returning an
    empty targets list.

    A child that is its own git repository counts as a project even
    when no stack detector recognizes it (a test-suite repo holding
    only scripts, say): in a container of sibling repos the ``.git``
    entry is the operator's own statement that the directory is a
    project, so it gets a bare profile (``target_path`` only) rather
    than being dropped. Skips hidden directories and common build /
    vendor noise. Sorts the output by target path so the result is
    reproducible. Does NOT recurse further; a detected child that is
    itself a monorepo (``monorepo_type`` would be set if re-scanned) is
    left to the operator to re-run against directly.
    """
    children: list[StackProfile] = []
    try:
        entries = sorted(workspace.iterdir())
    except OSError:
        return []
    for child in entries:
        if not child.is_dir():
            continue
        name = child.name
        if name.startswith("."):
            continue
        if name in _CONTAINER_SCAN_SKIP_DIRS:
            continue
        rel = child.relative_to(workspace).as_posix()
        if rel in skip_paths:
            continue
        profile = _detect_target(child, workspace)
        if profile is None and (child / GIT_DIR_NAME).exists():
            profile = StackProfile(target_path=rel)
        if profile is not None:
            children.append(profile)
    return children


def _detect_workspace_members(
    workspace: Path, section: WorkspaceSection
) -> tuple[WorkspaceDetection, list[StackProfile]]:
    """Profile each declared member and cross-check the declaration with disk.

    Every existing member becomes a target. A member no detector
    recognizes still gets a bare profile (``target_path`` only) so
    ``find_profile`` resolves it and ``propose_kitt_yml`` can offer a
    generic project file for it; a declared member is a target by
    the operator's word, not by marker files. Undeclared children are
    whatever the container scan would have found that the root file
    omits; the scan is immediate-children only, so a nested declared
    member such as ``apps/api`` never shows up as undeclared.
    """
    members: list[WorkspaceMemberDetection] = []
    targets: list[StackProfile] = []
    declared: set[str] = set()
    missing: list[str] = []
    for member in describe_members(workspace, section):
        declared.add(member.path)
        detected = False
        if member.exists:
            profile = _detect_target(member.abs_path, workspace)
            if profile is None:
                profile = StackProfile(target_path=member.path)
            else:
                detected = True
            targets.append(profile)
        else:
            missing.append(member.path)
        members.append(
            WorkspaceMemberDetection(
                path=member.path,
                abs_path=str(member.abs_path),
                slug=member.slug,
                role=member.role,
                exists=member.exists,
                has_kitt_yml=member.has_kitt_yml,
                kitt_yml_kind=member.kitt_yml_kind,
                has_learnings=member.has_learnings,
                detected=detected,
            )
        )
    # Declared members were just profiled; the container scan only has
    # to look at the children the root file does not mention.
    undeclared = [
        child.target_path
        for child in _detect_container_children(workspace, skip_paths=frozenset(declared))
    ]
    detection = WorkspaceDetection(
        slug=section.slug,
        name=section.name,
        members=members,
        undeclared_children=undeclared,
        missing_children=missing,
    )
    return detection, targets


def _summarize_kitt_yml(data: Any) -> dict[str, Any]:
    """Extract the recommender-relevant subset of a parsed kitt.yml.

    Picks just the fields downstream skills surface: project identity,
    spec paths, API contract pin. Avoids forwarding the whole document so
    callers do not couple to fields that are not yet stable.
    """
    if not isinstance(data, dict):
        return {}
    # ``kind`` is on every entry so a skill reading the inventory can tell
    # a workspace root from a project without re-deriving the rule, and
    # never mistakes the root file for a project with missing specs.
    info = classify_kitt_yml_data(data)
    summary: dict[str, Any] = {"kind": info.kind}
    if info.kind == KIND_INVALID:
        summary["error"] = info.error
        return summary
    if info.workspace is not None:
        summary["workspace"] = {
            "slug": info.workspace.slug,
            "name": info.workspace.name,
            "projects": [
                {"path": m.path, "slug": m.slug, "role": m.role}
                for m in info.workspace.members
            ],
        }
        if info.warnings:
            summary["warnings"] = list(info.warnings)
        return summary
    project = data.get("project") if isinstance(data.get("project"), dict) else {}
    if project:
        summary["project"] = {
            "slug": project.get("slug"),
            "name": project.get("name"),
            "base_package": project.get("base_package"),
            "build_file": project.get("build_file"),
            "target_source_root": project.get("target_source_root"),
            "test_root": project.get("test_root"),
        }
    specs = data.get("specs") if isinstance(data.get("specs"), dict) else {}
    if specs:
        summary["specs"] = {
            "coder_spec": specs.get("coder_spec"),
            "tester_spec": specs.get("tester_spec"),
            "audit_report": specs.get("audit_report"),
        }
    # API contract: the machine-readable surface agents cite (OpenAPI
    # document or GraphQL schema). The section was named ``openapi``
    # before GraphQL projects existed; a legacy ``openapi:`` block is
    # read as ``api_contract`` with ``kind: openapi`` so those projects
    # keep working. ``api_contract`` wins when both are present.
    raw_contract = data.get("api_contract")
    legacy_openapi = data.get("openapi")
    if isinstance(raw_contract, dict):
        summary["api_contract"] = {
            "kind": raw_contract.get("kind") or "openapi",
            "spec_url": raw_contract.get("spec_url"),
            "pinned_generator_version": raw_contract.get("pinned_generator_version"),
        }
    elif isinstance(legacy_openapi, dict):
        summary["api_contract"] = {
            "kind": "openapi",
            "spec_url": legacy_openapi.get("spec_url"),
            "pinned_generator_version": legacy_openapi.get("pinned_generator_version"),
            "legacy_section": "openapi",
        }
    # Requirements source resolution. Absent section defaults to
    # source=local with path=requirements so existing projects (which
    # predate this field) keep working without an edit. The summary
    # always includes a normalized requirements block so downstream
    # readiness checks have a single shape to consume. Store each
    # ``data.get`` call once and narrow via isinstance so mypy can
    # follow the type through (the existing project/specs/api_contract
    # blocks happen to escape narrowing only because each is guarded
    # by an ``if`` before use; the requirements block is unconditional).
    raw_requirements = data.get("requirements")
    requirements: dict[str, Any] = (
        raw_requirements if isinstance(raw_requirements, dict) else {}
    )
    req_source = requirements.get("source") or "local"
    req_summary: dict[str, Any] = {"source": req_source}
    if req_source == "local":
        raw_local = requirements.get("local")
        local_cfg: dict[str, Any] = (
            raw_local if isinstance(raw_local, dict) else {}
        )
        req_summary["local"] = {"path": local_cfg.get("path") or "requirements"}
    elif req_source == "jira":
        raw_jira = requirements.get("jira")
        jira_cfg: dict[str, Any] = (
            raw_jira if isinstance(raw_jira, dict) else {}
        )
        # cloud_id is intentionally NOT extracted here. The Atlassian
        # site is resolved at runtime by the orchestrator via
        # getAccessibleAtlassianResources; it is machine-level state
        # not project-level, and storing it in kitt.yml was redundant
        # for single-site operators. Any legacy `cloud_id` entry in
        # the yml is silently ignored.
        req_summary["jira"] = {
            "project_key": jira_cfg.get("project_key"),
        }
    summary["requirements"] = req_summary
    if "legacy-migration" in data:
        summary["has_legacy_migration_block"] = True
    return summary


def _detect_kitt_yml_files(workspace: Path) -> list[KittYmlInventory]:
    """Find every `kitt.yml` in the workspace, parse it, and summarize.

    The summary surfaces the recommender-relevant subset (project
    identity, spec paths, API contract pin). Operator-facing skills render
    this so the report shows what each kitt.yml declares, not just that
    it exists.
    """
    found: list[KittYmlInventory] = []
    for path in workspace.rglob("kitt.yml"):
        # Skip directories the container scanner already considers
        # noise. Sharing the set keeps the two scanners aligned; the
        # previous inline set was a stale six-entry subset that let
        # rglob walk into .angular/, .next/, .gradle/, coverage/ on
        # every scan.
        # Filter on the path INSIDE the workspace. Matching the absolute
        # path would empty the inventory for any workspace that happens
        # to sit under a directory named ``build``, ``out``, ``target``...
        if set(path.relative_to(workspace).parts) & _CONTAINER_SCAN_SKIP_DIRS:
            continue
        # Read via the module's shared helper so a parse failure is
        # logged at WARNING (operator-facing problem) and a read
        # failure is logged at DEBUG (hot path). The inventory still
        # carries parse_ok and parse_error so the operator report
        # shows the per-file outcome.
        try:
            text = path.read_text(encoding="utf-8")
        except OSError as e:
            logger.debug("Cannot read %s as text: %s", path, e)
            found.append(
                KittYmlInventory(
                    path=path.relative_to(workspace).as_posix(),
                    parse_ok=False,
                    parse_error=str(e),
                )
            )
            continue
        try:
            data = yaml.safe_load(text)
        except yaml.YAMLError as e:
            logger.warning("Cannot parse %s as YAML: %s", path, e)
            found.append(
                KittYmlInventory(
                    path=path.relative_to(workspace).as_posix(),
                    parse_ok=False,
                    parse_error=str(e),
                )
            )
            continue
        found.append(
            KittYmlInventory(
                path=path.relative_to(workspace).as_posix(),
                parse_ok=True,
                summary=_summarize_kitt_yml(data),
            )
        )
    return found


def _detect_external_signals(workspace: Path, targets: list[StackProfile]) -> list[str]:
    """Project-wide signals that recommend external MCPs.

    Conservative: only flag when the evidence is unambiguous.
    """
    signals: set[str] = set()

    for profile in targets:
        if "ag-grid" in profile.libraries or "ag-grid-enterprise" in profile.libraries:
            signals.add("ag-grid")

    # Atlassian: any markdown under tickets/ referencing a JIRA-style ticket ID,
    # e.g. DEMO26-1234. The regex is generic and matches any 2-5 letter prefix.
    tickets_dir = workspace / "tickets"
    if tickets_dir.is_dir():
        for md_path in tickets_dir.rglob("*.md"):
            text = _safe_read_text(md_path) or ""
            if re.search(r"\b[A-Z]{2,5}26-\d+\b", text):
                signals.add("atlassian")
                break

    # Chrome devtools: frontend Playwright or Cypress, or e2e tests.
    for profile in targets:
        if profile.test_runner == "playwright":
            signals.add("chrome-devtools")
            break

    return sorted(signals)


# -----------------------------------------------------------------------------
# Public: detect_stack
# -----------------------------------------------------------------------------


def detect_stack(workspace_path: str) -> str:
    """Scan a workspace directory and identify the stack.

    Args:
        workspace_path: Absolute path to the project directory to scan.
            Required. The caller (a skill running in the operator's
            session) is responsible for resolving this from the
            operator's actual working context. This function does NOT
            fall back to any env var, lock file, or other pinned
            workspace; relying on a server-side default produced
            silent foot-guns when the MCP server was started in one
            directory and the operator was working in another.

    Returns:
        JSON-encoded ``StackDetection`` describing project type, per-target
        stack profiles, `kitt.yml` inventory, and external signals worth
        flagging to the operator. Read-only; no file writes.
    """
    if not workspace_path:
        return json.dumps({
            "error": (
                "workspace_path is required. Pass the absolute path of "
                "the project directory the operator wants to scan; this "
                "function does not infer a workspace from environment "
                "or installation state."
            )
        })

    workspace = Path(workspace_path).expanduser().resolve()
    if not workspace.is_dir():
        return json.dumps({
            "error": f"Workspace path does not exist or is not a directory: {workspace}"
        })

    # A workspace-kind kitt.yml at the root wins over every other
    # signal: the operator declared what the children are, so the
    # targets are the declared members, not whatever marker files a
    # scan would guess at. An invalid root file is NOT a workspace; it
    # falls through to the ordinary logic and the inventory entry
    # carries the parse problem. Monorepo markers are not even consulted
    # on a workspace root.
    root_info = load_kitt_yml(workspace / CONFIG_FILENAME)
    root_workspace = None if root_info is None else root_info.workspace
    monorepo_type = None if root_workspace is not None else _detect_monorepo_type(workspace)
    targets: list[StackProfile] = []
    project_type = "monorepo" if monorepo_type else "single-app"
    workspace_detection: WorkspaceDetection | None = None

    if root_workspace is not None:
        project_type = "workspace"
        workspace_detection, targets = _detect_workspace_members(workspace, root_workspace)
    elif monorepo_type:
        # Always include root profile (the monorepo's own package.json / build file).
        root_profile = _detect_target(workspace, workspace)
        if root_profile:
            targets.append(root_profile)
        # Enumerate per-app sub-targets. Nx apps inherit package.json from
        # the workspace root, so they need a dedicated detector that falls
        # back to the root's deps when classifying.
        for app_path in _enumerate_monorepo_apps(workspace, monorepo_type):
            sub: StackProfile | None = None
            if monorepo_type == "nx":
                sub = _detect_nx_app(app_path, workspace)
            if sub is None:
                sub = _detect_target(app_path, workspace)
            if sub:
                targets.append(sub)
    else:
        root = _detect_target(workspace, workspace)
        if root:
            targets.append(root)
        else:
            # No markers at the root. The path is plausibly a container
            # directory holding sibling projects (e.g. a parent dir
            # with ``example-frontend/``, ``example-webapp/``, and
            # ``example-api/`` as children). Scan one level
            # down so the operator gets the actual sub-projects as
            # targets instead of an empty report. Skip hidden dirs and
            # common build/vendor noise; do not recurse further (a
            # detected child that is itself a monorepo is left for the
            # operator to re-run against directly).
            container_children = _detect_container_children(workspace)
            if container_children:
                project_type = "container"
            targets.extend(container_children)

    kitt_yml_inventory = _detect_kitt_yml_files(workspace)
    external_signals = _detect_external_signals(workspace, targets)

    detection = StackDetection(
        workspace_path=str(workspace),
        project_type=project_type,
        monorepo_type=monorepo_type,
        targets=targets,
        kitt_yml_inventory=kitt_yml_inventory,
        detected_external_signals=external_signals,
        workspace=workspace_detection,
    )
    return json.dumps(asdict(detection), indent=2)


# -----------------------------------------------------------------------------
# Registration
# -----------------------------------------------------------------------------


def register(mcp: FastMCP) -> None:
    """Register the stack detection tool with the KITT MCP server."""
    mcp.tool()(detect_stack)
