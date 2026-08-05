# SkillAudit — design for a skill that audits, understands, and optimizes skills

Working name: **`skill-audit`** (opencode-native). Alternates considered: `skill-evals`, `skillsmith`.
Grounding: `RESEARCH.md` (3 talks + SkillsBench + Anthropic/philschmid prior art + measured local state).

---

## 0. The problem, in numbers, on this machine

| Measure | Value |
|---|---|
| Skills loaded by opencode | **69** (58 `~/.agents/skills`, 10 `D:\.agents\skills`, 1 built-in) |
| `SKILL.md` maintenance surface | 554 KB (~139k tokens) |
| Description text on **every** request | **20,676 chars ≈ 5.2k tokens** |
| Descriptions over 400 chars | 14 (max 705) |
| Skills over 500 lines | 3 (694 / 640 / 538) |
| Recorded autonomous `skill` tool invocations in 43,059 stored parts | **0** |
| Silent name collisions | **1** (`find-skills` in both roots, byte-identical — project shadows global) |
| Skills with evals | 0 |

So: a permanent ~5.2k-token tax per request, 69 candidate distractors, and no evidence any of it fires or helps. Nick's 77%-vs-97% result says the null hypothesis isn't "harmless" — it's "possibly harmful". That is the case for building this.

## 1. Scope and non-goals

