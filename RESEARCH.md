# Skill Quality Research — 3 AI Engineer talks + online context

Transcripts pulled with `yt-dlp` (auto captions, deduped) → `transcripts/`.

| # | Talk | Speaker | Len | Date |
|---|------|---------|-----|------|
| 1 | Building Great Agent Skills: The Missing Manual | Matt Pocock (aihero.dev) | 20:43 | 2026-06-29 |
| 2 | How I deleted 95% of my agent skills and got better results | Nick Nisi (WorkOS) | 17:42 | 2026-05-30 |
| 3 | Don't Ship Skills Without Evals | Philipp Schmid (Google DeepMind) | 21:45 | 2026-07-14 |

---

## 1. Matt Pocock — The Missing Manual (checklist for skill quality)

Framing: after tutorial hell and framework hell we now have **skill hell** — thousands of downloadable skills, no shared rubric to tell a good one from a bad one. Nobody can look at a skill and say "this does X well, Y badly". His answer is a 4-part checklist. Encoded as a skill in `mattpocock/skills` (talk says `writing-great-skills`; the repo now ships it as `skills/productivity/writing-for-agents/` + `SKILL-MECHANICS.md`).

### 1.1 Trigger — how the skill is invoked
- Any skill can be **user-invoked** (human names it). A skill becomes **model-invoked** by having a `description` in frontmatter, which is a **context pointer** that permanently sits in the agent's context.
- Model-invoked = flexible + agent-discoverable, but costs **context load** (tokens + attention on every request) and adds unpredictability: the model may simply not follow the pointer even when it's perfect for the task. That unpredictability is exactly what forces you into eval work.
- User-invoked (`disable-model-invocation: true`) = zero context load, but costs **cognitive load**: the human becomes the index and must remember what exists.
- Superpowers = mostly model-invoked ("give the agent superpowers"). Matt's set = mostly user-invoked ("I stay in control"). Neither is free — pick deliberately.
- Repo doc adds: **router skill** = one user-invoked skill that names the others, to cure piled-up cognitive load.

### 1.2 Structure — internal layout
- Two content units: **steps** (ordered actions) and **reference** (facts/rules/templates consulted on demand). A skill can be all steps, all reference, or both.
- Keep `SKILL.md` **as small as possible** — cheaper, easier to audit, fewer words to think about.
- **Branch test** for progressive disclosure: reference every branch needs → inline; reference only some branches need → push to a sibling file behind a context pointer ("external reference").
  - `to-prd` has one branch (always writes a PRD) → template stays inline.
  - `domain-modeling` has 2–3 branches (glossary / ADR / neither) → each template moves out behind a pointer.
