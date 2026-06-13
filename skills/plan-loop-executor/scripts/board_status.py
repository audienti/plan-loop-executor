#!/usr/bin/env python3
"""Print a human-readable summary of a plan-loop-executor board.

Usage: python3 board_status.py <board.json>
"""
import json
import sys

STATUS_ORDER = ["backlog", "ready", "running", "verify", "done", "blocked", "deferred"]


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

    plan = data.get("plan", {})
    board = data.get("board", {})
    tasks = data.get("tasks", [])
    messages = data.get("messages", [])
    by_status = {s: [t for t in tasks if t.get("status") == s] for s in STATUS_ORDER}

    print(f"plan:     {plan.get('slug', '?')} — {plan.get('objective', '')}")
    print(f"board:    {board.get('status', '?')}  (updated {board.get('updatedAt', '?')})")
    if board.get("worktreeRoot"):
        print(f"worktree: {board.get('worktreeRoot')}")
    viewer = board.get("viewer") if isinstance(board.get("viewer"), dict) else {}
    if viewer.get("htmlPath"):
        print(f"viewer:   {viewer.get('htmlPath')}")
    print(
        f"progress: {len(by_status['done'])}/{len(tasks)} done   "
        + "  ".join(f"{s}:{len(v)}" for s, v in by_status.items() if v)
    )
    if board.get("parallelismNote"):
        print(f"parallel: {board.get('parallelismNote')}")
    if isinstance(messages, list):
        open_messages = [m for m in messages if isinstance(m, dict) and m.get("status") == "open"]
        if open_messages:
            print(f"messages: {len(open_messages)} open")

    in_flight = by_status["running"] + by_status["verify"]
    if in_flight:
        print("\nin flight:")
        for t in in_flight:
            extra = f"  [attempt {t.get('attemptCount', 0) + 1}]" if t.get("attemptCount") else ""
            tier = t.get("modelTier")
            tier_tag = f"  [{tier}]" if tier and tier != "default" else ""
            model = f"  model={t.get('resolvedModel')}" if t.get("resolvedModel") else ""
            worktree = f"  worktree={t.get('worktree')}" if t.get("worktree") else ""
            print(
                f"  {t.get('id')}: ({t.get('status')}) {t.get('title')}"
                f"{extra}{tier_tag}{model}{worktree}"
            )

    if by_status["blocked"]:
        print("\nblocked:")
        for t in by_status["blocked"]:
            why = t.get("lastFailure") or t.get("notes") or "no reason recorded"
            print(f"  {t.get('id')}: {t.get('title')} — {why}")

    if isinstance(messages, list):
        open_messages = [m for m in messages if isinstance(m, dict) and m.get("status") == "open"]
        if open_messages:
            print("\nopen messages:")
            for m in open_messages[:5]:
                targets = (
                    ", ".join(str(target) for target in m.get("toTasks", []))
                    if isinstance(m.get("toTasks"), list)
                    else "?"
                )
                print(
                    f"  {m.get('id')}: [{m.get('type')}] {m.get('subject')} "
                    f"({m.get('fromTask')} -> {targets or 'all'})"
                )

    nxt = sorted(by_status["ready"], key=lambda t: (t.get("priority", 99), t.get("id", "")))
    if nxt:
        print("\nnext up:")
        for t in nxt[:3]:
            tier = t.get("modelTier", "default")
            print(f"  {t.get('id')}: {t.get('title')} (priority {t.get('priority', '?')}, {tier})")

    if by_status["done"]:
        by_tier = {}
        for t in by_status["done"]:
            tier = t.get("modelTier", "default")
            by_tier.setdefault(tier, []).append(t.get("attemptCount", 0) + 1)
        stats = "  ".join(
            f"{tier}: {sum(v) / len(v):.1f} over {len(v)} task{'s' if len(v) != 1 else ''}"
            for tier, v in sorted(by_tier.items())
        )
        print(f"\nattempts/solve by tier: {stats}")

    if by_status["deferred"]:
        print("\ndeferred: " + ", ".join(t.get("id", "?") for t in by_status["deferred"]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
