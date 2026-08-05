#!/usr/bin/env python3
"""Run a skill's evals, with and without the skill, and report the delta.

The `without` arm denies the skill through injected config. Nothing on disk is
moved and the user's own config is never modified.

Grading is deliberately cheap-first: the trigger comes free from the event
stream, file and regex checks cover most outcomes, and a judge is only needed
for what regex genuinely cannot see.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import statistics
import subprocess
import sys
import tempfile
import time
from pathlib import Path

SCHEMA_HINT = """evals.json shape:
{
  "skill_name": "my-skill",
  "evals": [
    {
      "id": "happy-1",
      "prompt": "...",
      "should_trigger": true,
      "files": {"src/app.ts": "existing content"},
      "expect_regex": ["interactions\\\\.create\\\\("],
      "reject_regex": ["deprecated_api"],
      "expect_files": ["out/report.md"],
      "expectations": ["explains why the flag is needed"]
    }
  ]
}"""


def load_cases(path: Path) -> tuple[str, list[dict]]:
    data = json.loads(path.read_text(encoding="utf-8"))
    cases = data.get("evals") or []
    if not cases:
        sys.exit(f"no evals in {path}\n\n{SCHEMA_HINT}")
    return data.get("skill_name", path.parent.parent.name), cases


def build_workspace(case: dict) -> Path:
    """Fresh directory per trial: no run can read another run's work."""
    workspace = Path(tempfile.mkdtemp(prefix="skill-eval-"))
    for rel, content in (case.get("files") or {}).items():
        target = workspace / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")
    return workspace


def run_once(prompt: str, workspace: Path, model: str | None, agent: str,
             deny: str | None, timeout: int) -> dict:
    exe = shutil.which("opencode")
    if not exe:
        sys.exit("opencode not found on PATH")
    cmd = [exe, "run", "--format", "json", "--pure", "--agent", agent,
           "--dir", str(workspace)]
    if model:
        cmd += ["-m", model]
    cmd.append(prompt)

    env = dict(os.environ)
    if deny:
        env["OPENCODE_CONFIG_CONTENT"] = json.dumps({
            "$schema": "https://opencode.ai/config.json",
            "permission": {"skill": {"*": "allow", deny: "deny"}},
        })
    started = time.time()
    try:
        proc = subprocess.run(
            cmd, capture_output=True, text=True, encoding="utf-8",
            errors="replace", env=env, timeout=timeout,
        )
        out, err, code = proc.stdout or "", proc.stderr or "", proc.returncode
    except subprocess.TimeoutExpired:
        out, err, code = "", f"timeout after {timeout}s", -1
    return {
        "stdout": out,
        "stderr": err,
        "exit_code": code,
        "elapsed_s": round(time.time() - started, 1),
    }


def skills_fired(stdout: str) -> list[str]:
    """Read skill invocations out of the JSON event stream."""
    fired: list[str] = []
    for line in stdout.splitlines():
        line = line.strip()
        if not line.startswith("{") or '"skill"' not in line:
            continue
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            continue
        stack = [event]
        while stack:
            node = stack.pop()
            if isinstance(node, dict):
                if node.get("tool") == "skill":
                    name = ((node.get("state") or {}).get("input") or {}).get("name")
                    if name:
                        fired.append(str(name))
                stack.extend(node.values())
            elif isinstance(node, list):
                stack.extend(node)
    return fired


