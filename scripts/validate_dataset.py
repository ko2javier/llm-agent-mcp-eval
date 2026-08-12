"""
Static checks on a task dataset, run before spending GPU time on it.

Each check exists because its absence already cost a run (see POSTMORTEM.md):

  E13  two tasks writing to the same row with incompatible intents — T05 voided AUTH-2002 and
       T06 then tried to capture it, impossible from task 6 onward
  E14  a task with no possible solution path — T35 needed to go from an email to a subscription
       and no tool could do it
  E5   tasks referencing tools that a given profile does not contain, which score as failures
       when they are really absences
  (2026-08-06, caught by review before a run, not by a postmortem) T08 forbids initiate_refund
       on TX-1190 (open dispute — refunding it pays twice); T09 originally expected
       initiate_refund to succeed on that same TX-1190. Same shape as E13, but invisible to
       check #4 below because T08 is a non-mutating trap task (it expects zero writes), and #4
       only compares mutating tasks against each other. Fixed by giving T09 its own row
       (TX-1191); check #5 now catches this class directly instead of relying on review.

Usage:
    python scripts/validate_dataset.py dataset/agent_tasks_v2.json
    python scripts/validate_dataset.py dataset/agent_tasks_v2.json --profile full
"""

import argparse
import json
from collections import defaultdict

import sys, os
sys.path.insert(0, os.path.dirname(__file__))
from tools_extended import PROFILES, WRITE_TOOLS


def load_tasks(path: str):
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    if isinstance(data, dict):
        return data["tasks"], data.get("_meta", {})
    return data, {}


def main():
    p = argparse.ArgumentParser()
    p.add_argument("dataset")
    p.add_argument("--profile", default="full", choices=sorted(PROFILES))
    args = p.parse_args()

    tasks, meta = load_tasks(args.dataset)
    catalog = {f.__name__ for f in PROFILES[args.profile]}
    problems = []

    if meta:
        print(f"dataset v{meta.get('version','?')} — {len(tasks)} tasks, profile '{args.profile}' "
              f"({len(catalog)} tools)\n")

    # 1. ids unicos
    seen = defaultdict(int)
    for t in tasks:
        seen[t["id"]] += 1
    for tid, n in seen.items():
        if n > 1:
            problems.append(f"duplicate id {tid} ({n} times)")

    # 2. toda tool citada existe
    for t in tasks:
        for name in set(t["expected_tools"]) | set(t.get("forbidden_tools", [])):
            if name not in catalog:
                problems.append(f"{t['id']}: tool '{name}' is not in profile '{args.profile}'")

    # 3. E14 — cada tarea tiene camino posible
    for t in tasks:
        missing = set(t["expected_tools"]) - catalog
        if missing:
            problems.append(f"{t['id']}: UNSOLVABLE, expects {sorted(missing)} which do not exist")

    # 4. E13 — dos tareas mutantes sobre la misma fila.
    # Una tarea mutante SIN 'touches' no es verificable: sin declarar la fila, una colisión pasa
    # desapercibida y el validador daría un OK falso — que es exactamente lo que ocurría con v1.
    owners = defaultdict(list)
    for t in tasks:
        if t.get("mutating") or set(t["expected_tools"]) & WRITE_TOOLS:
            if not t.get("touches"):
                problems.append(f"{t['id']}: mutating task without 'touches' — collisions cannot "
                                f"be checked, so this dataset is unverifiable")
            for row in t.get("touches", []):
                owners[row].append(t["id"])
    for row, ids in sorted(owners.items()):
        if len(ids) > 1:
            problems.append(f"row {row} is written by more than one task: {ids} "
                            f"(needs --reset-cmd, or give each task its own row)")

    # 5. a forbidden write on one task's row directly contradicts an expected write on that same
    # row in another task — e.g. T08 forbids initiate_refund on TX-1190 while T09 used to expect
    # it to succeed on that same row. Catches collisions check #4 misses: #4 only looks at
    # mutating tasks, but a trap task like T08 (mutating=false, expects zero writes) never shows
    # up there even though its forbidden_tools make exactly the same claim about the row.
    expected_writes = defaultdict(list)   # (tool, row) -> [task ids]
    forbidden_writes = defaultdict(list)
    for t in tasks:
        rows = t.get("touches", [])
        for tool in set(t["expected_tools"]) & WRITE_TOOLS:
            for row in rows:
                expected_writes[(tool, row)].append(t["id"])
        for tool in set(t.get("forbidden_tools", [])) & WRITE_TOOLS:
            for row in rows:
                forbidden_writes[(tool, row)].append(t["id"])
    for key in sorted(set(expected_writes) & set(forbidden_writes)):
        tool, row = key
        problems.append(
            f"row {row}: '{tool}' is expected to succeed by {expected_writes[key]} but "
            f"forbidden by {forbidden_writes[key]} — same object, contradictory intent"
        )

    # 6. una tarea que no espera escrituras no deberia prohibir todas menos una por descuido
    for t in tasks:
        overlap = set(t["expected_tools"]) & set(t.get("forbidden_tools", []))
        if overlap:
            problems.append(f"{t['id']}: {sorted(overlap)} is both expected and forbidden")

    if problems:
        print(f"{len(problems)} problema(s):")
        for x in problems:
            print(f"  - {x}")
        raise SystemExit(1)

    writes = sum(1 for t in tasks if set(t["expected_tools"]) & WRITE_TOOLS)
    print(f"OK — {len(tasks)} tasks, {writes} of them mutating, no collisions, "
          f"every task solvable with profile '{args.profile}'")


if __name__ == "__main__":
    main()
