# Contracts — keeping core features intact through a rewrite

An optimizing pass is a deleting pass. The risk is not that it deletes too
little; it is that it confidently deletes the one line that was load-bearing and
then reports success. Agents will also claim work is done that was not, so the
guard has to be mechanical rather than a promise.

Freeze the contract before editing. Verify it after. Never trust the rewriter's
own account of what it preserved.

## Freeze

Write `state/contracts/<skill>.json` before touching the body:

```json
{
  "skill": "yeet",
  "frozen_at": "2026-08-06",
  "source_sha256": "<hash of SKILL.md at freeze time>",
  "triggers": [
    "user explicitly asks to stage, commit, push and open a PR"
  ],
  "preconditions": [
    "gh installed (gh --version)",
    "gh authenticated (gh auth status)"
  ],
  "steps": [
    "branch as codex/{description} if on the default branch",
    "git add -A after showing status",
    "commit with the terse description",
    "run checks; install deps and retry once on failure",
    "git push -u origin <current branch>",
    "gh pr create --draft --fill"
  ],
  "outputs": [
    "branch codex/{description}",
    "PR titled [codex] {description}",
    "PR body written from a temp file, not an inline string"
  ],
  "hard_constraints": [
    "stop and ask the user if gh is missing or unauthenticated",
    "PR body via file so newlines survive"
  ],
  "safety_content": [
    "stop conditions on missing or unauthenticated gh"
  ]
}
```

Extract by reading, not guessing. Every imperative in the body is a candidate
step; every "must", "never", "always", "stop", "ask first" is a candidate hard
constraint.

## What may change freely

- Prose rewritten as directives. `"The X API is recommended"` → `"Use X"`.
- Duplicated statements collapsed to one source of truth.
- No-ops deleted, once the deletion test confirms them.
- Reference material moved into a sibling file behind a pointer.
- The description rewritten for triggering.
- Formatting, ordering of reference sections, heading structure.

None of these need approval. All of them preserve the contract by construction.

## What needs explicit approval, every time

- Removing a step, precondition, or hard constraint.
- Changing an output shape or filename.
- Merging two skills.
- Deleting a skill.
- Splitting a skill.

Passing evals is not approval. The eval set is a sample; the user's intent is not.

## Never removable, in any pass

- Input validation at a trust boundary.
- Credential, token, and secret handling.
- Confirmation before a destructive or irreversible operation.
- Accessibility requirements.
- Any stop condition — a "stop and ask the user" is doing its job by never firing.

Cutting 95% of a bloated skill set is a good outcome when what you cut is
restatement of things the model already knows. It is a different act entirely
when a safeguard goes with it. Shrinking removes what the model already does;
it never removes what stops the model.

A skill whose entire content is a gate is not bloat. It is the cheapest possible
form of that gate.

## Verify

After the rewrite:

1. Re-derive the contract from the new body.
2. Assert set equality on `triggers`, `steps`, `outputs`, `hard_constraints`.
3. Assert every `safety_content` item still appears.
4. On any mismatch, reject the rewrite and restore. Do not negotiate with it, do
   not patch the diff to make the assertion pass — produce a new attempt.

Sentinel files and self-reported completion are worthless here: anything the
rewriter can write, it can write without doing the work. Hash the source before,
compare structure after, and let the comparison be the authority.

## History

Append to `state/history/<skill>.jsonl` per attempt:

```json
{"version": 3, "parent": 2, "pass_rate": 91.7, "contract_ok": true,
 "desc_tokens": 68, "body_lines": 180, "model": "<model id>",
 "is_current_best": true, "note": "moved cloud-specific steps behind pointers"}
```

Two properties make this worth keeping: a rewrite that scores worse can be
abandoned by version rather than by memory, and pass rates recorded against a
model id reveal when a model update — not an edit — changed the answer. Capability
skills expire that way, and the history is what tells you.
