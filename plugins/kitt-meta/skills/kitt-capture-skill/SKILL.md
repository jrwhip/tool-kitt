---
name: kitt-capture-skill
description: Capture hard-won knowledge as a reusable skill so it is not re-derived in a future context. Use after solving a problem that took real investigation, when the user says to save, capture, or preserve what was just figured out, to "make a skill for this", or to avoid reinventing the wheel. Also use to update an existing skill when fresh findings refine it.
---

<agent_identification>
**Before proceeding, identify which agent you are:**
- **I am Claude Code** → use the [CLAUDE] paths
- **I am GitHub Copilot** → use the [COPILOT] paths (Copilot no longer reads user-level `~/.claude/` paths; removed in Copilot CLI v1.0.36)
- **I am Gemini CLI** → use the [GEMINI] paths

Instructions without markers apply to all agents.
</agent_identification>

<cli_paths>
| Resource | [CLAUDE] | [COPILOT] | [GEMINI] |
|----------|----------|-----------|----------|
| User-level skills | `~/.claude/skills/` | `~/.copilot/skills/` | `~/.gemini/skills/` |
| Project-level skills | `<project-root>/.claude/skills/` | `<project-root>/.github/skills/` (`.claude/skills/` also read) | `<project-root>/.gemini/skills/` |
| User-level commands | `~/.claude/commands/` | none; a skill in `~/.copilot/skills/` is already `/`-invocable | `~/.gemini/commands/` |

Throughout this skill, `SKILLS_HOME` means the user-level skills row for your CLI, and `COMMANDS_HOME` means the user-level commands row.
</cli_paths>

<objective>
Turn a problem that just took significant effort to solve into a reusable skill, or an update to an existing one, so the durable knowledge is preserved and callable later instead of rediscovered from scratch. The unit of value is the lesson, not the play-by-play: what was hard, what the answer turned out to be, the dead ends worth skipping, and the concrete anchors (files, commands, endpoints) that prove it.

This meta-skill ships in the KITT `meta-authoring` pack, so it is reachable wherever that pack is installed. What it produces is scoped: knowledge about one project lands in that project, general knowledge lands in your CLI's user skills dir. See <location>.
</objective>

<relationship_to_create_agent_skills>
Stay in your lane to avoid two skills fighting over one trigger (the `duplicate_skill` trap below):

- **This skill** decides WHAT is worth capturing and WHERE it should live, then crystallizes the lesson. It fires on "capture / save / preserve what we just figured out", "make a skill for this", "so we don't reinvent the wheel".
- **`kitt-create-agent-skills`** is the authority on HOW to author a high-quality SKILL.md: structure, the router pattern, references vs workflows vs templates, validation. It fires on "how do I write / structure / build a skill".

When the captured lesson is large enough to need real structure (multiple workflows, a router, bundled references), hand the authoring mechanics to `kitt-create-agent-skills` rather than restating its guidance here.
</relationship_to_create_agent_skills>

<when_to_capture>
Capture when all of these hold:
- The answer took real work to reach: multiple investigation steps, a non-obvious conclusion, or the correction of a wrong assumption.
- The same problem, or a near neighbor, is plausibly going to come up again.
- The knowledge is durable enough to outlive this conversation.

Trigger phrases from the user: "save this as a skill", "capture this", "preserve this", "make a skill for this", "so we don't reinvent the wheel", "remember how to do this".

Be proactive. When you notice you just spent a long investigation arriving at a non-obvious result, offer to capture it in one sentence rather than waiting to be asked. Create only on a yes, or when the user already asked.

Do not capture: one-off facts with no reuse, anything an existing skill already covers (update that instead), knowledge the model plainly already has, or pure conversation state. Knowledge that a repo already records in its own code or docs belongs there, not in a skill. In a KITT-configured project, durable project state usually belongs in the project's LEARNINGS.md or a handoff, not a new skill; reach for `kitt-whats-next` when the goal is to resume work, and for this skill when the goal is a reusable capability.
</when_to_capture>

<quick_start>
1. Name the lesson in one line. If you cannot, it is probably not skill-worthy yet.
2. Check for an existing skill to update before creating a new one:

```bash
ls ~/.claude/skills/ 2>/dev/null; ls ~/.copilot/skills/ 2>/dev/null; ls ~/.gemini/skills/ 2>/dev/null; ls .claude/skills/ 2>/dev/null; ls .github/skills/ 2>/dev/null
```

3. Decide location per <location>, then copy this skill's bundled template into place. Set `SKILLS_HOME` from <cli_paths> for your CLI:

```bash
SKILLS_HOME=~/.claude/skills              # [CLAUDE]; use ~/.copilot/skills for [COPILOT], ~/.gemini/skills for [GEMINI]
SKILL=<verb-noun-name>
DIR="$SKILLS_HOME/$SKILL"                       # GENERAL knowledge
# DIR="<project-root>/.claude/skills/$SKILL"    # PROJECT-specific knowledge
mkdir -p "$DIR"
cp "$SKILLS_HOME/kitt-capture-skill/templates/captured-skill-template.md" "$DIR/SKILL.md"
```

4. Fill the template, following <quality_bar>.
5. Validate against <success_criteria>.
6. Tell the user the skill name, its path, and the one-line trigger that will fire it.
</quick_start>

