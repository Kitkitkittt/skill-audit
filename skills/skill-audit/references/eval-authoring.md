# Writing evals for a skill

Ten to twenty cases. Not two, which proves nothing; not two hundred, which never
gets written. Aim for roughly half happy path, half cases that must **not** fire.

Almost no published skill has evals. That is why nobody can tell you whether
their skills help, and why "I deleted most of mine and it got better" keeps being
a surprise.

## The file

`<skill>/evals/evals.json`, following the Anthropic skill-creator shape so the
artifacts stay portable:

```json
{
  "skill_name": "my-skill",
  "evals": [
    {
      "id": "happy-basic",
      "prompt": "what a real user would type, verbatim",
      "should_trigger": true,
      "files": { "src/index.ts": "seed content the run starts from" },
      "expect_regex": ["interactions\\.create\\("],
      "reject_regex": ["generateContent\\("],
      "expect_files": ["out/report.md"],
      "expectations": ["explains why the new method replaces the old one"]
    },
    {
      "id": "negative-adjacent",
      "prompt": "a plausible request this skill must stay out of",
      "should_trigger": false
    }
  ]
}
```

Order of preference for graders, cheapest first:

1. **Trigger** — free, read from the event stream. Costs nothing, catches the most common failure.
2. **Regex** — right SDK, right method, right model id, absence of the old pattern. Cheap enough to run many trials, and trivial to update when an id changes.
3. **File existence** — did it produce the artifact it promised.
4. **Judge (`expectations`)** — only for what regex genuinely cannot see.

A judge on every case makes the suite too slow and too expensive to run often,
and a suite that is not run often is not a suite.

## Sourcing prompts

Real traces first. `report/usage.json` carries the prompts already in local
history plus the keywords each skill claims — the mismatches between those two
are the best negative cases available, because they already happened.

Then: reported failures, the prompt that made you write the skill in the first
place, and synthetic variants for phrasings not yet seen.

Write prompts the way users write them: lowercase, partial, missing context. A
prompt that names the skill is testing nothing except string matching.

## Negative cases matter as much as positive ones

An over-triggering skill is worse than a missing one: it fires on adjacent work,
displaces a better-matched skill, and its wrongness is invisible because
something did happen. A skill scoped to "web development" will fire on
everything; scope it to "React components and Tailwind classes" and it fires when
it should.

Every skill needs at least three negatives:

- an adjacent topic it must ignore;
- a superficially similar request that a different skill owns;
- a request in its domain that is too trivial to justify loading it.

## Grade outcomes, not paths

Whether the agent got there in one turn or five does not matter. Whether it read
the reference file before or after the first edit does not matter. If a check
encodes the route rather than the destination, it will fail on a correct run and
you will "fix" a skill that was working.

Exception: when the path *is* the requirement — "must not push without running
tests" — check the path, because that is the outcome.

## Isolation and trials

- Fresh workspace per trial. Agents will read a previous run's output, a previous
  chat, or a leftover file and appear to succeed on knowledge they were never given.
- Three trials minimum. Non-determinism means a single pass proves nothing and a
  single failure condemns nothing.
- Pin the model. Otherwise a model change looks like a skill regression.
- Test on more than one harness if the skill will run on more than one. Skills
  that work well on one agent can fail on another.

## The ablation is the point

Run every case with the skill and without it:

```bash
python scripts/run_eval.py --skill <name> --arms with,without --trials 3
```

- `without` ≥ `with` → the skill is not helping. This is common and worth looking for directly; a real measured case scored 77% with a skill and 97% without it.
- gap under ~5 points → noise. Add cases or accept that it barely earns its cost.
- `with` clearly ahead → keep it, and you now have a number instead of a belief.

## Keep the evals after retiring the skill

The evals outlive the skill. They are what tells you whether the model still
needs the help — capability skills expire as models improve, and a retired
skill's eval suite is the sentinel that says "still passing without it" or
"bring it back". Delete the skill, keep the file.

## When to re-run

- Every change to a skill. A change that lowers the pass rate does not ship.
- Every model change, for preference skills — those encode your conventions and
  must be protected against drift rather than retired.
- Before deciding a capability skill has expired.
