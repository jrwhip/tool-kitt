---
name: wopr-wargame
description: "Turn an idea into an executable requirements set through a guided wargame session. Use when brainstorming requirements, rubber-ducking a new app idea, defining acceptance criteria for a feature, building a product backlog, or turning an idea into REQ files the crew can execute."
---

<purpose>
Requirements are the highest-leverage input in AI-assisted development: downstream agents execute almost everything, but only as well as the requirements permit. This skill runs the elicitation session that produces them. The operator makes every scoping decision; the skill's job is to ask the questions, generate the candidates, force the collisions, and write the files.
</purpose>

<session_flow>
Three phases, operator-gated. Announce phase transitions in one line. The operator can end any phase early; never end one for them.

**1. Diverge (the spaghetti wall).** Interview the operator and generate candidates side by side. Cover, in whatever order the conversation leads: users and what each is trying to do; core scenarios and the edge scenarios around them (disconnects, races, abuse, empty states); non-functional constraints (auth model, persistence, latency, deploy target); integrations. Batch related questions (up to 4 per round, AskUserQuestion when options are real, free text otherwise); one topic per round. Generate aggressively between rounds: propose candidate requirements the operator did not mention, including ones you expect them to reject. Run at least one adversarial pass before leaving the phase: invert ("what would guarantee this fails or embarrasses us?") and second-order ("what does each feature force us to build next?"). Do not filter during divergence; everything lands on the candidate list.

**2. Converge (the hammering).** Dedupe and merge candidates. Collide overlapping ones and make the operator pick. Classify every survivor: in scope, deferred, or excluded, and record WHY for every exclusion; excluded scope with reasons is a first-class output the crew's intake reads. Order the in-scope set by dependency, then priority. Size each requirement to one crew run; split anything bigger.

**3. Formalize.** Delegate to the wopr-draft-req skill: it asks where requirements live (REQ files, Jira, or GitHub issues) before anything is written, owns the document format and the criteria quality bar, and handles any post-sign-off publish step. One document per in-scope requirement (KEY: short project code the operator picks). Then write or update the Requirements Baseline table in the project's tracking document, statuses all Pending, deferred and excluded items listed under it with their reasons. Present the set for operator review; revise until they sign off.
</session_flow>

<rules>
- The operator decides scope; you decide phrasing. Never silently drop or add a requirement after convergence.
- Ask questions whose answers change the requirements. Skip anything derivable from what the operator already said.
- A candidate the operator rejects goes to excluded-with-reason, not to deletion; rejections are scope information.
- No implementation design in REQ files: no file names, no schema sketches, no library choices. That is the crew's scout and coder's territory.
</rules>
