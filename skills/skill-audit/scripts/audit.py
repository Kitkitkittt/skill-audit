#!/usr/bin/env python3
"""Static rubric over report/inventory.json -> report/audit.json + report/AUDIT.md.

Deterministic and free: no model calls. Every finding carries evidence and a fix.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
from collections import defaultdict
from pathlib import Path

DESC_WARN, DESC_ERROR = 400, 600
BODY_WARN, BODY_ERROR = 300, 500

WHEN_MARKERS = (
    "use when", "use only", "trigger", "when the user", "when you", "when a ",
    "for when", "invoke when", "use this when", "use for", "whenever",
)
NEGATIVE_MARKERS = (
    "use only", "do not use", "don't use", "not for", "avoid using",
    "does not cover", "out of scope", "never use", "only when", "not when",
)
FIRST_PERSON = re.compile(r"\b(?:I|I'll|I will|I can|my)\b")

NO_OP_PATTERNS = [
    (r"\bwrite (?:clear|clean|high[- ]quality|good|readable|idiomatic) code\b", "restates the default"),
    (r"\bfollow best practices\b", "no operational content"),
    (r"\bbe (?:thorough|careful|precise|concise|helpful|accurate)\b", "unmeasurable directive"),
    (r"\bthink (?:step[- ]by[- ]step|carefully|hard)\b", "already default behaviour"),
    (r"\bensure (?:high )?quality\b", "unmeasurable directive"),
    (r"\bmake sure (?:it|the code) works\b", "restates the task"),
    (r"\bwrite (?:good|meaningful|descriptive) (?:commit messages|tests)\b", "restates the default"),
    (r"\buse (?:proper|appropriate) (?:naming|formatting)\b", "restates the default"),
    (r"\bpay attention to detail\b", "unmeasurable directive"),
    (r"\bdo not (?:hallucinate|make things up)\b", "unenforceable"),
]
NO_OP_RE = [(re.compile(p, re.IGNORECASE), why) for p, why in NO_OP_PATTERNS]
# "a script would be helpful" describes; "be helpful" instructs. Only the
# instruction is a no-op, so skip hedged and descriptive moods.
HEDGED_RE = re.compile(
    r"\b(?:would|could|might|may|should|can|is|are|was|were|seems|tends)\s+(?:\w+\s+){0,2}?be\b",
    re.IGNORECASE,
)

NEGATION_RE = re.compile(r"\b(?:don't|do not|never|avoid|must not|should not)\b", re.IGNORECASE)
POSITIVE_RE = re.compile(
    r"\b(?:instead|rather than|prefer|use|always|only|write|call|run|ask|stop|keep|"
    r"replace|switch|choose|pick|treat|point|report|follow|include|limit|restrict|"
    r"scope|set|add|put|place|store|return|emit|output|define|declare|pass|wrap|"
    r"list|start|begin|first|then)\b",
    re.IGNORECASE,
)
# A prohibition that names its own escape hatch is already steering positively.
CONDITIONAL_RE = re.compile(r"\b(?:unless|until|if|when|except|without)\b", re.IGNORECASE)
# Stop conditions and safety gates are supposed to be prohibitions. Leave them alone.
SAFETY_RE = re.compile(
    r"\b(?:secret|credential|token|password|api key|destructive|irreversible|"
    r"force[- ]push|rm -rf|delete|drop table|production|confirm|approval|"
    r"permission|auth|sudo|overwrite)\b",
    re.IGNORECASE,
)
MAX_PER_CHECK = 5

ENV_CACHE_RE = [
    (re.compile(r"^\s*[│├└|+`-]{2,}.*\.(?:ts|js|py|json|md)\s*$", re.MULTILINE), "directory tree listing"),
    (re.compile(r"\"scripts\"\s*:\s*\{", re.IGNORECASE), "package.json scripts copied inline"),
    (re.compile(r"^\s*(?:-h|--help)\b.*$", re.MULTILINE), "--help output copied inline"),
]

STALE_RE = re.compile(r"\b(?:TODO|FIXME|XXX|WIP|deprecated|coming soon|not yet implemented)\b", re.IGNORECASE)
JUDGEMENT_RE = re.compile(
    r"\b(?:if|when|unless|otherwise|prefer|decide|choose|depending|either|consider)\b", re.IGNORECASE
)
NUMBERED_RE = re.compile(r"^\s{0,3}\d+[.)]\s+\S", re.MULTILINE)
SHINGLE_SIZE = 8
DUP_MIN_SHARED = 12
DUP_MIN_OVERLAP = 15


def sentences(text: str) -> list[str]:
    stripped = re.sub(r"```.*?```", " ", text, flags=re.DOTALL)
    return [s.strip() for s in re.split(r"(?<=[.!?])\s+|\n", stripped) if s.strip()]


def shingles(text: str) -> set[str]:
    words = re.findall(r"[a-z0-9]+", text.lower())
    if len(words) < SHINGLE_SIZE:
        return set()
    return {
        hashlib.blake2b(
            " ".join(words[i : i + SHINGLE_SIZE]).encode(), digest_size=8
        ).hexdigest()
        for i in range(len(words) - SHINGLE_SIZE + 1)
    }


def finding(skill, check, severity, evidence, fix, saved=0):
    return {
        "skill": skill,
        "check": check,
        "severity": severity,
        "evidence": evidence,
        "fix": fix,
        "est_tokens_saved": saved,
    }


def audit_skill(entry: dict) -> list[dict]:
    name = entry["name"]
    desc = entry["description"]
    body = entry.get("body", "")
    out: list[dict] = []

    # --- trigger: billed on every request, highest leverage -------------------
    if entry["desc_chars"] > DESC_ERROR:
        out.append(finding(
            name, "desc-length", "error",
            f"{entry['desc_chars']} chars (~{entry['desc_tokens_est']} tokens) on every request",
            f"cut to <{DESC_WARN} chars: what it does + when to trigger, nothing else",
            saved=round((entry["desc_chars"] - DESC_WARN) / 4),
        ))
    elif entry["desc_chars"] > DESC_WARN:
        out.append(finding(
            name, "desc-length", "warn",
            f"{entry['desc_chars']} chars (~{entry['desc_tokens_est']} tokens) on every request",
            f"trim toward {DESC_WARN} chars",
            saved=round((entry["desc_chars"] - DESC_WARN) / 4),
        ))

    low = desc.lower()
    if not any(m in low for m in WHEN_MARKERS):
        out.append(finding(
            name, "desc-missing-when", "error",
            "description states what it does but never when to trigger",
            "add an explicit 'Use when ...' clause with the literal words a user would type",
        ))
    if len(desc) > 120 and not any(m in low for m in NEGATIVE_MARKERS):
        # Almost every skill omits this, so it is a norm rather than an
        # incident. Only long descriptions get a warning; the rest are noted.
        out.append(finding(
            name, "desc-missing-negative", "warn" if len(desc) > 250 else "review",
            "no scope gate; nothing stops it firing on adjacent topics",
            "add 'Use ONLY when ...' or 'Do not use for ...'",
        ))
    if FIRST_PERSON.search(desc):
        out.append(finding(
            name, "desc-first-person", "warn",
            "first-person description",
            "rewrite in third person ('Use when ...')",
        ))

    # --- identity / resolution ----------------------------------------------
    fm = entry.get("frontmatter_name")
    if fm and fm != name:
        out.append(finding(
            name, "name-mismatch", "error",
            f"frontmatter name '{fm}' != resolved name '{name}'",
            "make frontmatter name match the directory name",
        ))
    if entry.get("shadowing"):
        out.append(finding(
            name, "collision", "error",
            f"also on disk at {'; '.join(entry['shadowing'])} — that copy never loads",
            "delete or rename one copy; a shadowed skill is edited but never used",
        ))

    # --- structure -----------------------------------------------------------
    if entry["body_lines"] > BODY_ERROR:
        out.append(finding(
            name, "body-length", "error",
            f"{entry['body_lines']} lines; focused skills outperform exhaustive ones",
            "move branch-specific reference material behind pointers",
        ))
    elif entry["body_lines"] > BODY_WARN:
        out.append(finding(
            name, "body-length", "warn",
            f"{entry['body_lines']} lines",
            "check whether every section is needed on every run",
        ))
    for pointer in entry.get("missing_pointers", []):
        out.append(finding(
            name, "broken-pointer", "error",
            f"body references file '{pointer}' which does not exist",
            "create the file or delete the pointer",
        ))
    for pointer in entry.get("missing_dir_pointers", []):
        out.append(finding(
            name, "broken-pointer-dir", "review",
            f"body names '{pointer}', which is not on disk (may be prose, may be stale)",
            "confirm whether this path was meant to exist",
        ))
    orphans = entry.get("orphan_assets", [])
    if orphans:
        shown = ", ".join(f"'{o}'" for o in orphans[:6])
        more = f" (+{len(orphans) - 6} more)" if len(orphans) > 6 else ""
        out.append(finding(
            name, "orphan-asset", "review",
            f"{len(orphans)} file(s) nothing in the skill points at: {shown}{more}",
            "add a pointer or delete the files; unreachable assets are dead weight",
        ))

    # --- content -------------------------------------------------------------
    sents = sentences(body)
    for index, sentence in enumerate(sents):
        for pattern, why in NO_OP_RE:
            if pattern.search(sentence) and not HEDGED_RE.search(sentence):
                out.append(finding(
                    name, "no-op", "warn",
                    f"{why}: {sentence[:110]!r}",
                    "delete the whole sentence; confirm with a deletion test",
                    saved=round(len(sentence) / 4),
                ))
                break
        if not NEGATION_RE.search(sentence):
            continue
        # Positive steering may live in this sentence or the next one
        # ("Never use X. Use Y instead.").
        window = sentence + " " + (sents[index + 1] if index + 1 < len(sents) else "")
        if POSITIVE_RE.search(window) or CONDITIONAL_RE.search(sentence):
            continue
        if SAFETY_RE.search(sentence):
            continue
        out.append(finding(
            name, "negation-without-positive", "warn",
            f"prohibition with no positive target: {sentence[:110]!r}",
            "state the wanted behaviour instead of the unwanted one",
        ))
    for pattern, why in ENV_CACHE_RE:
        if pattern.search(body):
            out.append(finding(
                name, "env-cache", "warn", f"{why}; goes stale silently",
                "point at the real source instead of copying it",
            ))
            break
    if STALE_RE.search(body):
        markers = sorted({m.group(0) for m in STALE_RE.finditer(body)})
        out.append(finding(
            name, "stale-marker", "warn",
            f"unfinished markers: {', '.join(markers)}",
            "finish or remove; a stale skill is a confident wrong answer",
        ))

    steps = len(NUMBERED_RE.findall(body))
    if steps >= 5 and len(JUDGEMENT_RE.findall(body)) < 3:
        out.append(finding(
            name, "rigid-procedure", "warn",
            f"{steps} numbered steps, almost no branching",
            "invariant checkable steps belong in a script, where they cannot be skipped",
        ))
    return cap_per_check(out)


def cap_per_check(items: list[dict]) -> list[dict]:
    """Keep a report readable: at most MAX_PER_CHECK examples per check per skill."""
    seen: dict[str, int] = defaultdict(int)
    kept: list[dict] = []
    for item in items:
        seen[item["check"]] += 1
        if seen[item["check"]] <= MAX_PER_CHECK:
            kept.append(item)
        elif seen[item["check"]] == MAX_PER_CHECK + 1:
            kept.append(finding(
                item["skill"], item["check"], item["severity"],
                "further occurrences suppressed; see the skill body",
                item["fix"],
            ))
    return kept


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", default="report")
    args = parser.parse_args()

    out_dir = Path(args.out)
    inventory = json.loads((out_dir / "inventory.json").read_text(encoding="utf-8"))
    entries = inventory["skills"]

    # bodies are not stored in inventory.json (size); re-read from disk
    for entry in entries:
        location = Path(entry["location"])
        entry["body"] = (
            location.read_text(encoding="utf-8", errors="replace")
            if location.is_file() else ""
        )

    findings: list[dict] = []
    for entry in entries:
        findings.extend(audit_skill(entry))

    # cross-skill duplication
    sets = {e["name"]: shingles(e["body"]) for e in entries}
    index: dict[str, list[str]] = defaultdict(list)
    for name, shs in sets.items():
        for sh in shs:
            index[sh].append(name)
    pairs: dict[tuple[str, str], int] = defaultdict(int)
    for names in index.values():
        if 1 < len(names) <= 6:
            for i, a in enumerate(names):
                for b in names[i + 1 :]:
                    pairs[tuple(sorted((a, b)))] += 1
    clusters = []
    for (a, b), shared in sorted(pairs.items(), key=lambda kv: -kv[1]):
        if shared < DUP_MIN_SHARED:
            continue
        smaller = min(len(sets[a]), len(sets[b])) or 1
        overlap = round(100 * shared / smaller)
        clusters.append({"a": a, "b": b, "shared_shingles": shared, "overlap_pct": overlap})
        if overlap < DUP_MIN_OVERLAP:
            continue
        for name, other in ((a, b), (b, a)):
            findings.append(finding(
                name, "duplication", "warn",
                f"{overlap}% text overlap with '{other}' ({shared} shared 8-grams)",
                "extract the shared part, or merge; overlapping skills make the trigger ambiguous",
            ))

    for path in inventory.get("orphans_on_disk", []):
        findings.append(finding(
            Path(path).parent.name, "not-loaded", "error",
            f"{path} exists on disk but opencode does not load it",
            "check for a name collision, missing description, or wrong directory",
        ))

    severity_rank = {"error": 0, "warn": 1, "review": 2}
    findings.sort(key=lambda f: (severity_rank.get(f["severity"], 9), f["skill"], f["check"]))

    by_skill: dict[str, list[dict]] = defaultdict(list)
    for item in findings:
        by_skill[item["skill"]].append(item)

    payload = {
        "generated_by": "skill-audit/audit.py",
        "totals": inventory["totals"],
        "findings": len(findings),
        "errors": sum(1 for f in findings if f["severity"] == "error"),
        "warnings": sum(1 for f in findings if f["severity"] == "warn"),
        "review": sum(1 for f in findings if f["severity"] == "review"),
        "est_tokens_saved": sum(f["est_tokens_saved"] for f in findings),
        "duplication_clusters": clusters,
        "by_check": {
            check: sum(1 for f in findings if f["check"] == check)
            for check in sorted({f["check"] for f in findings})
        },
        "results": findings,
    }
    (out_dir / "audit.json").write_text(json.dumps(payload, indent=2), encoding="utf-8")

    totals = inventory["totals"]
    lines = [
        "# Skill audit",
        "",
        f"- **{totals['skills']} skills loaded** — {totals['by_root']}",
        f"- **Description budget: {totals['desc_chars']} chars "
        f"(~{totals['desc_tokens_est']} tokens) billed on every request**",
        f"- Body surface: {totals['body_lines']} lines / {totals['body_chars']} chars",
        f"- {payload['errors']} errors, {payload['warnings']} warnings, "
        f"{payload['review']} to review, across {len(by_skill)} skills",
        f"- Recoverable by compression alone: ~{payload['est_tokens_saved']} tokens per request",
        "",
        "Severity: **error** = unambiguous, fix now. **warn** = probably worth fixing.",
        "**review** = needs a human glance; the check cannot tell prose from a promise.",
        "",
        "## Findings by check",
        "",
        "| check | count |",
        "| --- | --- |",
    ]
    lines += [f"| {c} | {n} |" for c, n in sorted(payload["by_check"].items(), key=lambda kv: -kv[1])]

    lines += ["", "## Description budget — worst first", "", "| skill | desc chars | ~tokens/request | body lines |", "| --- | --- | --- | --- |"]
    for entry in sorted(entries, key=lambda e: -e["desc_chars"])[:20]:
        lines.append(
            f"| `{entry['name']}` | {entry['desc_chars']} | {entry['desc_tokens_est']} | {entry['body_lines']} |"
        )

    errors = [f for f in findings if f["severity"] == "error"]
    if errors:
        lines += ["", "## Errors — unambiguous, fix without an interview", "", "| skill | check | evidence |", "| --- | --- | --- |"]
        lines += [
            f"| `{f['skill']}` | {f['check']} | {f['evidence'].replace('|', '/')} |" for f in errors
        ]

    if clusters:
        lines += ["", "## Duplication clusters", "", "| a | b | overlap |", "| --- | --- | --- |"]
        lines += [f"| `{c['a']}` | `{c['b']}` | {c['overlap_pct']}% |" for c in clusters[:20]]

    lines += ["", "## Per-skill detail", ""]
    for name in sorted(by_skill):
        items = by_skill[name]
        errs = sum(1 for i in items if i["severity"] == "error")
        lines.append(f"### `{name}` — {errs} errors, {len(items) - errs} warnings")
        lines.append("")
        for item in items:
            lines.append(f"- **{item['check']}** ({item['severity']}): {item['evidence']}")
            lines.append(f"  - fix: {item['fix']}")
        lines.append("")

    (out_dir / "AUDIT.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"wrote {out_dir / 'audit.json'} and {out_dir / 'AUDIT.md'}")
    print(f"  {payload['errors']} errors, {payload['warnings']} warnings")
    print(f"  ~{payload['est_tokens_saved']} tokens recoverable by compression")


if __name__ == "__main__":
    main()