def grade(case: dict, result: dict, workspace: Path, skill: str) -> dict:
    fired = skills_fired(result["stdout"])
    checks: list[dict] = []

    if "should_trigger" in case:
        want = bool(case["should_trigger"])
        got = skill in fired
        checks.append({
            "check": "trigger",
            "passed": want == got,
            "detail": f"expected {want}, fired={fired or 'none'}",
        })
    for pattern in case.get("expect_regex", []):
        checks.append({
            "check": f"expect_regex:{pattern}",
            "passed": bool(re.search(pattern, result["stdout"], re.IGNORECASE)),
            "detail": "not found in transcript",
        })
    for pattern in case.get("reject_regex", []):
        checks.append({
            "check": f"reject_regex:{pattern}",
            "passed": not re.search(pattern, result["stdout"], re.IGNORECASE),
            "detail": "forbidden pattern present",
        })
    for rel in case.get("expect_files", []):
        checks.append({
            "check": f"expect_file:{rel}",
            "passed": (workspace / rel).exists(),
            "detail": "file not created",
        })

    judged = case.get("expectations") or []
    return {
        "checks": checks,
        "passed": all(c["passed"] for c in checks) if checks else None,
        "skills_fired": fired,
        "needs_judge": judged,
        "elapsed_s": result["elapsed_s"],
        "exit_code": result["exit_code"],
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--skill", required=True)
    parser.add_argument("--evals", default=None, help="path to evals.json")
    parser.add_argument("--arms", default="with,without")
    parser.add_argument("--trials", type=int, default=3)
    parser.add_argument("--model", default=None)
    parser.add_argument("--agent", default="build")
    parser.add_argument("--timeout", type=int, default=600)
    parser.add_argument("--out", default="report")
    parser.add_argument("--keep-workspaces", action="store_true")
    args = parser.parse_args()

    evals_path = Path(args.evals) if args.evals else None
    if evals_path is None:
        inventory_path = Path(args.out) / "inventory.json"
        if inventory_path.is_file():
            inventory = json.loads(inventory_path.read_text(encoding="utf-8"))
            for entry in inventory["skills"]:
                if entry["name"] == args.skill and entry["location"] != "<built-in>":
                    evals_path = Path(entry["location"]).parent / "evals" / "evals.json"
                    break
    if not evals_path or not evals_path.is_file():
        sys.exit(f"no evals.json for '{args.skill}'\n\n{SCHEMA_HINT}")

    _, cases = load_cases(evals_path)
    arms = [a.strip() for a in args.arms.split(",") if a.strip()]
    total = len(cases) * len(arms) * args.trials
    print(f"{len(cases)} cases x {len(arms)} arms x {args.trials} trials = {total} runs")

    records = []
    for arm in arms:
        deny = args.skill if arm == "without" else None
        for case in cases:
            for trial in range(1, args.trials + 1):
                workspace = build_workspace(case)
                try:
                    result = run_once(case["prompt"], workspace, args.model,
                                      args.agent, deny, args.timeout)
                    graded = grade(case, result, workspace, args.skill)
                finally:
                    if not args.keep_workspaces:
                        shutil.rmtree(workspace, ignore_errors=True)
                records.append({
                    "arm": arm, "case": case["id"], "trial": trial, **graded,
                })
                status = {True: "pass", False: "FAIL", None: "n/a"}[graded["passed"]]
                print(f"  [{arm}] {case['id']} trial {trial}: {status} "
                      f"({graded['elapsed_s']}s)")

    def rate(arm: str) -> float | None:
        graded = [r["passed"] for r in records if r["arm"] == arm and r["passed"] is not None]
        return round(100 * sum(graded) / len(graded), 1) if graded else None

    rates = {arm: rate(arm) for arm in arms}
    verdict = "inconclusive"
    if rates.get("with") is not None and rates.get("without") is not None:
        if rates["without"] >= rates["with"]:
            verdict = "RETIRE: the skill does not beat its own absence. Keep the evals."
        elif rates["with"] - rates["without"] < 5:
            verdict = "MARGINAL: within noise. Add cases or accept it is not earning much."
        else:
            verdict = f"KEEP: +{round(rates['with'] - rates['without'], 1)} points from the skill."

    payload = {
        "generated_by": "skill-audit/run_eval.py",
        "skill": args.skill,
        "model": args.model,
        "arms": arms,
        "trials": args.trials,
        "pass_rate": rates,
        "median_elapsed_s": {
            arm: statistics.median([r["elapsed_s"] for r in records if r["arm"] == arm] or [0])
            for arm in arms
        },
        "verdict": verdict,
        "needs_judge": sorted({e for r in records for e in r["needs_judge"]}),
        "runs": records,
    }
    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / f"eval-{args.skill}.json"
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")

    print(f"\nwrote {path}")
    print(f"  pass rate: {rates}")
    print(f"  {verdict}")
    if payload["needs_judge"]:
        print(f"  {len(payload['needs_judge'])} expectation(s) still need a judge; "
              "grade those by reading the transcripts.")


if __name__ == "__main__":
    main()