**Does**
1. **Inventory** every skill opencode actually resolves (not what's on disk).
2. **Audit** each one statically against a rubric derived from the three talks.
3. **Measure** the ones that matter behaviourally: does it trigger, does it help, does it hurt (ablation).
4. **Optimize** under a gate: no change ships unless the pass rate holds or improves and the frozen contract survives.
5. **Remember** verdicts so the next run doesn't re-litigate.

**Does not**: write new skills from scratch (`skill-creator` owns that), touch application code, or auto-delete anything.

## 2. Shape: one user-invoked skill, three tools, four scripts

The auditor must not add to the problem it measures. So: **one skill, one short description, deterministic work in scripts.**

```
skill-audit/
  SKILL.md                    # <120 lines, description <200 chars
  scripts/
    inventory.py              # opencode debug skill --> normalized JSON
    audit.py                  # static rubric --> AUDIT.md + audit.json
    mine_usage.py             # storage/part/** --> usage.json (ranking + eval seeds)
    run_eval.py               # behavioural evals + ablation --> results.json
  references/
    rubric.md                 # the 14 checks, with fix patterns
    contracts.md              # what "core feature" means + freeze format
    eval-authoring.md         # how to write the 10-20 prompts
  state/                      # gitignored; per-skill contracts, history, memory
```

Phase 1 (`inventory` + `audit` + `mine_usage`) is **free and deterministic** — no model calls. Phase 2 (`run_eval`) costs tokens and is opt-in per skill. This split matters: the static pass covers all 69 for ~0 cost, and the expensive pass runs only where usage data says it's worth it.

## 3. Inventory — use the platform, don't reimplement it

`opencode debug skill` returns JSON `[{name, description, location, content}]` for exactly the set the model sees, including built-ins, **after** collision resolution. Globbing `**/SKILL.md` would have missed the `find-skills` shadowing entirely (both files exist; only one loads).

`inventory.py` = that JSON + per-skill derived fields: `desc_chars`, `body_lines`, `body_bytes`, `sibling_files[]`, `pointers[]` (relative paths named in the body), `root` (project/global/builtin), `shadowed_by`.

Cross-check against disk to report **orphans** (on disk, not loaded) and **shadows** (loaded from the other root than expected).

## 4. Static audit — 14 checks, all mechanical or near-mechanical

Derived from Matt's checklist, Philipp's tips, and SkillsBench. Each check emits `{skill, check, severity, evidence, fix, est_tokens_saved}`.

**Trigger (paid every request — highest leverage)**
1. `desc-length` — >400 chars warn, >600 error. Budget view: this skill's share of the 5.2k.
2. `desc-missing-when` — no "Use when" / "Trigger" / condition clause → the description says what but not when.
3. `desc-missing-negative` — no scope gate ("Use ONLY when", "Do not use for") on a broad-topic skill → over-trigger risk (Philipp's "web development" case).
4. `desc-first-person` — "I help you…" instead of third person.
5. `name-mismatch` — frontmatter `name` ≠ directory name.
6. `collision` — same name in two roots → silent shadowing. **Already firing once.**

**Structure**
7. `body-length` — >500 lines error (SkillsBench), >300 warn.
8. `broken-pointer` — body references `scripts/x.py` / `references/y.md` that doesn't exist.
9. `orphan-asset` — sibling file no pointer reaches → dead weight or missing pointer.
10. `inline-branch-reference` — long template/table (>40 lines) inside a body that has ≥2 branches → candidate for disclosure. Heuristic, flagged for human judgement, never auto-applied.

**Content**
11. `no-op` — sentence matches the no-op corpus ("write clear code", "be thorough", "use best practices", "ensure high quality", "think step by step", "be careful"). Flag, then *prove* by deletion test in phase 2.
12. `negation-without-positive` — "don't/never/avoid X" with no adjacent positive target. Matt's elephant.
13. `env-cache` — restates `package.json` scripts, directory listings, or `--help` output → stale-prone cache of the environment.
14. `duplication` — 8-gram shingle hashing across all 69 bodies; report clusters ≥3 shared shingles. Cross-skill duplication is the merge/extract signal.

Plus `rigid-procedure`: ≥5 numbered steps with no branching and no judgement verbs → Philipp's "that's a script, not a skill".

Output: `report/AUDIT.md` (human) + `report/audit.json` (machine) + a **budget table** sorted by description tokens, because that's the bill you pay whether or not anything fires.

## 5. Usage mining — how to spend the eval budget

`mine_usage.py` walks `~/.local/share/opencode/storage/part/**` (43,059 files here, ~90s in Python):
- count `type:"tool"` parts by `tool` name → what actually gets used;
- count `tool == "skill"` and `state.input.name` → **which skills fire** (currently 0, itself the finding);
- collect user-message text as a corpus of **real prompts** → seeds for eval cases, per Philipp's "mine your trajectories";
- match each skill's trigger keywords against that corpus → **should-have-fired-but-didn't** (a trigger bug) vs **never-relevant** (a retire candidate).

This is what makes the tiering honest: rank by (would-be-relevant frequency × description cost), eval the top N, static-audit the rest.

## 6. Contract freeze — how "core features are kept intact"

The failure mode of any optimizing agent is confident deletion. Nick's rule: agents lie. So before any edit, `audit.py` extracts a **contract** to `state/contracts/<skill>.json`:

```json
{
  "skill": "yeet",
  "frozen_at": "2026-08-06",
  "triggers": ["explicit request to stage, commit, push, open PR", "gh CLI"],
  "preconditions": ["gh installed", "gh auth status succeeds"],
  "steps": ["branch if on default", "stage all", "commit terse", "run checks", "push -u", "gh pr create --draft"],
  "outputs": ["branch codex/{desc}", "commit {desc}", "PR titled [codex] {desc}", "PR body from temp file"],
  "hard_constraints": ["stop if gh missing", "PR body via file not inline \\n"],
  "safety_content": []
}
```

**Allowed without asking**: lossless compression (prose→directive, dedupe, delete proven no-ops), moving reference material behind a pointer, description rewrites, adding negative scope.
**Requires explicit approval**: removing a step/precondition/constraint, changing an output shape, merging skills, deleting a skill, touching anything tagged `safety_content`.

`safety_content` is a hard allowlist that the shrink pass never touches: input validation at trust boundaries, auth/secret handling, destructive-op confirmations, accessibility requirements, and anything the skill marks as a stop condition. Nick deleted 95% *of doc summaries*; he did not delete gates.

After a rewrite, a diff check re-derives the contract from the new body and asserts set-equality on triggers/steps/outputs/constraints. Mismatch → reject the rewrite, don't argue with it.

## 7. Behavioural evals — Anthropic's schema, opencode's runner

Reuse `anthropics/skills` schemas verbatim (`evals.json`, `history.json`) so artifacts stay portable. Per skill:

```
<skill>/evals/evals.json        # 10-20 cases: ~5 happy, ~5 must-not-trigger, rest from real traces
<skill>/evals/history.json      # version, parent, pass_rate, is_current_best
```

Each case: `{id, prompt, should_trigger, expected_output, files[], expectations[]}`.

Runner, per case per trial:
```
opencode run --format json --agent build --dir <fresh temp workspace> "<prompt>"
```
- `--format json` gives a parseable event stream → **did the `skill` tool fire, with which name** (trigger grading, free, no judge).
- fresh temp `--dir` per trial → isolation; no cross-contamination, no reading prior work (Philipp: agents cheat).
- `--pure` to exclude plugin noise; pin `-m` so model drift doesn't masquerade as a skill change.
- regex/file-existence checks first; LLM-judge only for the qualitative expectations.
- **3 trials** per case minimum.

**Ablation** is the whole point, and opencode gives it for free:
```json
{ "permission": { "skill": { "*": "allow", "<name>": "deny" } } }
```
injected via `OPENCODE_CONFIG_CONTENT` for the "without" arm. Verified in the binary: skill listing filters on `evaluate("skill", name, permission) !== "deny"`, and the guidance block is dropped entirely when `skill:*` is denied — so the description cost disappears too. No file moves, no mutation of the user's config.

Four arms per skill: `with` / `without` / (`with`, description-only rewrite) / (`with`, shrunk body). Verdict from the delta, not from the rewriter's opinion.

Cost control: 15 cases × 3 trials × 2 arms = 90 runs per skill. Feasible for 10 skills, not for 69 — hence the usage tiering. Small/cheap model for the executor; the auditor never grades its own work with the same model that produced it.

## 8. Verdicts

Per skill, one of:

| Verdict | Trigger condition |
|---|---|
| **KEEP** | with > without, contract clean, within budget |
| **SHRINK** | with > without but body >300 lines or ≥3 no-ops proven |
| **RETARGET** | outcome fine, trigger wrong (missed positives or fired on negatives) → description-only fix |
| **SPLIT** | ≥2 unrelated branch clusters, or premature completion on a fuzzy step |
| **MERGE** | duplication cluster with another skill ≥60% shingles |
| **DEMOTE** | useful but rarely relevant → `permission.skill: ask`, or convert to a command; recovers its description tokens |
| **RETIRE** | without ≥ with (Nick's 97%-vs-77%), or never relevant in trace history. **Keep the evals** as reintroduction sentinels |

Every verdict carries: evidence lines, token delta, and — for anything destructive — a required human ack.

`state/MEMORY.md` records each decision with its evidence so re-runs are incremental (Nick's retro agent, applied to the auditor itself).

## 9. Rubric score (for the report, not for gating)

Five axes, 0–4: **Trigger**, **Structure**, **Steering**, **Leanness**, **Evidence**. Gating is always the eval delta + contract check; the score is just how the report sorts 69 rows.

`Evidence` is deliberately an axis: today all 69 skills score 0 on it.

## 10. Rollout

- **v0 (today, no model calls)** — `inventory.py` + `audit.py` + `mine_usage.py`. Deliverable: `AUDIT.md` over 69 skills, budget table, the collision, the orphan, the 14 oversized descriptions, the 3 oversized bodies, duplication clusters. Fix the collision and the descriptions immediately; those are pure wins.
- **v1** — contracts frozen for the top 10 by usage; `evals.json` authored; ablation run. Expect several RETIREs given 0 recorded invocations.
- **v2** — gated optimize loop (`run_loop.py`-style), `history.json` tracking, re-run on model change so preference skills are protected against drift (DeepMind's regression posture).
- **v3 (maybe)** — extend the same rubric to `AGENTS.md` / global instruction blocks. Their per-request cost exceeds every skill combined, and no-ops/negation/sediment apply identically.

## 11. Known risks

| Risk | Mitigation |
|---|---|
| Auditor audits itself, recurses | Exclude own name; single-pass, no self-invocation |
| Shrink deletes a real safeguard | `safety_content` allowlist + contract set-equality assert |
| Eval leakage via reused sessions | Fresh `--dir` per trial, no `--continue`, `--pure` |
| Cost blowup | Static tier for all; behavioural tier top-N only; 3 trials; cheap executor |
| Ablation switch doesn't actually work | Verified in binary (permission filter + guidance drop); still assert empirically with a canary skill before trusting results |
| Rewrites that pass evals but read worse | Human ack for merges/deletes; diffs surfaced, not silently applied |
| Model update invalidates verdicts | Verdicts stamped with model+version; re-run required on change |

## 12. Open decisions

1. **Ship as a skill or a command?** A user-invoked command costs 0 description tokens; but opencode ignores `disable-model-invocation`, so as a skill it must pay ~150 chars forever. Leaning: **skill with a tight description** (discoverability wins) plus `permission.skill` documented as the off switch.
2. **Eval budget.** How many skills get behavioural evals in v1 — 5 or 10 — and which executor model.
3. **Blast radius.** Audit both roots (69) or global-only first? Both is more useful; `D:\.agents\skills` is where the vnstock/mongodb set lives and is the more likely retire pool.
