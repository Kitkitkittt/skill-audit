---
name: skill-audit
description: Audit, grill, and prune agent skills. Use when the user asks to review their skills, find unused or bloated skills, check if a skill is worth keeping, write skill evals, or run a with/without ablation.
---

# Skill Audit

Most skill collections rot. They grow, nobody measures them, and every description
is billed on every request whether or not it ever fires. A skill that never
triggers is a tax; a skill that triggers and misleads is worse than nothing
(one measured case: 77% with the skill, 97% without it).

This skill answers three questions, in this order, cheapest first:

1. **What is actually loaded, and what does it cost?** — deterministic, free.
2. **Does the user still need each one?** — an interview, driven by evidence.
3. **Does it actually help?** — a with/without ablation. Costs tokens; last resort.

Never delete anything yourself. Produce evidence and a recommendation; the user decides.

## Pick the mode

| User wants | Go to |
|---|---|
| "review / audit my skills", "what's bloated" | [Phase 1](#phase-1--inventory-and-static-audit) then stop |
| "do I really need these", "grill me on my skills" | Phase 1 → [Phase 2](#phase-2--the-grill) |
| "is this skill worth keeping", "prove it helps" | Phase 1 → [Phase 3](#phase-3--ablation-and-evals) |
| "write evals for this skill" | Phase 3 only, see `references/eval-authoring.md` |

Do not run a later phase without the earlier one. Phase 2 without Phase 1 is
guessing; Phase 3 without Phase 2 burns tokens on skills the user was about to
delete anyway.

## Phase 1 — inventory and static audit

```bash
python scripts/inventory.py --out report
python scripts/audit.py --out report
python scripts/mine_usage.py --out report      # optional, slow (~90s), high value
```

`inventory.py` reads `opencode debug skill`, which is the set the model actually
sees — after collision resolution. Never glob for `**/SKILL.md` as the source of
truth: a skill can exist on disk and be silently shadowed by a same-named skill
in another root, and globbing hides exactly that bug.

Read `report/AUDIT.md`. Report to the user, in this order:

1. **The bill** — total description characters, and its token cost per request.
   This is paid on every single request, forever, whether any skill fires.
2. **Structural bugs** — collisions, orphans, name mismatches, broken pointers.
   These are unambiguous. Offer to fix them immediately; they need no interview.
3. **The ranked table** — worst offenders by description cost and body size.

Then stop and ask whether to continue to the grill. Do not start rewriting.

`mine_usage.py` reads local session history and reports which skills have ever
fired. Treat a zero-invocation count as a *question*, not a verdict — the user
may have installed a skill last week, or use another harness.

## Phase 2 — the grill

An interview whose only goal is to decide, per skill: keep, shrink, retarget,
split, merge, demote, or retire. Full protocol in `references/grilling.md`.

```bash
python scripts/grill.py --out report            # builds the evidence dossiers
```

Four rules, in priority order:

**Facts are your job, decisions are the user's.** Never ask the user something
the environment can answer. Whether a description exceeds 400 chars, whether a
pointer is broken, whether a skill ever fired, whether two skills duplicate each
other — look it up. Ask only what lives in the user's head: do you still work in
this domain, do you trust this, would you notice if it vanished.

**Batch by frontier, not by skill.** Do not walk 69 skills one at a time; the
user will quit at skill nine. Group them into cohorts that share a single
decision (`references/grilling.md` has the cohort rules), and put one question to
the cohort. One answer can retire eleven skills.

**Every question carries your recommended answer and the evidence behind it.**
Format:

```
❓ **Q1 — <cohort or skill>**: <question>

📊 <the evidence: numbers, dates, counts>

➡️ <your recommendation, and what happens if they accept>
```

**Never accept "I might need it someday."** That is the answer that produced the
mess. Push once: name the last concrete time it was needed, or accept that it is
demotable — reachable when asked for, not loaded on every request. Demotion is
the compromise that costs nothing; offer it before deletion.

The grill ends when every skill has a verdict, and each verdict has a reason
written next to it. Write the results to `report/VERDICTS.md` and append the
decisions to `state/MEMORY.md` so the next run starts from here instead of
re-asking.

## Phase 3 — ablation and evals

Only for skills the grill marked KEEP-but-unproven, or where the user disputes a
retire recommendation. This is the only way to know whether a skill helps.

Cases live in `<skill>/evals/evals.json`. This skill's own suite is in
`evals/evals.json` — read it as the worked example of shape and of how many
negative cases a suite needs.

```bash
python scripts/run_eval.py --skill <name> --arms with,without --trials 3
```

The runner executes each prompt in a fresh temporary directory with
`opencode run --format json`, so the trigger is graded from the event stream
rather than guessed, and no run can read another run's work. The `without` arm
denies the skill via config injection — no files are moved and the user's config
is never modified.

Interpreting results:

- `without` ≥ `with` → the skill is not earning its place. **Keep the evals**, delete the skill; the evals become the sentinel that tells you when to bring it back.
- outcome good, trigger wrong → fix the description only. Half of all skill failures are non-triggering, and a description rewrite is the cheapest possible fix.
- both arms fail → the skill was never the problem. Stop working on it.

## Before you change a single skill

Freeze its contract first: `references/contracts.md`. Extract the triggers,
preconditions, steps, outputs, and hard constraints to
`state/contracts/<skill>.json`, then assert they all survive the rewrite.

Compression is allowed freely: prose to directives, deduplication, deleting
proven no-ops, moving reference material behind a pointer.

**Never delete, in any pass:** input validation at trust boundaries, credential
and secret handling, confirmations before destructive or irreversible operations,
accessibility requirements, and any stop condition. Shrinking a skill means
deleting restatement and no-ops. It never means deleting a safeguard.

Removing a step, changing an output shape, merging skills, or deleting a skill
requires explicit user approval every time — even when the evals pass.

## Reference map

- `references/rubric.md` — the checks, what each one means, and the fix pattern.
- `references/grilling.md` — the interview protocol, cohort rules, and question bank.
- `references/contracts.md` — freezing and verifying a skill's core features.
- `references/eval-authoring.md` — writing the 10–20 cases, including negatives.
- `evals/evals.json` — this skill's own eval suite, usable as a template.