- Repo doc formalizes an **information hierarchy** ladder: in-file step → in-file reference → disclosed reference. Plus **co-location** (a concept's definition + rules + caveats under one heading) and **sprawl** (document simply too long even when every line is live).

### 1.3 Steering — getting the agent to actually comply
- **Leading words**: compact concepts already in pretraining that pack meaning into one token and get echoed back in the agent's reasoning traces, changing behaviour (`vertical slice`, `fog of war`, `tracer bullets`, `lesson`). Repeat the *word*, never restate the sentence. Verification is free: watch the reasoning trace for your word.
  - "don't code layer by layer, build a small slice first" → **vertical slice**.
  - Coin your own only if you must; a made-up word recruits no priors and you pay in definition tokens.
- **Legwork** and **premature completion**: a step whose completion criterion is fuzzy gets rushed because the agent can see the later steps and wants to be done. Classic case: plan mode's "ask clarifying questions" always under-delivers because "create a plan" is visible.
  - Fix order: sharpen the completion criterion first (cheap, local); only if it stays fuzzy, **split the sequence** so future steps are hidden (Matt split `grill-with-docs` out of `to-prd`). Hiding only works across a real context boundary (hand-off / subagent), not an inline call.
- Repo doc adds **negation** as the failure mode: prohibitions drag the forbidden behaviour into context and make it more available ("don't think of an elephant"). Prompt the positive target instead.

### 1.4 Pruning — failure modes that make skills fat
- **Duplication** → every meaning gets one single source of truth.
- **Sediment** → shared markdown accumulates layers nobody dares delete; irrelevant or stale material. Fix structure first, then delete.
- **No-ops** → instructions the model already obeys by default ("write a long detailed commit message", "write clear high-quality code"). Test = *deletion test*: delete it, does behaviour change? Model-relative, not reader-relative — settle disagreements by running the doc, not by debate. Delete the whole sentence, don't trim words.
- Repo doc adds **cache**: a doc restating what the environment already says (`package.json` scripts, `--help`, directory layout) is a stale-prone cache. Cache only the expensive lookups: unwritten conventions, reasons, gotchas.
- Also **relevance** as a per-line check, and a note that no-op testing also grades leading words (a word too weak to beat the default is a no-op; fix = stronger word).

### 1.5 Summary sweep
trigger (context load vs cognitive load) → structure (branches, steps/reference, disclose) → steering (leading words, legwork) → pruning (sediment, crud, no-ops).

---

## 2. Nick Nisi — deleted 95% of his skills, results improved

Context: DX engineer at WorkOS, 20+ repos across 8 languages, hasn't hand-written code in ~8 months. Two systems:

### 2.1 `case` — inward harness (skill → state machine)
- Started as a Claude skill; as it grew, "context drop" became real — it forgot things and silently skipped tasks ("you told me to, I decided not to").
- Rebuilt on a TypeScript **state machine** with 5 agents: implementer → verifier → reviewer → closer → retro.
- **The agents aren't the point; the gates between them are.** Can't reach reviewer until verifier verifies; reviewer bounces work back; closer only runs when it can produce evidence.
- Agents lie. `.case-tested` sentinel file → Claude just `touch`ed it. Fix: SHA-256 of real test output written into the file and verified → cryptographic proof. Principle: **make doing the work easier than lying about it**.
- Retro agent reads Claude/Codex JSONL transcripts, detects doom loops (same tool 3× with no change, over-parallel calls), and writes **memory files** (general + per-framework: Next.js, TanStack Start …) so the next run avoids the same landmine. Next planned addition: pruning memory over time.

### 2.2 WorkOS CLI — outward (`workos install` sets up AuthKit in <5 min)
- Failure that started it: generated `start.ts` looked right to him and to Claude, but violated TanStack Start's implicit export contract.
- First fix attempt: auto-generate skills from docs. **10,000+ lines** of skills, section-hashed for incremental regeneration. Evals took **68 min/run**, failed repeatedly, retried, eventually passed — huge token burn, worse results.
- Rewrite by hand as **gotchas only**, not comprehensive coverage: **553 lines**, 6 min/run, focused. Deleting ~95% raised performance.
- The kicker, only visible because he measured: one skill scored **77% with the skill vs 97% without it**. He was actively making the model worse.

### 2.3 Lessons
- **Enforce, don't instruct** — code/state machine, not prompt politeness.
- **Guide, don't prescribe** — gotchas at decision points ("in the Next.js proxy you can't call redirects"), not a doc summary.
- **Measure, don't assume** — trust is a pass rate, a hash, a delta score.
- **Replace trust with evidence** — Playwright before/after videos attached to the PR; he won't read the diff until non-code evidence exists.
- **Every failure is a harness bug** — fix the harness, not the output (Ryan Loeppolo / harness engineering).
- For product-facing skills: find what agents reliably get *wrong* about your product and cover only that. The model already knows how to code.

---

## 3. Philipp Schmid — Don't ship skills without evals

Room check: everyone uses coding agents, most use skills, almost nobody has evals.

### 3.1 Two distinctions that drive testing
- **Agents we use** (Claude Code, Cursor, Antigravity): you're the engineer, you notice a missed trigger instantly and re-prompt or slash-command it. **Agents we build**: your customers don't know skills exist and won't write "use the refund skill" — trigger reliability is entirely on you.
- **Capability skills** teach what the model can't do consistently → temporary; evals tell you when to retire. **Preference skills** encode your team's workflow/style → durable; evals protect fidelity against model updates.

### 3.2 Evidence
- **SkillsBench** (arXiv 2602.12670, v4): 87 tasks / 8 domains, paired no-Skills vs curated-Skills across 18 model-harness configs → average pass rate **33.9% → 50.5%** (+16.6 pp, 25.5% normalized gain; range +4.1 to +25.7 pp). **Focused skills with ≤3 modules beat larger/exhaustive bundles.** Smaller models + skills can match larger models without them. Their crawl indexed ~47k unique skills across 6,300+ repos — almost none had evals, most AI-written.
- AI-generated skills can hurt performance; human-written are best. Keep `SKILL.md` **under ~500 lines**.

### 3.3 Eight writing tips
1. Description is the trigger — needs the *what*, the *when*, and the *why/how*; 50% of failures were non-triggering, and a description rewrite alone fixed 5 of 7 failures.
2. **Directives, not essays** — "use `interactions.create()`", not "the Interactions API is recommended".
3. Keep it lean, layer it — description (paid every call) → body (paid on load) → reference files (paid on demand). Multi-cloud deploy → one reference per cloud, never all inline.
4. **Right level of freedom** — goals and constraints, not step 1/2/3. If the exact order matters and never varies, that's a **script**, not a skill.
5. **Don't skip negative cases** — "web development" over-triggers; scope to "React components / Tailwind".
6. **Test early** — 10–20 prompts: ~5 happy path, ~5 should-not-trigger, plus real production traces.
7. **Kill no-ops** (credits Matt) — instructions that don't change default behaviour cost tokens for nothing.
8. **Know when to retire** — run evals with and without; if the model passes without it, delete the skill and keep the eval.

### 3.4 The Gemini Interactions API case study
API shipped after the model's training cutoff → model had no knowledge of it. 117 test cases from real user data + synthetic + reported failures. Assets: one JSON file of cases (`prompt`, `language`, `should_trigger`, `expected_checks`) and one Python script that runs Gemini CLI and parses the output. Most checks are **regex** (right SDK, right model ID, right method, no old patterns) — cheap enough to run many trials, trivially updatable when a model ID changes. LLM-as-judge only for the qualitative stuff (blog: went 66.7% → 100%; talk quotes ~90%).

### 3.5 How DeepMind runs it internally
Evals live **alongside every skill**. Each test: prompt, clean workspace definition, startup commands (installs), script/regex evals over the trace (did the skill trigger? was command X run?), plus LLM-as-judge with expectations. **Evals run on every diff to a skill, and a change can't merge unless it improves or at least holds the pass rate** — regression tests for skills.

### 3.6 Ten eval best practices
description first · directives over passive info · include negative tests · start small (10–20) · **grade outcomes, not paths** (turn 1 vs turn 5 doesn't matter) · **isolated runs** (agents cheat by reading prior chats/executions) · **3–6 trials per case** (non-determinism) · **test across harnesses** (good on Gemini, bad on Codex) · **keep evals after retiring the skill** as sentinels for reintroduction · **run ablations** (with vs without) — the only way to know a skill helps.

Homework he gives: take your most-used skill, write 5 test prompts, mine your own trajectories to find which skills you actually use, remove no-ops, run the ablation.

---

## 4. Online context gathered

| Source | Key takeaway |
|---|---|
| `mattpocock/skills` → `skills/productivity/writing-for-agents/SKILL.md` + `SKILL-MECHANICS.md` | Current, tightened version of talk 1. Adds: information hierarchy ladder, co-location, sprawl, negation, cache-of-environment, router skills, "sharpen the criterion before splitting", `disable-model-invocation` mechanics. Repo: 204k stars, MIT. |
| philschmid.de/agent-skills-tips | The 8 tips, with ✅/❌ examples for descriptions and freedom level. |
| philschmid.de/testing-skills | Full harness walkthrough: prompt-set JSON schema, CLI runner, `CHECK_REGISTRY` regex checks, Pydantic-structured LLM-judge, 10 best practices, "graduate capability evals into regression evals". |
| claude.com/blog/improving-skill-creator… (Mar 2026) | `skill-creator` now writes evals, **benchmark mode** (pass rate + elapsed + tokens), **parallel multi-agent runs in clean contexts**, **blind comparator agents** for A/B (v1 vs v2, skill vs no-skill), and **description optimization** against sample prompts (improved triggering on 5/6 public doc skills). Notes the eventual blur: evals describe the *what*, so evals may become the skill. |
| github.com/anthropics/skills → `skills/skill-creator` | Reusable: `scripts/run_eval.py`, `run_loop.py`, `aggregate_benchmark.py`, `improve_description.py`, `quick_validate.py`, `generate_report.py`, `eval-viewer/`, and `references/schemas.md` with concrete JSON schemas for `evals.json`, `history.json`, `grading.json`, `metrics.json`, `timing.json`, `benchmark.json`, `comparison.json`, `analysis.json`. Steal these schemas rather than inventing new ones. |
| arXiv 2602.12670 (SkillsBench) | Numbers in §3.2. "Focused ≤3 modules beat exhaustive bundles" is the strongest single argument for a shrink-oriented audit. |
| blog.mgechev.com/2026/02/26/skill-eval | `mgechev/skill-eval` — minimal open-source unit-test-for-skills runner, ~1 skill per eval, Gemini API key. |
| opencode.ai/docs/skills | Local platform facts (see §5). |

---

## 5. Local environment facts (measured 2026-08-05)

Skill roots discovered by opencode: `.opencode/skills`, `.claude/skills`, `.agents/skills` (project, walking up to worktree) and `~/.config/opencode/skills`, `~/.claude/skills`, `~/.agents/skills` (global).

- **69 skills total**: 59 in `C:\Users\Admin\.agents\skills`, 10 in `D:\.agents\skills`. None in `~/.config/opencode/skills` or `~/.claude/skills`. Project `D:\SkillAudit` has none.
- **Total `SKILL.md` bytes: 554,507** (~139k tokens if everything loaded — it never is, but it's the maintenance surface).
- **Always-loaded description budget: 20,636 chars (~5.2k tokens) on every single request**, avg 299 chars/skill, **14 descriptions over 400 chars** (worst: `figma-generate-design` at 705).
- **3 skills over 500 lines**: `playwright-interactive` (694), `nodejs-backend-patterns` (640), `figma-create-design-system-rules` (538). Next: `render-deploy` 480, `postgresql-optimization` 405.
- **0 skills are user-invoked.** opencode's frontmatter whitelist is `name`, `description`, `license`, `compatibility`, `metadata` — **`disable-model-invocation` is not supported**; the equivalent lever is `permission.skill` (`allow` / `ask` / `deny`, wildcards) in `opencode.json`, per-agent overridable, plus `tools: { skill: false }`.
- Ablation switch available for free: `permission.skill: { "<name>": "deny" }` hides a skill from the agent without moving files.
- Description hard limit 1–1024 chars; `name` must match the directory and `^[a-z0-9]+(-[a-z0-9]+)*$`; **names must be unique across all roots** (silent collision risk with 2 roots in play).
- Session history: `~/.local/share/opencode/storage/part/**` — 43,059 parts, 11,176 tool calls. Top tools: read 3054, bash 2545, apply_patch 1332, edit 1036, grep 776, glob 452. **`skill` tool invocations: 0.** 379 parts mention "skill", 99 reference `SKILL.md` (mostly manual reads).
  - Meaning: 69 model-invoked skills, ~5.2k tokens of descriptions paid on every request, and **zero recorded autonomous invocations** in local history. That is the single most damning audit finding and the reason to build this.
- Also on the always-loaded budget: `~/.claude/CLAUDE.md` is 8 bytes but `@RTK.md`-includes and the harness injects a large instruction block — the same audit rubric (no-ops, negation, sediment, duplication) applies to `AGENTS.md`/`CLAUDE.md`, and its per-request cost dwarfs any single skill.
- Tooling present: `python 3.14`, `node`, `yt-dlp`, `opencode run --format json` (JSON event stream — parseable trace), `opencode stats`, `opencode export <sessionID>`. No `rg`.
- Existing `skill-creator` locally is the **pre-eval version**: `SKILL.md` + `scripts/init_skill.py`, `quick_validate.py`, `generate_openai_yaml.py`. Missing all of Anthropic's eval machinery (`run_eval.py`, `run_loop.py`, `aggregate_benchmark.py`, `improve_description.py`, `generate_report.py`, `eval-viewer/`, `references/schemas.md`).

---

## 6. Where the three talks agree, disagree, and what that implies

**Agree**
- Smaller wins. Sprawl and comprehensive coverage actively hurt (Nick: 10k→553 lines; SkillsBench: ≤3 modules beats bundles; Philipp: <500 lines; Matt: minimize `SKILL.md`).
- The description/trigger is the highest-leverage surface, and it's the one that costs on every request.
- No-ops are real and worth hunting sentence by sentence (Philipp explicitly credits Matt).
- Layer information; disclose per branch.
- Skills are not permanent — retire on model improvement.
- Give goals/constraints, not procedures; if the procedure is rigid, write a script.

**Disagree / tension**
- Matt avoids model-invocation to *avoid needing evals* (removes a class of problem, pays cognitive load). Philipp treats evals as non-negotiable *because* model-invocation is unavoidable when you ship to others. Resolution: invocation mode determines how much trigger-eval you owe. User-invoked skills need outcome evals only; model-invoked skills additionally need positive **and** negative trigger evals.
- Matt: split a skill to hide future steps and force legwork. Philipp: don't over-specify steps at all. Resolution: splitting is about hiding *goals*, not about adding *procedure*.
- Nick: enforce with code outside the model. Matt: steer with words inside the doc. Resolution: words for judgement, scripts+gates for anything checkable. Nick's cryptographic-proof trick is the extreme end of Matt's "completion criterion".

**Implications for an audit tool**
1. Static audit is cheap and catches most rot (Matt's checklist is largely mechanical) → run it over all 69 skills.
2. Behavioural claims ("this skill helps") are unknowable without a paired **ablation** → expensive, so tier it by real usage.
3. Any rewrite must be gated by evidence, not by the rewriting agent's own say-so (Nick: agents lie; DeepMind: can't merge unless the pass rate holds).
4. Failures should update the auditor's memory, not just the skill (Nick's retro agent).
