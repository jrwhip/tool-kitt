"""Tests for format converters."""

from kitt.converters import (
    COPILOT_ARGUMENTS_PHRASE,
    parse_claude,
    to_copilot_agent,
    to_copilot_skill,
    to_gemini_toml,
)


class TestParseClaude:
    def test_no_frontmatter(self):
        result = parse_claude("Just some text")
        assert result.frontmatter == {}
        assert result.body == "Just some text"

    def test_with_frontmatter(self):
        content = "---\ndescription: test\n---\nBody text"
        result = parse_claude(content)
        assert result.frontmatter == {"description": "test"}
        assert result.body == "Body text"

    def test_malformed_frontmatter(self):
        content = "---\nno closing"
        result = parse_claude(content)
        assert result.frontmatter == {}
        assert result.body == "---\nno closing"

    def test_empty_frontmatter(self):
        content = "---\n---\nBody only"
        result = parse_claude(content)
        assert result.frontmatter == {}
        assert result.body == "Body only"

    def test_complex_frontmatter(self):
        content = "---\nname: test-agent\ntools:\n  - Read\n  - Write\n---\nInstructions"
        result = parse_claude(content)
        assert result.frontmatter["name"] == "test-agent"
        assert result.frontmatter["tools"] == ["Read", "Write"]
        assert result.body == "Instructions"


class TestToGeminiToml:
    def test_basic_conversion(self):
        content = "---\ndescription: Test command\n---\nDo the thing with $ARGUMENTS"
        result = to_gemini_toml(content)
        assert 'description = "Test command"' in result
        assert "{{args}}" in result
        assert "$ARGUMENTS" not in result

    def test_no_frontmatter(self):
        result = to_gemini_toml("Just text $ARGUMENTS")
        assert "description" not in result
        assert "{{args}}" in result

    def test_dynamic_bash_syntax(self):
        result = to_gemini_toml("Run !`git status` now")
        assert "!{git status}" in result

    def test_file_references(self):
        result = to_gemini_toml("Read @src/main.ts for context")
        assert "@{src/main.ts}" in result


class TestToCopilotAgent:
    def test_basic_conversion(self):
        content = "---\nname: test-agent\ndescription: A test\n---\nDo stuff"
        result = to_copilot_agent(content)
        assert "name: test-agent" in result
        assert "description: A test" in result
        assert "Do stuff" in result

    def test_tool_mapping(self):
        """Tools normalize to Copilot's CANONICAL names (`execute`, not
        the accepted alias `shell`), so the generated frontmatter does
        not depend on alias acceptance staying stable.
        """
        content = "---\ntools:\n  - Read\n  - Bash\n  - Grep\n---\nBody"
        result = to_copilot_agent(content)
        assert "read" in result
        assert "execute" in result
        assert "shell" not in result
        assert "search" in result

    def test_write_and_web_and_todo_map_to_canonical(self):
        content = (
            "---\ntools:\n  - Write\n  - WebFetch\n  - WebSearch\n  - TodoWrite\n---\nBody"
        )
        result = to_copilot_agent(content)
        assert "- edit" in result
        assert "- web" in result
        assert "- todo" in result

    def test_mcp_tool_names_pass_through_unchanged(self):
        content = "---\ntools:\n  - Read\n  - mcp__kitt__append_learnings\n---\nBody"
        result = to_copilot_agent(content)
        assert "mcp__kitt__append_learnings" in result

    def test_no_frontmatter(self):
        result = to_copilot_agent("Just instructions")
        assert result == "Just instructions"
        assert "---" not in result

    def test_task_tool_maps_to_agent(self):
        """Claude's `Task` tool (subagent dispatch) becomes Copilot's
        canonical `agent` tool (`custom-agent` is the accepted alias).
        Pinned for DEMO-123 because the crew orchestrator relies on
        this mapping to dispatch the four role subagents on Copilot the
        same way it does on Claude.
        """
        content = "---\nname: dispatcher\ntools:\n  - Task\n  - Read\n---\nDispatch."
        result = to_copilot_agent(content)
        assert "- agent" in result
        assert "Task" not in result  # original Claude name must be gone

    def test_crew_orchestrator_converts_cleanly(self):
        """The kitt-crew orchestrator agent dispatches the four
        role agents. It must survive Copilot conversion with the
        Task -> agent mapping in place and the body intact.
        """
        content = (
            "---\n"
            "name: kitt-crew\n"
            "description: Orchestrate the four-role crew\n"
            "tools:\n"
            "  - Read\n"
            "  - Write\n"
            "  - Glob\n"
            "  - Grep\n"
            "  - Bash\n"
            "  - Task\n"
            "---\n"
            "\n"
            "You are the Crew Orchestrator.\n"
        )
        result = to_copilot_agent(content, "kitt-crew")
        assert "name: kitt-crew" in result
        assert "- agent" in result
        assert "Crew Orchestrator" in result