<process>
1. **Distill the lesson.** Write the durable takeaway, not the transcript. Answer three things: what the problem was, what the answer is, and what a future session needs in order to not get stuck again. One problem per skill.
2. **Check for duplication.** List existing skills with the quick_start command. If one already covers this area, update it (add a section, sharpen its description) instead of creating a near-duplicate. Two skills fighting over the same trigger is worse than one good skill.
3. **Choose scope and location.** Apply <location>. Project-specific knowledge goes in that project's skills dir; cross-project knowledge goes in your CLI's user skills dir. When unsure, prefer project scope; promoting later is cheap, leaking repo noise into every session is not.
4. **Name it and write the description.** Use a verb-noun name (`debug-*`, `wire-*`, `migrate-*`, `find-*`, `setup-*`). The description is the single most important line: it is what makes the skill auto-fire later. Write it in third person and pack it with the real words a future session would use when it hits this problem. A captured skill with a vague description is effort thrown away.
5. **Write the body.** Pure XML, no markdown headings. Minimum sections: objective, quick_start (the fastest path to the answer), the knowledge with concrete anchors (file:line, exact commands, endpoint paths, code), and a verify step. Write the gotchas and dead ends down explicitly. For anything more elaborate, defer to `kitt-create-agent-skills` per <relationship_to_create_agent_skills>.
6. **Make it verifiable.** Code drifts. Include a verify block with the exact command or check that re-proves the knowledge still holds, so a future session can trust it or detect that it went stale. Record provenance and an absolute date.
7. **Validate and finish.** Run the <success_criteria> checklist. Optionally add a slash command so the skill is easy to call by hand. Set `COMMANDS_HOME` from <cli_paths> for your CLI:

```bash
COMMANDS_HOME=~/.claude/commands          # [CLAUDE]; use ~/.gemini/commands for [GEMINI]. [COPILOT]: skip this step; the skill is already /-invocable from ~/.copilot/skills/
cat > "$COMMANDS_HOME/$SKILL.md" << EOF
---
description: <brief>
allowed-tools: Skill($SKILL)
---
Invoke the $SKILL skill for: \$ARGUMENTS
EOF
```

Then report: name, path, the trigger sentence, and whether it was new or an update.
</process>

<location>
This meta-skill is distributed by the KITT pack. The skill it produces is placed by scope:

| Knowledge is about... | Put the produced skill in | Why |
|---|---|---|
| One repo or workspace: its internals, layout, conventions, quirks | `<project-root>/.claude/skills/<name>/` (`.gemini` for [GEMINI]; [COPILOT] reads project `.github/skills/` and `.claude/skills/`) | Travels with that code; noise everywhere else |
| A tool, language, API, or technique usable anywhere | `SKILLS_HOME/<name>/` (your CLI's user skills dir) | Available in every future context |
| Unsure | project scope first | Cheaper to promote than to un-leak |

In a multi-repo workspace, "project root" means the specific sibling repo the knowledge belongs to (for example `example-monorepo-frontend/`), not the container directory. Use an absolute path so the skill lands in the right repo.
</location>

<quality_bar>
A captured skill earns its keep when it:
- States the lesson, not the play-by-play. Future-you wants the answer and the trap, not the diary.
- Carries concrete anchors: file:line, exact commands, endpoint paths, code. Generic prose is not reusable.
- Names the dead ends. Most of the time saved is the wrong turns avoided.
- Is verifiable: a verify step re-proves it, because the underlying code can change.
- Records provenance and an absolute date so its trustworthiness can be judged later.
- Covers exactly one problem. Split anything broader into separate skills.
</quality_bar>

<anti_patterns>
<pitfall name="diary_not_lesson">Recording the step-by-step of what you did instead of the durable takeaway. Capture the conclusion and the gotchas, not the transcript.</pitfall>
<pitfall name="weak_description">A vague description means the skill never auto-fires and the effort is wasted. Load the description with the real trigger words.</pitfall>
<pitfall name="duplicate_skill">Creating a new skill when an existing one should be updated, or restating `kitt-create-agent-skills`. Two skills competing for one trigger is worse than one.</pitfall>
<pitfall name="unverifiable">Knowledge with no re-check goes stale silently. Always include a verify step and a date.</pitfall>
<pitfall name="repo_trivia">Capturing what a repo already documents in its code or docs, or what belongs in LEARNINGS.md / a handoff. Skills are for hard-won, non-obvious, reusable knowledge.</pitfall>
<pitfall name="wrong_scope">Putting project-specific knowledge in the user-level directory, so every unrelated session sees it. Match scope to <location>.</pitfall>
</anti_patterns>

<success_criteria>
The capture is done when:
- [ ] The lesson fits in one sentence and covers one problem.
- [ ] No existing skill already covers it, or the existing one was updated instead.
- [ ] Location matches scope (project vs user-level) per <location>.
- [ ] Name is verb-noun and matches the directory.
- [ ] Description is third person and rich with real trigger words.
- [ ] Body is pure XML with objective, quick_start, knowledge with concrete anchors, and a verify step.
- [ ] Dead ends and gotchas are written down.
- [ ] Provenance and an absolute date are recorded.
- [ ] The user was told the name, path, and trigger sentence.
</success_criteria>
