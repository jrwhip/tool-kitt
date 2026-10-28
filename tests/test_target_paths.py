"""Tests for the shared target-path helpers.

``kitt.tools._target_paths`` is consumed by both ``kitt_yml``
and ``claude_md`` for normalizing operator-supplied target paths,
locating profiles in a detection result, and deriving slugs / names.
Pinning each helper's contract here means a future edit to the
NFKD normalization, regex, or fallback string lands one test
failure away.
"""

from __future__ import annotations

from kitt.tools._target_paths import (
    find_profile,
    name_from_slug,
    normalize_target_path,
    slug_from_target,
)


class TestNormalizeTargetPath:
    def test_empty_string_becomes_dot(self):
        assert normalize_target_path("") == "."

    def test_dot_stays_dot(self):
        assert normalize_target_path(".") == "."

    def test_dot_slash_becomes_dot(self):
        assert normalize_target_path("./") == "."

    def test_leading_dot_slash_stripped(self):
        assert normalize_target_path("./apps/foo") == "apps/foo"

    def test_trailing_slash_stripped(self):
        assert normalize_target_path("apps/foo/") == "apps/foo"

    def test_both_leading_and_trailing(self):
        assert normalize_target_path("./apps/foo/") == "apps/foo"

    def test_whitespace_is_stripped(self):
        assert normalize_target_path("  apps/foo  ") == "apps/foo"

    def test_intermediate_segments_preserved(self):
        assert normalize_target_path("a/b/c") == "a/b/c"


class TestFindProfile:
    def test_matches_exact_path(self):
        detection = {
            "targets": [
                {"target_path": "apps/foo", "framework": "angular"},
                {"target_path": "apps/bar", "framework": "react"},
            ]
        }
        assert find_profile(detection, "apps/foo")["framework"] == "angular"

    def test_matches_after_normalization(self):
        detection = {"targets": [{"target_path": "apps/foo", "framework": "angular"}]}
        # Operator typed "./apps/foo/" but the detection stores "apps/foo".
        assert find_profile(detection, "./apps/foo/")["framework"] == "angular"

    def test_root_dot_matches_dot_target(self):
        detection = {"targets": [{"target_path": ".", "framework": "spring-boot"}]}
        assert find_profile(detection, ".")["framework"] == "spring-boot"
        assert find_profile(detection, "")["framework"] == "spring-boot"

    def test_no_match_returns_none(self):
        detection = {"targets": [{"target_path": "apps/foo"}]}
        assert find_profile(detection, "apps/bar") is None

    def test_empty_targets_returns_none(self):
        assert find_profile({"targets": []}, "anything") is None
        assert find_profile({}, "anything") is None

    def test_non_dict_profile_returns_none(self):
        """A target entry that isn't a dict cannot be a StackProfile."""
        detection = {"targets": ["just-a-string"]}
        # The match still uses ``target_path`` access, which fails on a
        # str. The helper protects via the get(...) on a non-dict and
        # the trailing isinstance check.
        result = find_profile(detection, "anything")
        assert result is None


class TestSlugFromTarget:
    def test_basic_kebab_lowercase(self):
        assert slug_from_target("apps/example-app", "/ws") == "example-app"

    def test_nfkd_normalization_preserves_accented_chars(self):
        """``café`` becomes ``cafe``, NOT ``caf``.

        The prior regex-only strip silently dropped accented glyphs.
        This is the carefully-documented behavior in the helper.
        """
        assert slug_from_target("apps/café", "/ws") == "cafe"

    def test_falls_back_to_workspace_name_when_target_is_dot(self):
        assert slug_from_target(".", "/some/workspace-name") == "workspace-name"

    def test_collapses_non_alphanumeric_to_hyphen(self):
        assert slug_from_target("apps/foo_bar baz", "/ws") == "foo-bar-baz"

    def test_strips_leading_trailing_hyphens(self):
        assert slug_from_target("apps/__foo__", "/ws") == "foo"

    def test_falls_back_to_project_when_slug_would_be_empty(self):
        assert slug_from_target("apps/!!!", "/ws") == "project"


class TestNameFromSlug:
    def test_title_cases_kebab_segments(self):
        assert name_from_slug("example-app") == "Example App"

    def test_single_word(self):
        assert name_from_slug("foo") == "Foo"

    def test_empty_falls_back_to_project(self):
        assert name_from_slug("") == "Project"
