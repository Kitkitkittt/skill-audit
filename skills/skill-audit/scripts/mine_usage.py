#!/usr/bin/env python3
"""Mine local session history for evidence about which skills earn their place.

Answers, per skill: has it ever fired, and did anything the user actually asked
for look like a match? A skill that never fired and never nearly matched is the
strongest retire candidate available, and it costs nothing to find.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

STOPWORDS = {
    "the", "and", "for", "with", "when", "use", "user", "this", "that", "from",
    "into", "your", "using", "asks", "ask", "want", "wants", "help", "should",
    "skill", "used", "only", "not", "any", "all", "via", "are", "its", "you",
    "them", "then", "than", "have", "has", "will", "can", "may", "also", "such",
    "like", "including", "include", "based", "over", "under", "about", "code",
    "file", "files", "run", "runs", "new", "get", "set", "make", "need", "needs",
    "trigger", "triggers", "invoke", "prefer", "provide", "provides", "work",
    "working", "task", "tasks", "project", "example", "examples", "etc",
}
KEYWORD_RE = re.compile(r"[a-z][a-z0-9+#.-]{2,}")
MIN_KEYWORD_HITS = 2


def default_storage() -> Path:
    if os.name == "nt":
        return Path.home() / ".local" / "share" / "opencode" / "storage"
    data = os.environ.get("XDG_DATA_HOME") or (Path.home() / ".local" / "share")
    return Path(data) / "opencode" / "storage"


def keywords(description: str, name: str) -> set[str]:
    words = {w for w in KEYWORD_RE.findall(description.lower()) if w not in STOPWORDS}
    words |= {p for p in name.split("-") if len(p) > 2}
    return words


def scan(storage: Path, verbose: bool) -> tuple[Counter, Counter, list[str], int]:
    """Return (tool counts, skill-invocation counts, user prompts, parts seen)."""
    tools: Counter = Counter()
    skills: Counter = Counter()
    prompts: list[str] = []
    seen = 0
    part_dir = storage / "part"
    if not part_dir.is_dir():
        sys.exit(f"no session storage at {part_dir}")

    for dirpath, _dirnames, filenames in os.walk(part_dir):
        for filename in filenames:
            if not filename.endswith(".json"):
                continue
            seen += 1
            if verbose and seen % 10000 == 0:
                print(f"  ...{seen} parts", file=sys.stderr)
            path = Path(dirpath) / filename
            try:
                raw = path.read_text(encoding="utf-8", errors="ignore")
            except OSError:
                continue
            if '"type"' not in raw:
                continue
            try:
                part = json.loads(raw)
            except json.JSONDecodeError:
                continue
            kind = part.get("type")
            if kind == "tool":
                tool = str(part.get("tool") or "")
                tools[tool] += 1
                if tool == "skill":
                    state = part.get("state") or {}
                    name = ((state.get("input") or {}) or {}).get("name")
                    if name:
                        skills[str(name)] += 1
            elif kind == "text":
                text = part.get("text")
                # Assistant text has timing; user text does not. Cheap filter
                # that keeps the prompt corpus close to what the user typed.
                if text and "time" not in part and len(text) < 4000:
                    prompts.append(text)
    return tools, skills, prompts, seen


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", default="report")
    parser.add_argument("--storage", default=None, help="override storage path")
    parser.add_argument("--quiet", action="store_true")
    args = parser.parse_args()

    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)
    inventory_path = out_dir / "inventory.json"
    if not inventory_path.is_file():
        sys.exit(f"run inventory.py first: {inventory_path} missing")
    inventory = json.loads(inventory_path.read_text(encoding="utf-8"))

    storage = Path(args.storage) if args.storage else default_storage()
    tools, invocations, prompts, seen = scan(storage, verbose=not args.quiet)

    corpus = [p.lower() for p in prompts]
    per_skill = []
    for entry in inventory["skills"]:
        words = keywords(entry["description"], entry["name"])
        name_hits = sum(1 for p in corpus if entry["name"] in p)
        near = 0
        for prompt in corpus:
            if sum(1 for w in words if w in prompt) >= MIN_KEYWORD_HITS:
                near += 1
        fired = invocations.get(entry["name"], 0)
        if fired:
            signal = "fired"
        elif name_hits:
            signal = "named-never-fired"
        elif near:
            signal = "relevant-never-fired"
        else:
            signal = "never-relevant"
        per_skill.append({
            "name": entry["name"],
            "desc_tokens_est": entry["desc_tokens_est"],
            "invocations": fired,
            "prompts_naming_it": name_hits,
            "prompts_matching_keywords": near,
            "signal": signal,
            "keywords": sorted(words)[:12],
        })

    per_skill.sort(key=lambda s: (-s["invocations"], -s["prompts_matching_keywords"], s["name"]))
    by_signal = Counter(s["signal"] for s in per_skill)
    wasted = sum(s["desc_tokens_est"] for s in per_skill if s["signal"] == "never-relevant")

    payload = {
        "generated_by": "skill-audit/mine_usage.py",
        "storage": str(storage),
        "parts_scanned": seen,
        "tool_calls": sum(tools.values()),
        "top_tools": tools.most_common(15),
        "skill_invocations_total": sum(invocations.values()),
        "prompts_sampled": len(prompts),
        "by_signal": dict(by_signal),
        "tokens_per_request_on_never_relevant": wasted,
        "skills": per_skill,
    }
    (out_dir / "usage.json").write_text(json.dumps(payload, indent=2), encoding="utf-8")

    print(f"wrote {out_dir / 'usage.json'}")
    print(f"  scanned {seen} parts, {sum(tools.values())} tool calls, {len(prompts)} prompts")
    print(f"  skill invocations recorded: {sum(invocations.values())}")
    print(f"  signals: {dict(by_signal)}")
    if not sum(invocations.values()):
        print("  NOTE: zero recorded invocations. Treat as a question, not a verdict:")
        print("        the skills may be new, or used from another harness.")
    else:
        print(f"  ~{wasted} tokens/request spent on never-relevant skills")


if __name__ == "__main__":
    main()
