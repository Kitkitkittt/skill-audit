# Grilling protocol — deciding whether a skill deserves to exist

Adapted from the `grilling` design-tree pattern: work in rounds, ask the whole
frontier at once, recommend an answer for every question, let the user's answers
reshape what you ask next.

The difference here: you are not exploring a design space, you are prosecuting a
collection. The burden of proof is on the skill.

## The premise

A skill costs three things:

1. **Description tokens on every request, forever** — paid whether it fires or not.
2. **Attention** — 69 candidate descriptions is 69 chances to pick the wrong one.
3. **Maintenance** — every stale line is a future wrong answer delivered confidently.

Against that, its only defence is: it changes what the agent does, in a direction
the user wants, on work the user actually does. "It might be useful" is not a
defence. Skills are not free to hold.

## Rule 1 — find the facts yourself

Before asking anything, you must already know, per skill:

| Fact | Where it comes from |
|---|---|
| description chars, body lines | `report/inventory.json` |
| every rubric violation | `report/audit.json` |
| times it has ever fired | `report/usage.json` |
| prompts in history that should have matched it but didn't | `report/usage.json` |
| which other skills it overlaps, and by how much | `report/audit.json` duplication clusters |
| whether it is shadowed, orphaned, or has broken pointers | `report/audit.json` |
| whether its scripts still run | try one |
| whether the domain still exists in the user's projects | look at the filesystem |

Dispatch subagents for the slow lookups and keep asking the rest of the frontier
while they run. A question that depends on a pending lookup belongs to a later
round.

If you catch yourself asking "do you use X?" when history can answer it, stop.
Ask the version history can't answer: "history says never — was that ever wrong?"

## Rule 2 — cohorts, not a parade

Sixty-nine one-at-a-time questions is a survey nobody finishes. Group first, and
put one question to each group. Cohort rules, in the order you should try them:

**By domain.** Every skill for one platform, tool, or vendor. If the user no
longer touches that platform, the whole cohort retires on one answer. This is the
highest-yield cut and should always be round 1.

**By duplication cluster.** Skills sharing significant text are competing for the
same trigger; the agent cannot reliably choose between them. One question: which
one is real?

**By verdict-if-unanswered.** All never-fired, never-nearly-matched skills form
one cohort with one question. All oversized-description-but-clearly-used skills
form another, whose answer is "shrink" and needs no interview at all — just do it.

**By origin.** Bulk-installed sets tend to live or die together, and the user
usually remembers installing them as a batch rather than choosing each one.

Aim for six to ten questions in round 1, covering all 69 skills. Never open with
the smallest decision.

## Rule 3 — question format

```
❓ **Q<n> — <cohort name or skill name>**: <the question>

📊 <evidence: counts, dates, sizes, overlap percentages — no adjectives>

➡️ <recommended verdict, and the concrete consequence of accepting it>
```

The evidence line is not optional and must be numbers, not characterisation.
"Large and probably unused" is worthless. "640 lines, 512-char description
(~128 tokens/request), 0 invocations in 43,059 stored parts, 71% text overlap
with `nodejs-backend-patterns`" is a case.

The recommendation is not optional either. An interview where the interviewer has
no opinion is a form; the user will disengage. Recommend, then let them overrule.

## Rule 4 — the necessity questions

Ask these of a skill, not of the user, and answer as many as you can yourself.
What remains is the interview.

1. **Has it ever fired?** If never and nothing in history nearly matched it, the
   default is retire. This is the single strongest signal available.
2. **Would its absence be noticed?** If the agent does the same thing without it,
   it is a no-op wearing a skill's clothes. Phase 3 settles this; the user's
   instinct is a useful prior.
3. **Does it teach, or does it restate?** Anything the model already knows, or
   that the repository already says (`package.json` scripts, directory layout,
   `--help` output) is a stale-prone cache, not knowledge.
4. **Is it a capability or a preference?** Capability skills fill a gap in the
   model's knowledge and expire when the model improves — always ask when it was
   last checked against the current model. Preference skills encode the user's
   own conventions and do not expire, but must be tested for fidelity.
5. **Is it a skill or a script?** Rigid, invariant, checkable steps belong in
   code, where they cannot be skipped or negotiated. If the agent has no
   judgement to exercise, it should not be reading prose.
6. **Could it be reached on demand instead?** If the answer is yes, demotion
   recovers its description tokens at zero risk. This is the most common correct
   verdict and the most commonly skipped one.
7. **Does another skill already do this?** Two overlapping skills are worse than
   either alone, because now the trigger is ambiguous.
8. **Is it wrong?** A stale skill is not neutral. It is a confident wrong answer
   waiting for the right prompt.

## Rule 5 — closing the loop

Every skill leaves the grill with exactly one verdict:

| Verdict | Means | Requires approval |
|---|---|---|
| KEEP | earns its cost | no |
| SHRINK | earns it, but bloated | no (compression only) |
| RETARGET | good content, wrong trigger | no (description only) |
| SPLIT | two unrelated jobs in one file | yes |
| MERGE | duplicate of another skill | yes |
| DEMOTE | useful, rarely relevant → on-demand | no |
| RETIRE | delete, keep the evals | yes |

Write `report/VERDICTS.md`: one row per skill, verdict, one-line reason, token
delta. Total the savings at the bottom — the number is the point of the exercise.

Append every verdict to `state/MEMORY.md` with its date and evidence. A grill
that has to be re-run from zero next month will not be re-run at all.

## Anti-patterns

- **Asking permission to think.** "Would you like me to analyse your skills?" — you were invoked to do that.
- **Retiring on a hunch.** No verdict without a number next to it.
- **Accepting "someday".** Push once, then offer demotion. Demotion is what "someday" actually means.
- **Grilling the safeguards.** A skill whose whole content is a stop condition is doing its job by being boring.
- **Deleting during the interview.** Interview first, verdicts second, edits third, and only after approval.
- **Charging the user for phase 3 to settle a decision they already made.** If they want it gone, it's gone; don't run 90 evals to prove them right.
