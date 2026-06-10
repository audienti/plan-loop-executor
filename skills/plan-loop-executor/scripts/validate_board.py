#!/usr/bin/env python3
"""Validate a plan-loop-executor board file.

Usage: python3 validate_board.py <board.json>

Exit 0 if valid (warnings allowed), 1 on errors.
"""
import json
import sys

TASK_STATUSES = {"backlog", "ready", "running", "verify", "done", "blocked", "deferred"}
BOARD_STATUSES = {"active", "complete", "abandoned"}
OWNER_LANES = {"controller", "subagent"}
REQUIRED_TASK_FIELDS = [
    "id", "title", "status", "priority", "dependsOn", "ownerLane", "files",
    "context", "doneWhen", "verification", "outputs", "attemptCount",
    "lastFailure", "commit", "notes",
]


def validate(data):
    errors, warnings = [], []

    plan = data.get("plan", {})
    if not plan.get("slug") or plan.get("slug") == "replace-me":
        warnings.append("plan.slug is unset")
    if not plan.get("acceptanceCriteria"):
        warnings.append("plan.acceptanceCriteria is empty")
    if not plan.get("verificationCommands"):
        warnings.append("plan.verificationCommands is empty")

    board = data.get("board", {})
    if board.get("status") not in BOARD_STATUSES:
        errors.append(
            f"board.status {board.get('status')!r} must be one of {sorted(BOARD_STATUSES)}"
        )

    base = board.get("base") or {}
    if not base:
        warnings.append("board.base is unset — record branch, commit, verifiedGreen at preflight")
    elif not base.get("verifiedGreen"):
        warnings.append("board.base.verifiedGreen is false — green trunk has no verified baseline")

    tasks = data.get("tasks", [])
    if not tasks:
        warnings.append("no tasks on board")

    ids = [t.get("id") for t in tasks if t.get("id")]
    dupes = sorted({i for i in ids if ids.count(i) > 1})
    if dupes:
        errors.append(f"duplicate task ids: {dupes}")
    by_id = {t["id"]: t for t in tasks if t.get("id")}

    for t in tasks:
        tid = t.get("id") or "<missing-id>"
        for field in REQUIRED_TASK_FIELDS:
            if field not in t:
                errors.append(f"{tid}: missing field {field!r}")
        status = t.get("status")
        if status not in TASK_STATUSES:
            errors.append(f"{tid}: status {status!r} must be one of {sorted(TASK_STATUSES)}")
        if t.get("ownerLane") not in OWNER_LANES:
            errors.append(
                f"{tid}: ownerLane {t.get('ownerLane')!r} must be one of {sorted(OWNER_LANES)}"
            )
        for dep in t.get("dependsOn", []):
            if dep not in by_id:
                errors.append(f"{tid}: dependsOn references unknown task {dep!r}")
        deps_done = all(
            by_id[d].get("status") == "done"
            for d in t.get("dependsOn", [])
            if d in by_id
        )
        if status in {"ready", "running", "verify", "done"} and not deps_done:
            errors.append(f"{tid}: status {status!r} but not all dependencies are done")
        if status == "done":
            if not t.get("verification"):
                errors.append(f"{tid}: done with no verification commands")
            if not t.get("commit"):
                warnings.append(f"{tid}: done but no commit recorded")
        if status not in {"backlog", "deferred"}:
            if not t.get("doneWhen"):
                warnings.append(f"{tid}: no doneWhen criteria")
            if not t.get("context"):
                warnings.append(f"{tid}: no context for a cold worker")

    cap = board.get("concurrencyCap")
    in_flight = sum(1 for t in tasks if t.get("status") in {"running", "verify"})
    if isinstance(cap, int) and in_flight > cap:
        warnings.append(f"{in_flight} tasks in flight exceeds concurrencyCap {cap}")

    # dependency cycle check (Kahn's algorithm)
    indeg = {i: 0 for i in by_id}
    dependents = {i: [] for i in by_id}
    for tid, t in by_id.items():
        for dep in set(t.get("dependsOn", [])):
            if dep in by_id:
                dependents[dep].append(tid)
                indeg[tid] += 1
    queue = [i for i, d in indeg.items() if d == 0]
    seen = 0
    while queue:
        n = queue.pop()
        seen += 1
        for m in dependents[n]:
            indeg[m] -= 1
            if indeg[m] == 0:
                queue.append(m)
    if seen < len(by_id):
        errors.append(
            f"dependency cycle among: {sorted(i for i, d in indeg.items() if d > 0)}"
        )

    return errors, warnings


def main():
    if len(sys.argv) != 2:
        print(__doc__.strip())
        return 2
    try:
        with open(sys.argv[1]) as f:
            data = json.load(f)
    except (OSError, json.JSONDecodeError) as e:
        print(f"ERROR: cannot read board: {e}")
        return 1
    errors, warnings = validate(data)
    for w in warnings:
        print(f"WARN:  {w}")
    for e in errors:
        print(f"ERROR: {e}")
    if errors:
        print(f"\nboard INVALID: {len(errors)} error(s), {len(warnings)} warning(s)")
        return 1
    print(f"board OK: 0 errors, {len(warnings)} warning(s)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
