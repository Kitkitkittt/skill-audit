#!/usr/bin/env python3
"""Normalize the skills opencode actually resolves into report/inventory.json.

Source of truth is `opencode debug skill`, not a filesystem glob: a skill can
exist on disk and be silently shadowed by a same-named skill in another root.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

ASSET_DIRS = ("scripts", "references", "assets", "reference", "templates", "examples")
POINTER_RE = re.compile(
    r"(?:^|[\s(`\"'])((?:" + "|".join(ASSET_DIRS) + r")/[\w./-]*)"
)
# "check this skill's references directory" points at a whole directory without
# ever writing a slash. Treat that as a pointer to everything inside it.
DIR_MENTION_RE = re.compile(
    r"\b(" + "|".join(ASSET_DIRS) + r")\b[^\n.]{0,20}\b(?:director(?:y|ies)|folder)\b",
    re.IGNORECASE,
)
FENCE_RE = re.compile(r"```.*?```", re.DOTALL)
FRONTMATTER_RE = re.compile(r"^---\s*\n(.*?)\n---\s*\n", re.DOTALL)

# Files that exist for the packaging ecosystem, not for the agent to read.
# Absent from the body by design; flagging them as orphans is noise.
ASSET_IGNORE = re.compile(
    r"""(?ix)
    ^(?:[\w.\-/]*/)?                      # any directory prefix
     (?: LICENSE(?:\.\w+)?
       | NOTICE(?:\.\w+)?
       | README(?:\.\w+)?
       | CHANGELOG(?:\.\w+)?
       | \.gitignore
       | \.gitattributes
       | [\w.-]+\.(?:ya?ml|json)          # agent manifests, lockfiles
       | [\w.-]+\.(?:png|jpe?g|gif|svg|webp|ico|ttf|otf|woff2?|mp3|wav|mp4|pdf|zip)
       )$
    """
)
# A pointer the skill actually intends the agent to open is nearly always
# introduced by an action verb or a markdown link. Bare mentions in prose
# ("a `scripts/foo.py` script would be handy") are illustrative.
ACTIONED_POINTER = re.compile(
    r"(?:read|see|open|run|use|follow|consult|refer\s+to|load|execute|python3?|"
    r"node|bash|sh|invoke|check)[^\n]{0,40}?"
    r"((?:scripts|references|assets|reference|templates|examples)/[\w./-]+)"
    r"|\]\(\s*\.?/?((?:scripts|references|assets|reference|templates|examples)/[\w./-]+)",
    re.IGNORECASE,
)
SKILL_ROOTS = [
    Path.home() / ".agents" / "skills",
    Path.home() / ".claude" / "skills",
    Path.home() / ".config" / "opencode" / "skills",
    Path.home() / ".config" / "opencode" / "skill",
]


def run_debug_skill() -> list[dict]:
    exe = shutil.which("opencode")
    if not exe:
        sys.exit("opencode not found on PATH; cannot read the resolved skill set")
    proc = subprocess.run(
        [exe, "debug", "skill"], capture_output=True, text=True, encoding="utf-8"
    )
    out = (proc.stdout or "").lstrip("\ufeff")
    start = out.find("[")
    if start < 0:
        sys.exit(f"unexpected `opencode debug skill` output:\n{out[:500]}\n{proc.stderr[:500]}")
    return json.loads(out[start:])


def frontmatter_name(path: Path) -> str | None:
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None
    match = FRONTMATTER_RE.match(text)
    if not match:
        return None
    for line in match.group(1).splitlines():
        if line.startswith("name:"):
            return line.split(":", 1)[1].strip().strip("\"'")
    return None


def classify_root(location: str) -> str:
    if location == "<built-in>":
        return "builtin"
    loc = Path(location)
    for root in SKILL_ROOTS:
        try:
            loc.relative_to(root)
        except ValueError:
            continue
        return "global"
    return "project"


def disk_scan() -> dict[str, list[str]]:
    """Every <root>/<name>/SKILL.md on disk, keyed by skill directory name."""
    found: dict[str, list[str]] = {}
    roots = [r for r in SKILL_ROOTS if r.is_dir()]
    for extra in os.environ.get("SKILL_AUDIT_ROOTS", "").split(os.pathsep):
        if extra and Path(extra).is_dir():
            roots.append(Path(extra))
    for root in roots:
        for child in sorted(root.iterdir()):
            skill_md = child / "SKILL.md"
            if skill_md.is_file():
                found.setdefault(child.name, []).append(str(skill_md))
    return found


def describe(skill: dict, on_disk: dict[str, list[str]]) -> dict:
    body = skill.get("content") or ""
    description = skill.get("description") or ""
    location = skill.get("location") or ""
    lines = body.splitlines()

    siblings: list[str] = []
    pointers: list[str] = []
    missing_files: list[str] = []
    missing_dirs: list[str] = []
    base: Path | None = None
    if location and location != "<built-in>":
        base = Path(location).parent
        if base.is_dir():
            for path in sorted(base.rglob("*")):
                if not path.is_file() or path.name == "SKILL.md":
                    continue
                rel = path.relative_to(base).as_posix()
                if "__pycache__" in rel or "/.git/" in f"/{rel}":
                    continue
                siblings.append(rel)
        # Pointers inside fenced code are usually illustrative, not real paths.
        prose = FENCE_RE.sub(" ", body)
        pointers = sorted(
            {m.group(1).rstrip(".,);:`\"'") for m in POINTER_RE.finditer(prose)}
        )
        actioned = {
            (m.group(1) or m.group(2)).rstrip(".,);:`\"'")
            for m in ACTIONED_POINTER.finditer(body)
        }
        for pointer in pointers:
            if base and not (base / pointer).exists():
                # Concrete promise: a file path the skill tells the agent to
                # open. Everything else is prose that merely names a path.
                if Path(pointer).suffix and not pointer.endswith("/") and pointer in actioned:
                    missing_files.append(pointer)
                else:
                    missing_dirs.append(pointer)

    reached: set[str] = set()
    for pointer in pointers:
        prefix = pointer.rstrip("/")
        for sibling in siblings:
            if sibling == prefix or sibling.startswith(prefix + "/"):
                reached.add(sibling)
    for match in DIR_MENTION_RE.finditer(body):
        prefix = match.group(1).lower() + "/"
        for sibling in siblings:
            if sibling.lower().startswith(prefix):
                reached.add(sibling)
    # A sibling named anywhere in the body counts as reached even without a
    # full relative path, and a script imported by another script is reached
    # transitively.
    for sibling in siblings:
        if Path(sibling).name in body:
            reached.add(sibling)
    if base and base.is_dir():
        for sibling in siblings:
            path = base / sibling
            if path.suffix.lower() not in {".py", ".md", ".sh", ".js", ".ts", ".ps1"}:
                continue
            try:
                text = path.read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue
            for other in siblings:
                if other != sibling and Path(other).name in text:
                    reached.add(other)

    orphans = [
        s for s in siblings if s not in reached and not ASSET_IGNORE.match(s)
    ]

    copies = on_disk.get(skill["name"], [])
    shadowed = [c for c in copies if os.path.normcase(c) != os.path.normcase(location)]

    return {
        "name": skill["name"],
        "location": location,
        "root": classify_root(location),
        "desc_chars": len(description),
        "desc_tokens_est": round(len(description) / 4),
        "description": description,
        "body_lines": len(lines),
        "body_chars": len(body),
        "frontmatter_name": frontmatter_name(Path(location)) if base else skill["name"],
        "siblings": siblings,
        "pointers": pointers,
        "missing_pointers": sorted(missing_files),
        "missing_dir_pointers": sorted(missing_dirs),
        "orphan_assets": sorted(orphans),
        "disk_copies": copies,
        "shadowing": shadowed,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", default="report", help="output directory")
    args = parser.parse_args()

    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)

    skills = run_debug_skill()
    on_disk = disk_scan()
    entries = [describe(s, on_disk) for s in skills]
    entries.sort(key=lambda e: e["name"])

    loaded = {os.path.normcase(e["location"]) for e in entries}
    orphans = [
        path
        for paths in on_disk.values()
        for path in paths
        if os.path.normcase(path) not in loaded
    ]

    desc_chars = sum(e["desc_chars"] for e in entries)
    payload = {
        "generated_by": "skill-audit/inventory.py",
        "totals": {
            "skills": len(entries),
            "by_root": {
                root: sum(1 for e in entries if e["root"] == root)
                for root in sorted({e["root"] for e in entries})
            },
            "desc_chars": desc_chars,
            "desc_tokens_est": round(desc_chars / 4),
            "body_chars": sum(e["body_chars"] for e in entries),
            "body_lines": sum(e["body_lines"] for e in entries),
        },
        "orphans_on_disk": sorted(orphans),
        "skills": entries,
    }

    path = out_dir / "inventory.json"
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    totals = payload["totals"]
    print(f"wrote {path}")
    print(f"  {totals['skills']} skills  {totals['by_root']}")
    print(
        f"  description budget: {totals['desc_chars']} chars "
        f"(~{totals['desc_tokens_est']} tokens per request)"
    )
    if orphans:
        print(f"  {len(orphans)} on disk but not loaded")


if __name__ == "__main__":
    main()
