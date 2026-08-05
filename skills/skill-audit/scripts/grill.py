#!/usr/bin/env python3
"""Build evidence dossiers and a first-round grill from audit + usage data.

This script does not interview the user. It removes the legwork so the agent can:
- ask cohort questions instead of 69 one-at-a-time questions;
- put numbers behind every recommendation;
- write one row per skill to VERDICTS.md as decisions are made.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

# Cohorts are intentionally broad. One answer can retire a whole platform. The
# fallback is the first word in the name, which still produces useful batches.
DOMAIN_RULES = [
    ("figma", re.compile(r"^figma(?:-|$)")),
    ("github-git", re.compile(r"^(?:gh-|git-|yeet$)")),
    ("deployment", re.compile(r"(?:deploy|vercel|netlify|render|cloudflare)")),
    ("notion-linear", re.compile(r"^(?:notion-|linear$)")),
    ("databases", re.compile(r"(?:mongo|postgres|sql|supabase)")),
    ("media-generation", re.compile(r"(?:image|sora|speech|transcrib|tts|stt)")),
    ("documents", re.compile(r"^(?:doc|pdf|slides|spreadsheet|jupyter)")),
    ("testing-browser", re.compile(r"(?:playwright|web-game)")),
    ("security", re.compile(r"^security-")),
    ("opencode-agent-skills", re.compile(r"(?:opencode|skill|chatgpt-apps|openai-docs)")),
    ("9router", re.compile(r"^9router")),
    ("vnstock", re.compile(r"^vnstock")),
]


def domain(name: str) -> str:
    for cohort, pattern in DOMAIN_RULES:
        if pattern.search(name):
            return cohort
    return name.split("-", 1)[0]


def recommend(skill: dict, findings: list[dict], duplicates: list[dict]) -> tuple[str, str]:
    checks = {f["check"] for f in findings}
    signal = skill.get("signal", "unknown")
    if "collision" in checks or "not-loaded" in checks:
        return "MERGE", "same-named copy is shadowed; only one can ever load"
    if signal == "never-relevant":
        return "RETIRE", "never fired and no stored prompt matched its trigger"
    if any(c.get("overlap_pct", 0) >= 60 for c in duplicates):
        other = next(c["other"] for c in duplicates if c.get("overlap_pct", 0) >= 60)
        return "MERGE", f">=60% text overlap with {other}"
    if signal in {"named-never-fired", "relevant-never-fired"}:
        return "RETARGET", f"{signal.replace('-', ' ')}; trigger is not earning its cost"
    if "body-length" in checks:
        return "SHRINK", "body exceeds the focused-skill budget"
    if "desc-length" in checks or "desc-missing-when" in checks:
        return "RETARGET", "description is oversized or lacks an explicit trigger"
    if "rigid-procedure" in checks:
        return "DEMOTE", "invariant procedure belongs in a script or command"
    return "KEEP?", "no static reason to remove it; still unproven without ablation"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", default="report")
    args = parser.parse_args()
    out = Path(args.out)

    required = [out / "inventory.json", out / "audit.json", out / "usage.json"]
    missing = [str(p) for p in required if not p.is_file()]
    if missing:
        sys.exit("run inventory.py, audit.py, and mine_usage.py first; missing: " + ", ".join(missing))

    inventory = json.loads((out / "inventory.json").read_text(encoding="utf-8"))
    audit = json.loads((out / "audit.json").read_text(encoding="utf-8"))
    usage = json.loads((out / "usage.json").read_text(encoding="utf-8"))

    findings_by: dict[str, list[dict]] = defaultdict(list)
    for item in audit["results"]:
        findings_by[item["skill"]].append(item)

    dupes_by: dict[str, list[dict]] = defaultdict(list)
    for cluster in audit["duplication_clusters"]:
        dupes_by[cluster["a"]].append({"other": cluster["b"], **cluster})
        dupes_by[cluster["b"]].append({"other": cluster["a"], **cluster})

    usage_by = {s["name"]: s for s in usage["skills"]}
    dossiers = []
    for entry in inventory["skills"]:
        u = usage_by.get(entry["name"], {})
        fs = findings_by.get(entry["name"], [])
        ds = dupes_by.get(entry["name"], [])
        verdict, reason = recommend(u, fs, ds)
        dossiers.append({
            "name": entry["name"],
            "cohort": domain(entry["name"]),
            "root": entry["root"],
            "description_tokens": entry["desc_tokens_est"],
            "body_lines": entry["body_lines"],
            "invocations": u.get("invocations", 0),
            "prompt_matches": u.get("prompts_matching_keywords", 0),
            "signal": u.get("signal", "unknown"),
            "errors": sum(1 for f in fs if f["severity"] == "error"),
            "warnings": sum(1 for f in fs if f["severity"] == "warn"),
            "checks": sorted({f["check"] for f in fs}),
            "duplicates": sorted(ds, key=lambda d: -d["overlap_pct"])[:3],
            "recommended_verdict": verdict,
            "reason": reason,
        })

    cohorts: dict[str, list[dict]] = defaultdict(list)
    for dossier in dossiers:
        cohorts[dossier["cohort"]].append(dossier)

    # Rank round-one questions by recoverable description cost, then cohort size.
    ranked = sorted(
        cohorts.items(),
        key=lambda item: (-sum(s["description_tokens"] for s in item[1]), -len(item[1]), item[0]),
    )

    payload = {
        "generated_by": "skill-audit/grill.py",
        "summary": {
            "skills": len(dossiers),
            "cohorts": len(cohorts),
            "recommended": dict(Counter(d["recommended_verdict"] for d in dossiers)),
            "description_tokens_per_request": inventory["totals"]["desc_tokens_est"],
        },
        "dossiers": dossiers,
        "cohorts": [
            {
                "name": name,
                "skills": [s["name"] for s in skills],
                "description_tokens": sum(s["description_tokens"] for s in skills),
                "invocations": sum(s["invocations"] for s in skills),
                "signals": dict(Counter(s["signal"] for s in skills)),
                "recommended": dict(Counter(s["recommended_verdict"] for s in skills)),
            }
            for name, skills in ranked
        ],
    }
    (out / "grill.json").write_text(json.dumps(payload, indent=2), encoding="utf-8")

    lines = [
        "# Skill grill — round 1",
        "",
        "Facts are settled below. The user decides whether each domain still belongs in their workflow.",
        "Answer one cohort at a time; do not interview every skill individually.",
        "",
    ]
    for number, (name, skills) in enumerate(ranked, 1):
        tokens = sum(s["description_tokens"] for s in skills)
        invocations = sum(s["invocations"] for s in skills)
        signals = Counter(s["signal"] for s in skills)
        recs = Counter(s["recommended_verdict"] for s in skills)
        names = ", ".join(f"`{s['name']}`" for s in skills)
        recommendation = ", ".join(f"{n} {v}" for v, n in recs.most_common())
        lines += [
            f"## Q{number} — {name}",
            "",
            f"**Question:** Do you still do work that needs this {len(skills)}-skill cohort?",
            "",
            f"**Skills:** {names}",
            "",
            f"**Evidence:** ~{tokens} description tokens/request, {invocations} recorded invocations, "
            f"signals {dict(signals)}.",
            "",
            f"**Recommendation:** {recommendation}. If you answer 'someday', demote instead of keeping "
            "it in the permanent model-visible list.",
            "",
        ]
    (out / "GRILL.md").write_text("\n".join(lines), encoding="utf-8")

    verdict_lines = [
        "# Skill verdicts",
        "",
        "Status: PROPOSED — no delete/merge has user approval yet.",
        "",
        "| skill | cohort | static recommendation | evidence | final verdict | user reason |",
        "| --- | --- | --- | --- | --- | --- |",
    ]
    for d in sorted(dossiers, key=lambda x: (x["cohort"], x["name"])):
        evidence = (
            f"{d['description_tokens']} tok/req; {d['body_lines']} lines; "
            f"{d['invocations']} fires; {d['prompt_matches']} prompt matches; "
            f"{d['errors']}E/{d['warnings']}W"
        )
        verdict_lines.append(
            f"| `{d['name']}` | {d['cohort']} | {d['recommended_verdict']} | "
            f"{evidence} | — | — |"
        )
    verdict_lines += [
        "",
        "## Savings",
        "",
        "Fill final verdicts first. Compute savings only after the user approves them.",
    ]
    (out / "VERDICTS.md").write_text("\n".join(verdict_lines) + "\n", encoding="utf-8")

    print(f"wrote {out / 'grill.json'}, {out / 'GRILL.md'}, and {out / 'VERDICTS.md'}")
    print(f"  {len(dossiers)} skills -> {len(cohorts)} cohort questions")
    print(f"  proposed: {dict(Counter(d['recommended_verdict'] for d in dossiers))}")


if __name__ == "__main__":
    main()
