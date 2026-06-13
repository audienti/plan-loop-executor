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
MODEL_TIERS = {"fast", "default", "max"}
MESSAGE_TYPES = {"blocker", "interface-note", "handoff", "discovery", "question", "risk"}
MESSAGE_STATUSES = {"open", "acknowledged", "resolved", "superseded"}
REQUIRED_TASK_FIELDS = [
    "id", "title", "status", "priority", "dependsOn", "ownerLane", "modelTier",
    "files", "context", "doneWhen", "verification", "outputs", "attemptCount",
    "lastFailure", "commit", "notes",
]
REQUIRED_MESSAGE_FIELDS = [
    "id", "fromTask", "toTasks", "type", "subject", "body", "createdAt", "status",
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

    viewer = board.get("viewer")
    if viewer is None:
        warnings.append("board.viewer is unset — HTML board rendering path will use <board>.html")
    elif not isinstance(viewer, dict):
        errors.append("board.viewer must be an object when set")
    elif viewer.get("htmlPath") is not None and not isinstance(viewer.get("htmlPath"), str):
        errors.append("board.viewer.htmlPath must be a string when set")

    if board.get("parallelismNote") is not None and not isinstance(board.get("parallelismNote"), str):
        errors.append("board.parallelismNote must be a string when set")

    models = board.get("models")
    if models is not None:
        if not isinstance(models, dict):
            errors.append("board.models must be an object mapping tiers to model names")
        else:
            for tier, model in models.items():
                if tier not in MODEL_TIERS:
                    errors.append(
                        f"board.models key {tier!r} must be one of {sorted(MODEL_TIERS)}"
                    )
                if not isinstance(model, str) or not model:
                    errors.append(
                        f"board.models.{tier} must be a non-empty string ('inherit' = session model)"
                    )

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
        if t.get("modelTier") not in MODEL_TIERS:
            errors.append(
                f"{tid}: modelTier {t.get('modelTier')!r} must be one of {sorted(MODEL_TIERS)}"
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
        if status in {"running", "verify"}:
            if not t.get("updatedAt"):
                warnings.append(f"{tid}: {status} but updatedAt is unset")
            if t.get("ownerLane") == "subagent":
                if not t.get("worktree"):
                    warnings.append(f"{tid}: subagent {status} but worktree is unset")
                if not t.get("resolvedModel"):
                    warnings.append(f"{tid}: subagent {status} but resolvedModel is unset")

    cap = board.get("concurrencyCap")
    in_flight = sum(
        1
        for t in tasks
        if t.get("status") in {"running", "verify"} and t.get("ownerLane") == "subagent"
    )
    if isinstance(cap, int) and in_flight > cap:
        warnings.append(f"{in_flight} subagent tasks in flight exceeds concurrencyCap {cap}")

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

    messages = data.get("messages", [])
    if messages is None:
        messages = []
    if not isinstance(messages, list):
        errors.append("messages must be an array when set")
    else:
        message_ids = [m.get("id") for m in messages if isinstance(m, dict) and m.get("id")]
        message_dupes = sorted({i for i in message_ids if message_ids.count(i) > 1})
        if message_dupes:
            errors.append(f"duplicate message ids: {message_dupes}")
        for m in messages:
            if not isinstance(m, dict):
                errors.append("message entries must be objects")
                continue
            mid = m.get("id") or "<missing-message-id>"
            for field in REQUIRED_MESSAGE_FIELDS:
                if field not in m:
                    errors.append(f"{mid}: missing message field {field!r}")
            if not isinstance(m.get("id"), str) or not m.get("id"):
                errors.append(f"{mid}: id must be a non-empty string")
            if not isinstance(m.get("fromTask"), str) or not m.get("fromTask"):
                errors.append(f"{mid}: fromTask must be a non-empty string")
            if m.get("type") not in MESSAGE_TYPES:
                errors.append(
                    f"{mid}: type {m.get('type')!r} must be one of {sorted(MESSAGE_TYPES)}"
                )
            if m.get("status") not in MESSAGE_STATUSES:
                errors.append(
                    f"{mid}: status {m.get('status')!r} must be one of {sorted(MESSAGE_STATUSES)}"
                )
            if m.get("fromTask") != "controller" and m.get("fromTask") not in by_id:
                errors.append(f"{mid}: fromTask references unknown task {m.get('fromTask')!r}")
            to_tasks = m.get("toTasks", [])
            if not isinstance(to_tasks, list):
                errors.append(f"{mid}: toTasks must be an array")
            else:
                for target in to_tasks:
                    if not isinstance(target, str) or not target:
                        errors.append(f"{mid}: toTasks entries must be non-empty strings")
                        continue
                    if target != "controller" and target not in by_id:
                        errors.append(f"{mid}: toTasks references unknown task {target!r}")
            if not isinstance(m.get("createdAt"), str) or not m.get("createdAt"):
                errors.append(f"{mid}: createdAt must be a non-empty string")
            if not m.get("subject"):
                warnings.append(f"{mid}: subject is empty")
            if m.get("status") == "open" and not m.get("body"):
                warnings.append(f"{mid}: open message has empty body")

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
