# skill-audit

An agent skill that audits, interrogates, and prunes your other agent skills.

Skill collections rot. They grow, nobody measures them, and every skill
description is billed on **every request** whether or not the skill ever fires. A
skill that never triggers is a tax. A skill that triggers and misleads is worse
than nothing.

## What it found on the machine it was built on

Run against a real 69-skill installation:

| Measurement | Value |
|---|---|
| Skills loaded | 69 (58 global, 10 project, 1 built-in) |
| Description budget | 20,664 chars ≈ **5,166 tokens billed per request** |
| Skill tool invocations, all local history | **0** (43,059 parts, 11,176 tool calls, 593 prompts) |
| Structural errors | 18 |
| Silently shadowed skill | `find-skills` — byte-identical in two roots, one copy never loads |
| Largest single cohort | 8 figma skills, ~818 tok/request, 0 fires |

The `find-skills` collision is the interesting one: the file exists, looks
correct, and edits to it have no effect whatsoever, because a same-named skill in
another root wins resolution. Globbing `**/SKILL.md` cannot see this. Reading
`opencode debug skill` can.

## Why

Three talks, documented in [`RESEARCH.md`](RESEARCH.md):

- **Matt Pocock — "Building Great Agent Skills: The Missing Manual"** — a four-part checklist: trigger, structure, steering, pruning. Context load vs cognitive load; the branch test; leading words; premature completion.
- **Nick Nisi (WorkOS) — "How I deleted 95% of my agent skills"** — 10,000+ lines down to 553, evals from 68 minutes to 6. One skill scored **77% with it and 97% without it**. Enforce, don't instruct. Measure, don't assume.
- **Philipp Schmid (Google DeepMind) — "Don't Ship Skills Without Evals"** — capability vs preference skills; regex-first grading; a real suite going 66.7% → 100%. DeepMind gates merges on pass rate.

Plus SkillsBench (arXiv 2602.12670): 87 tasks, 33.9% → 50.5%, and the finding
that **focused skills with ≤3 modules beat exhaustive bundles**. Roughly 47,000
skills exist across 6,300+ public repos. Almost none have evals.

## How it works

Three phases, cheapest first. It never deletes anything on its own — it produces
evidence and a recommendation, and you decide.

Run the examples below from the repository root. They share the local `report/`
directory. Keep inventory and usage reports private: they can include local
installation paths and observations from session history.

**Phase 1 — inventory and static audit.** Deterministic and free.

```bash
python skills/skill-audit/scripts/inventory.py --out report
python skills/skill-audit/scripts/audit.py --out report
python skills/skill-audit/scripts/mine_usage.py --out report  # optional, ~90s
```

14 checks across three severities: description length and missing trigger
conditions, name mismatches, collisions, broken pointers, orphaned assets,
no-ops, negation without a positive, cached environment state, staleness markers,
cross-skill duplication by shingling, and rigid procedures that belong in a
script.

**Phase 2 — the grill.** An interview that assigns every skill one of seven
verdicts: keep, shrink, retarget, split, merge, demote, retire.

```bash
python skills/skill-audit/scripts/grill.py --out report
```

It batches skills into cohorts sharing a single decision — 69 skills became 20
questions — and attaches numeric evidence and a recommended answer to each. It
will not accept "I might need it someday"; that answer is what produced the mess.
Demotion is offered before deletion, because it costs nothing.

**Phase 3 — ablation.** The only way to actually know.

```bash
python skills/skill-audit/scripts/run_eval.py --skill <name> --arms with,without --trials 3
```

Every case runs in a fresh temporary workspace so no run can read another run's
work. The `without` arm suppresses the skill through config injection — nothing is
moved on disk and your config is never modified. If `without` ≥ `with`, the skill
is not earning its place.

## Protecting what matters

Compression is a deleting pass, and the risk is deleting the one load-bearing
line and then reporting success. So the contract is frozen before any edit and
verified structurally afterwards — never by asking the rewriter what it preserved.

Never removable, in any pass: input validation at trust boundaries, credential
handling, confirmations before destructive operations, accessibility
requirements, and any stop condition. Shrinking removes what the model already
does. It never removes what stops the model.

## Install

```bash
git clone https://github.com/Kitkitkittt/skill-audit
cp -r skill-audit/skills/skill-audit ~/.config/opencode/skill/
```

Requires Python 3.9+ and `opencode` on PATH.

## Layout

```
skills/skill-audit/
  SKILL.md                      the skill itself
  references/
    rubric.md                   every check, what it means, the fix
    grilling.md                 interview protocol, cohorts, question bank
    contracts.md               freezing and verifying core features
    eval-authoring.md          writing cases, including negatives
  scripts/
    inventory.py               what is loaded and what it costs
    audit.py                   the 14 static checks
    mine_usage.py              what has ever actually fired
    grill.py                   cohorts, dossiers, verdicts
    run_eval.py                with/without ablation runner
  evals/evals.json             its own suite: 7 positive, 5 negative
RESEARCH.md                    the three talks, in depth
DESIGN.md                      architecture and decisions
transcripts/                   cleaned source transcripts
```

## License

MIT
