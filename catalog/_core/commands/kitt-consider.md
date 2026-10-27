---
description: Apply a named decision framework to the current problem or discussion
argument-hint: [framework] [optional subject]
---

<objective>
Apply the decision framework named by the first word of $ARGUMENTS to the rest of
$ARGUMENTS, or to the current discussion when no subject is given.

If $ARGUMENTS is empty, or the first word matches no framework below, print the
framework list from `<frameworks>` (name plus its "fits when" line) and stop. Do
not guess which framework was meant.
</objective>

<routing>
Match the first word case-insensitively against the framework names below.
Accept the listed aliases. Everything after the first word is the subject.
</routing>

<frameworks>

**10-10-10** (aliases: 10-10-10, 101010)
Fits when: a choice feels urgent and the urgency may be distorting it.
Output: **Decision**, then per option a 10 minutes / 10 months / 10 years line,
then **Time Conflicts** (where short-term and long-term disagree), then
**Recommendation** weighted toward the longer horizons.

**5-whys** (aliases: 5-whys, 5why, why)
Fits when: a problem keeps recurring and the fix keeps addressing a symptom.
Output: **Problem**, then **Why 1** through **Why N** each digging into the prior
answer, then **Root Cause**, then **Intervention** (a specific action at the root).
Stop when the answer becomes actionable, not at a fixed count.

**eisenhower-matrix** (aliases: eisenhower, eisenhower-matrix, matrix)
Fits when: a list of work is overwhelming and needs triage.
Output: four quadrants, **Q1 Do First** (important + urgent, with next actions),
**Q2 Schedule** (important + not urgent, with when and why), **Q3 Delegate** (not
important + urgent, with who or how to minimize), **Q4 Eliminate** (explicitly
droppable), then **Immediate Focus** in one sentence.

**first-principles** (aliases: first-principles, fp, fundamentals)
Fits when: the current approach is inherited convention and may not be necessary.
Output: **Current Assumptions** each marked true / false / partially after
challenge, **Fundamental Truths** with why each is irreducible, **Rebuilt
Understanding** derived only from those truths, **New Possibilities** that the
discarded assumptions were hiding. No reasoning by analogy.

**inversion** (aliases: inversion, invert, backwards)
Fits when: planning for success has produced a vague plan and the risks are unlisted.
Output: **Goal**, **Guaranteed Failure Modes** each paired with a specific
avoidance action, **Anti-Goals (Never Do)**, **Success By Avoidance**, and
**Remaining Risk** after the obvious failures are removed.

**occams-razor** (aliases: occams-razor, occam, razor, simplest)
Fits when: several explanations fit and one of them is quietly elaborate.
Output: **Candidate Explanations** each with the assumptions it requires, an
**Evidence Check** marking each assumption supported or unsupported, the
**Simplest Valid Explanation**, and **Why This Wins**. It must still fit all facts.

**one-thing** (aliases: one-thing, onething, leverage)
Fits when: many tasks compete and none obviously comes first.
Output: **Goal**, **Candidate Actions** each with its downstream effect, **The One
Thing**, **Why This One** (the causal chain that makes other work easier or
unnecessary), and a concrete **Next Action**.

**opportunity-cost** (aliases: opportunity-cost, opportunity, cost)
Fits when: something looks affordable and its real cost has not been named.
Output: **Choice**, **Resources Required** (time, money, energy/attention, other),
**Best Alternative Uses** of those same resources with their value, **True Cost**
stated as what is being given up, and a **Verdict**. Compare against the best
alternative, not an arbitrary one.

**pareto** (aliases: pareto, 80-20, 8020)
Fits when: a long list of factors needs to shrink to the ones that move the result.
Output: **Vital Few** (roughly the 20 percent driving most of the outcome) each
with why it matters and a specific action, **Trivial Many** to defer or ignore,
and a one-sentence **Bottom Line**.

**second-order** (aliases: second-order, second, consequences)
Fits when: an action's immediate effect is clearly good and the follow-on is unexamined.
Output: **Action**, **First-Order Effects**, **Second-Order Effects** written as
effect leads to consequence, **Third-Order Effects** when significant, **Delayed
Consequences**, and a **Revised Assessment** of whether it is still worth it.

**swot** (aliases: swot)
Fits when: a position or project needs a structured read before committing to strategy.
Output: **Strengths** and **Weaknesses** (internal, controllable) and
**Opportunities** and **Threats** (external, not controllable), each item paired
with how to leverage, mitigate, capture, or defend; then **Strategic Moves** as SO,
WO, ST, and WT pairings. Categorize internal versus external correctly.

**via-negativa** (aliases: via-negativa, negativa, subtract, remove)
Fits when: the instinct is to add something and removal has not been considered.
Output: **Current State**, **Subtraction Candidates** each with the reason and the
resulting improvement, **Keep (Passed the Test)** with the genuine value of each,
**After Subtraction** describing the leaner state, and **What to Say No To**.

</frameworks>

<rules>
- Use the requested framework only. Do not blend two, and do not substitute one
  you consider better; say so in one line if you disagree, then comply.
- Apply the framework to real specifics from the subject or conversation.
  Generic filler that would fit any topic is a failed run.
- Follow the output structure above. Headings are the contract; the content under
  them is yours.
- State the framework's own conclusion even when it is inconvenient. A framework
  that always agrees with the current plan was not actually applied.
</rules>
