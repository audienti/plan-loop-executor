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
    by_status = {s: [t for t in tasks if t.get("status") == s] for s in STATUS_ORDER}

    print(f"plan:     {plan.get('slug', '?')} — {plan.get('objective', '')}")
    print(f"board:    {board.get('status', '?')}  (updated {board.get('updatedAt', '?')})")
    if board.get("worktreeRoot"):
        print(f"worktree: {board.get('worktreeRoot')}")
    print(
        f"progress: {len(by_status['done'])}/{len(tasks)} done   "
        + "  ".join(f"{s}:{len(v)}" for s, v in by_status.items() if v)
    )

    in_flight = by_status["running"] + by_status["verify"]
    if in_flight:
        print("\nin flight:")
        for t in in_flight:
            extra = f"  [attempt {t.get('attemptCount', 0) + 1}]" if t.get("attemptCount") else ""
            tier = t.get("modelTier")
            tier_tag = f"  [{tier}]" if tier and tier != "default" else ""
            print(f"  {t.get('id')}: ({t.get('status')}) {t.get('title')}{extra}{tier_tag}")

    if by_status["blocked"]:
        print("\nblocked:")
        for t in by_status["blocked"]:
            why = t.get("lastFailure") or t.get("notes") or "no reason recorded"
            print(f"  {t.get('id')}: {t.get('title')} — {why}")

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