class TestToCopilotSkill:
    def test_basic_conversion(self):
        content = (
            "---\ndescription: Apply the lens\nargument-hint: [topic]\n---\n"
            "Apply the model to $ARGUMENTS now."
        )
        result = to_copilot_skill(content, "kitt-example")
        parsed = parse_claude(result)
        assert parsed.frontmatter["name"] == "kitt-example"
        assert parsed.frontmatter["description"] == "Apply the lens"
        assert parsed.frontmatter["argument-hint"] == "[topic]"
        assert "$ARGUMENTS" not in result
        assert COPILOT_ARGUMENTS_PHRASE in parsed.body

    def test_description_derived_from_heading_when_absent(self):
        content = "# Check Todos\n\nDo the thing."
        result = to_copilot_skill(content, "kitt-x")
        parsed = parse_claude(result)
        assert parsed.frontmatter["description"] == "Check Todos"

    def test_description_derived_from_first_sentence_when_no_heading(self):
        content = "List outstanding todos and pick one. Then work it."
        result = to_copilot_skill(content, "kitt-x")
        parsed = parse_claude(result)
        assert parsed.frontmatter["description"] == "List outstanding todos and pick one."

    def test_description_never_empty(self):
        result = to_copilot_skill("", "kitt-mystery")
        parsed = parse_claude(result)
        assert parsed.frontmatter["description"].strip()

    def test_argument_hint_omitted_when_absent(self):
        content = "---\ndescription: d\n---\nBody"
        parsed = parse_claude(to_copilot_skill(content, "kitt-x"))
        assert "argument-hint" not in parsed.frontmatter

    def test_allowed_tools_dropped(self):
        content = "---\ndescription: d\nallowed-tools: Skill(x)\n---\nBody"
        result = to_copilot_skill(content, "kitt-x")
        assert "allowed-tools" not in result

    def test_path_replacements_applied_to_body(self):
        content = "---\ndescription: d\n---\nSee ~/.claude/skills/foo/ for details."
        result = to_copilot_skill(content, "kitt-x")
        assert "~/.copilot/skills/foo/" in result
        assert "~/.claude/" not in result

    def test_consider_command_gets_disable_model_invocation(self):
        content = "---\ndescription: d\n---\nBody"
        parsed = parse_claude(to_copilot_skill(content, "kitt-consider"))
        assert parsed.frontmatter["disable-model-invocation"] is True

    def test_wrapper_body_rewritten_to_native_skill_invocation(self):
        content = (
            "---\ndescription: Create or edit Claude Code skills\n"
            "allowed-tools: Skill(kitt-create-agent-skills)\n"
            "argument-hint: [skill description or requirements]\n---\n"
            "Invoke the create-agent-skills skill for: $ARGUMENTS"
        )
        result = to_copilot_skill(content, "kitt-create-agent-skill")
        parsed = parse_claude(result)
        assert "/kitt-create-agent-skills" in parsed.body
        assert "$ARGUMENTS" not in result
        assert "Skill(" not in result
        assert "Claude Code" not in result
        assert parsed.frontmatter["disable-model-invocation"] is True
        # argument-hint still carried over for the wrapper.
        assert parsed.frontmatter["argument-hint"] == "[skill description or requirements]"

    def test_wrapper_without_arguments_has_no_argument_phrase(self):
        content = (
            "---\ndescription: d\nallowed-tools: Skill(kitt-create-hooks)\n---\n"
            "Invoke the create-hooks skill."
        )
        result = to_copilot_skill(content, "kitt-create-hook")
        assert "/kitt-create-hooks" in result
        assert COPILOT_ARGUMENTS_PHRASE not in result
