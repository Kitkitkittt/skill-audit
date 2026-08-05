# Rubric — what each check means and how to fix it

Every check is mechanical. Severity is about certainty, not importance:

- **error** — unambiguous. Fix without an interview.
- **warn** — probably worth fixing; a human should agree first.
- **review** — the check cannot distinguish prose from a promise. Glance, then decide.

## Trigger checks (billed on every request)

The description is the only part of a skill that costs tokens whether or not the
skill is ever used. With enough skills installed, descriptions alone can exceed
the size of the largest skill body. Fix these first: they are the cheapest wins
available and they compound across every request forever.

| check | means | fix |
|---|---|---|
| `desc-length` | over 400 chars (error over 600) | cut to what it does and when to fire; move detail into the body, which is only paid on load |
| `desc-missing-when` | says what, never when | add an explicit `Use when ...` with the literal words a user would type |
| `desc-missing-negative` | no scope gate | add `Use ONLY when ...` or `Do not use for ...`; broad topics over-trigger and crowd out better matches |
| `desc-first-person` | "I help you…" | third person; the description is read by a model choosing between options, not by a person |
| `name-mismatch` | frontmatter name ≠ directory | make them match, or the skill resolves under a name nobody expects |
| `collision` | same name in two roots | one copy silently never loads. Editing the shadowed copy produces no effect and looks like the model ignoring instructions |

Roughly half of skill failures are non-triggering rather than bad content, and a
description rewrite alone fixes most of them. Always exhaust `RETARGET` before
concluding a skill is useless.

## Structure checks

| check | means | fix |
|---|---|---|
| `body-length` | over 300 lines (error over 500) | focused skills outperform exhaustive ones; move branch-specific material behind pointers |
| `broken-pointer` | body tells the agent to open a file that does not exist | create it or delete the instruction |
| `broken-pointer-dir` | body names a path not on disk | may be illustrative prose; confirm before acting |
| `orphan-asset` | file exists, nothing points at it | add a pointer or delete it. Unreachable assets are pure maintenance cost |

**The branch test** decides what to inline. Reference material every run needs
goes inline. Material only some runs need goes into a sibling file behind a
pointer. A skill with one path through it should keep its template inline; a
skill with three should have three files.

## Content checks

| check | means | fix |
|---|---|---|
| `no-op` | instruction the model already follows | delete the whole sentence, not a few words |
| `negation-without-positive` | prohibition with no target | state the wanted behaviour; naming the unwanted one makes it more available, not less |
| `env-cache` | copies `package.json`, a tree listing, or `--help` | point at the real source; a copy goes stale silently and then lies confidently |
| `stale-marker` | TODO / FIXME / WIP / deprecated | finish or delete |
| `duplication` | text shared with another skill | extract or merge; two overlapping skills make the trigger ambiguous and the agent picks unpredictably |
| `rigid-procedure` | many numbered steps, no branching | invariant checkable steps belong in a script, where they cannot be silently skipped |

### The deletion test

A no-op is defined relative to the model, not the reader. The only valid test:
delete the sentence, run the eval, compare. If behaviour is unchanged, the
sentence was decoration. Do not argue about whether a line is a no-op — run it.

Delete whole sentences. Trimming adjectives off an instruction that does nothing
leaves a shorter instruction that still does nothing.

### Leading words

Compact terms the model already knows (`vertical slice`, `tracer bullet`,
`fog of war`) do more work per token than a paragraph of explanation, because
they recruit knowledge already in the model instead of building it from scratch.
Repeat the term; never restate its definition. Verification is free: look for
your term in the reasoning trace. Absent means it was too weak — that is a no-op
in disguise, and the fix is a stronger word, not more words.

### Premature completion

When later steps are visible, the agent rushes the earlier ones — most visibly on
steps like "ask clarifying questions", which always under-deliver when the next
step is "now write the plan". Fix in this order:

1. Sharpen the completion criterion so "done" is checkable. Cheap and local.
2. Only if it stays fuzzy, split so the later steps are not visible. Splitting
   works only across a real context boundary, not an inline section break.

Sharpening beats splitting; a split skill is two things to maintain.

## Interpreting counts

A check firing on nearly every skill is a norm, not an incident. Report it once
as a pattern and move on. A check firing on three skills out of sixty-nine is a
finding. Ranking by count alone will bury the real problems.
