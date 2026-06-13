#!/usr/bin/env python3
"""Render a plan-loop-executor board as a read-only HTML kanban page.

Usage: python3 render_board.py <board.json> [--output <board.html>]

The JSON board remains the only source of truth. This script writes a static
HTML snapshot that can be refreshed in a browser during long-running work.
"""
import argparse
import json
import sys
from datetime import datetime, timezone
from html import escape
from pathlib import Path

STATUS_ORDER = ["backlog", "ready", "running", "verify", "done", "blocked", "deferred"]
STATUS_LABELS = {
    "backlog": "Backlog",
    "ready": "Ready",
    "running": "Running",
    "verify": "Verify",
    "done": "Done",
    "blocked": "Blocked",
    "deferred": "Deferred",
}
MESSAGE_TYPES = {"blocker", "interface-note", "handoff", "discovery", "question", "risk"}


def utc_now():
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def h(value):
    if value is None:
        return ""
    return escape(str(value), quote=True)


def read_json(path):
    try:
        with path.open(encoding="utf-8") as f:
            return json.load(f)
    except (OSError, json.JSONDecodeError) as e:
        raise SystemExit(f"ERROR: cannot read board: {e}") from e


def find_repo_root(path):
    current = path.resolve().parent
    for candidate in [current, *current.parents]:
        if (candidate / ".git").exists():
            return candidate
    return None


def output_path_for(board_path, data, override):
    if override:
        return Path(override)

    viewer = data.get("board", {}).get("viewer") or {}
    html_path = viewer.get("htmlPath") if isinstance(viewer, dict) else None
    if html_path:
        candidate = Path(html_path)
        if candidate.is_absolute():
            return candidate
        repo_root = find_repo_root(board_path)
        if repo_root:
            return repo_root / candidate
        return Path.cwd() / candidate

    return board_path.with_suffix(".html")


def as_list(value):
    if isinstance(value, list):
        return [str(v) for v in value if str(v)]
    if value:
        return [str(value)]
    return []


def render_list(items, empty=""):
    values = as_list(items)
    if not values:
        return f"<span class=\"muted\">{h(empty)}</span>" if empty else ""
    return "<ul>" + "".join(f"<li>{h(item)}</li>" for item in values) + "</ul>"


def task_files(task):
    return set(as_list(task.get("files")))


def deps_done(task, by_id):
    return all(by_id.get(dep, {}).get("status") == "done" for dep in as_list(task.get("dependsOn")))


def blocked_deps(task, by_id):
    return [dep for dep in as_list(task.get("dependsOn")) if by_id.get(dep, {}).get("status") != "done"]


def sort_key(task):
    return (task.get("priority", 99), str(task.get("id", "")))


def select_dispatch_candidates(tasks, by_id, board):
    cap = board.get("concurrencyCap")
    if not isinstance(cap, int) or cap < 1:
        return [], "No valid concurrencyCap is set."

    in_flight = [
        task for task in tasks
        if task.get("status") in {"running", "verify"} and task.get("ownerLane") == "subagent"
    ]
    capacity = max(cap - len(in_flight), 0)
    if capacity == 0:
        return [], "Sub-agent capacity is full."

    used_files = set()
    for task in in_flight:
        used_files.update(task_files(task))

    candidates = []
    skipped_for_overlap = []
    ready = sorted(
        [
            task for task in tasks
            if task.get("status") == "ready"
            and task.get("ownerLane") == "subagent"
            and deps_done(task, by_id)
        ],
        key=sort_key,
    )

    for task in ready:
        files = task_files(task)
        if files and used_files.intersection(files):
            skipped_for_overlap.append(task.get("id", "?"))
            continue
        candidates.append(task)
        used_files.update(files)
        if len(candidates) >= capacity:
            break

    if candidates:
        ids = ", ".join(task.get("id", "?") for task in candidates)
        return candidates, f"Capacity available. Next safe dispatch candidates: {ids}."
    if ready and skipped_for_overlap:
        return [], "Ready sub-agent tasks exist, but file ownership overlaps with in-flight work."
    if ready:
        return [], "Ready sub-agent tasks exist, but none were selected by the audit."
    return [], "No ready sub-agent tasks; work is dependency-gated or controller-lane only."


def task_reason(task, by_id):
    status = task.get("status")
    if status == "backlog":
        waiting = blocked_deps(task, by_id)
        if waiting:
            return "Waiting on " + ", ".join(waiting)
        return "Backlog task has no open dependency; it may need promotion to ready."
    if status == "ready":
        if task.get("ownerLane") == "controller":
            return "Ready for controller execution."
        return "Ready for dispatch if file ownership and capacity permit."
    if status == "running":
        return "In flight."
    if status == "verify":
        return "Awaiting controller verification."
    if status == "done":
        return "Verified and committed." if task.get("commit") else "Verified; no commit recorded."
    if status == "blocked":
        return task.get("lastFailure") or task.get("notes") or "Blocked; no reason recorded."
    if status == "deferred":
        return task.get("notes") or "Deferred."
    return ""


def chip(label, value=None):
    if value is None or value == "":
        return ""
    return f"<span class=\"chip\"><b>{h(label)}</b>{h(value)}</span>"


def render_task(task, by_id):
    status = task.get("status", "unknown")
    classes = f"task task-{h(status)}"
    try:
        attempts = int(task.get("attemptCount") or 0)
    except (TypeError, ValueError):
        attempts = 0
    attempt_label = attempts + 1 if status in {"running", "verify"} else attempts
    chips = [
        chip("lane", task.get("ownerLane")),
        chip("tier", task.get("modelTier")),
        chip("model", task.get("resolvedModel")),
        chip("attempt", attempt_label),
        chip("priority", task.get("priority")),
    ]
    chips_html = "".join(c for c in chips if c)

    sections = [
        ("Reason", task_reason(task, by_id), False),
        ("Worktree", task.get("worktree"), False),
        ("Depends on", ", ".join(as_list(task.get("dependsOn"))), False),
        ("Files", render_list(task.get("files"), "none recorded"), True),
        ("Verification", render_list(task.get("verification"), "none recorded"), True),
        ("Done when", render_list(task.get("doneWhen"), "none recorded"), True),
        ("Last failure", task.get("lastFailure"), False),
        ("Notes", task.get("notes"), False),
        ("Outputs", render_list(task.get("outputs")), True),
        ("Commit", task.get("commit"), False),
    ]
    body = []
    for label, value, is_html in sections:
        if not value:
            continue
        rendered_value = value if is_html else h(value)
        body.append(f"<div class=\"field\"><div class=\"label\">{h(label)}</div><div>{rendered_value}</div></div>")

    return f"""
      <article class="{classes}">
        <header>
          <div class="task-id">{h(task.get("id", "?"))}</div>
          <h3>{h(task.get("title", ""))}</h3>
        </header>
        <div class="chips">{chips_html}</div>
        {''.join(body)}
      </article>
    """


def render_parallel_audit(tasks, by_id, board):
    candidates, reason = select_dispatch_candidates(tasks, by_id, board)
    cap = board.get("concurrencyCap", "?")
    in_flight = [task for task in tasks if task.get("status") in {"running", "verify"}]
    running_ids = ", ".join(task.get("id", "?") for task in in_flight) or "none"
    candidate_ids = ", ".join(task.get("id", "?") for task in candidates) or "none"
    note = board.get("parallelismNote") or ""
    return f"""
      <section class="panel">
        <h2>Parallelization Audit</h2>
        <div class="metrics">
          <div><b>{h(len(in_flight))}</b><span>in flight</span></div>
          <div><b>{h(cap)}</b><span>cap</span></div>
          <div><b>{h(candidate_ids)}</b><span>next dispatch candidates</span></div>
        </div>
        <p><b>Running or verifying:</b> {h(running_ids)}</p>
        <p><b>Capacity read:</b> {h(reason)}</p>
        {f'<p><b>Controller note:</b> {h(note)}</p>' if note else ''}
      </section>
    """


def message_sort_key(message):
    status_rank = 0 if message.get("status") == "open" else 1
    created = str(message.get("createdAt", ""))
    return (status_rank, created, str(message.get("id", "")))


def render_messages(messages):
    if not isinstance(messages, list):
        messages = []
    usable = [m for m in messages if isinstance(m, dict)]
    open_count = sum(1 for m in usable if m.get("status") == "open")
    cards = []
    for message in sorted(usable, key=message_sort_key):
        msg_type = message.get("type", "unknown")
        type_class = msg_type if msg_type in MESSAGE_TYPES else "unknown"
        targets = message.get("toTasks") if isinstance(message.get("toTasks"), list) else []
        target_text = ", ".join(str(t) for t in targets) if targets else "all"
        cards.append(f"""
          <article class="message message-{h(type_class)}">
            <div class="message-head">
              <span class="task-id">{h(message.get("id", "?"))}</span>
              <b>{h(message.get("subject", ""))}</b>
            </div>
            <div class="chips">
              {chip("type", msg_type)}
              {chip("status", message.get("status"))}
              {chip("from", message.get("fromTask"))}
              {chip("to", target_text)}
              {chip("created", message.get("createdAt"))}
            </div>
            <p>{h(message.get("body", ""))}</p>
          </article>
        """)
    body = "".join(cards) if cards else "<div class=\"empty\">No coordination messages</div>"
    return f"""
      <section class="panel">
        <h2>Coordination Messages <span class="muted">{h(open_count)} open</span></h2>
        <p class="muted">Controller-mediated messages only. These are context artifacts, not workflow state transitions.</p>
        <div class="messages">{body}</div>
      </section>
    """


def render_html(data, rendered_at):
    plan = data.get("plan", {})
    board = data.get("board", {})
    tasks = data.get("tasks", [])
    messages = data.get("messages", [])
    by_id = {task.get("id"): task for task in tasks if task.get("id")}
    by_status = {
        status: sorted([task for task in tasks if task.get("status") == status], key=sort_key)
        for status in STATUS_ORDER
    }
    done = len(by_status["done"])
    total = len(tasks)
    progress = f"{done}/{total}" if total else "0/0"
    models = board.get("models") if isinstance(board.get("models"), dict) else {}
    open_message_count = (
        sum(1 for m in messages if isinstance(m, dict) and m.get("status") == "open")
        if isinstance(messages, list)
        else 0
    )

    columns = []
    for status in STATUS_ORDER:
        cards = "".join(render_task(task, by_id) for task in by_status[status])
        if not cards:
            cards = "<div class=\"empty\">No tasks</div>"
        columns.append(f"""
          <section class="column">
            <h2>{h(STATUS_LABELS[status])} <span>{len(by_status[status])}</span></h2>
            {cards}
          </section>
        """)

    model_rows = "".join(
        f"<span class=\"chip\"><b>{h(tier)}</b>{h(model)}</span>"
        for tier, model in sorted(models.items())
    )

    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <meta http-equiv="cache-control" content="no-store">
  <title>{h(plan.get("slug", "plan"))} board</title>
  <style>
    :root {{
      --bg: #f6f7f9;
      --panel: #ffffff;
      --text: #17191c;
      --muted: #636b74;
      --border: #d7dce2;
      --accent: #2563eb;
      --ready: #0f766e;
      --running: #b45309;
      --verify: #6d28d9;
      --done: #15803d;
      --blocked: #b91c1c;
      --deferred: #475569;
    }}
    * {{ box-sizing: border-box; }}
    body {{
      margin: 0;
      background: var(--bg);
      color: var(--text);
      font: 14px/1.45 -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
    }}
    header.page {{
      background: var(--panel);
      border-bottom: 1px solid var(--border);
      padding: 20px 24px;
      position: sticky;
      top: 0;
      z-index: 2;
    }}
    h1 {{ font-size: 22px; margin: 0 0 8px; }}
    h2 {{ font-size: 14px; margin: 0 0 12px; }}
    h3 {{ font-size: 14px; margin: 0; }}
    .subtle, .muted {{ color: var(--muted); }}
    .topline {{ display: flex; gap: 10px; flex-wrap: wrap; align-items: center; }}
    .chip {{
      display: inline-flex;
      gap: 5px;
      align-items: center;
      border: 1px solid var(--border);
      border-radius: 999px;
      padding: 3px 8px;
      margin: 2px;
      background: #fff;
      color: #2f3640;
      font-size: 12px;
      white-space: nowrap;
    }}
    .panel {{
      margin: 16px 24px 0;
      padding: 14px 16px;
      background: var(--panel);
      border: 1px solid var(--border);
      border-radius: 8px;
    }}
    .metrics {{ display: flex; gap: 12px; flex-wrap: wrap; margin-bottom: 8px; }}
    .metrics div {{
      min-width: 120px;
      border: 1px solid var(--border);
      border-radius: 6px;
      padding: 8px 10px;
      background: #fbfcfd;
    }}
    .metrics b {{ display: block; font-size: 18px; }}
    .metrics span {{ color: var(--muted); font-size: 12px; }}
    .board {{
      display: grid;
      grid-template-columns: repeat(7, minmax(240px, 1fr));
      gap: 12px;
      padding: 16px 24px 24px;
      overflow-x: auto;
    }}
    .column {{
      min-width: 240px;
      background: #eceff3;
      border: 1px solid var(--border);
      border-radius: 8px;
      padding: 10px;
    }}
    .column h2 {{ display: flex; justify-content: space-between; color: #303741; }}
    .task {{
      background: var(--panel);
      border: 1px solid var(--border);
      border-left: 4px solid #9aa3af;
      border-radius: 8px;
      padding: 10px;
      margin-bottom: 10px;
    }}
    .task-ready {{ border-left-color: var(--ready); }}
    .task-running {{ border-left-color: var(--running); }}
    .task-verify {{ border-left-color: var(--verify); }}
    .task-done {{ border-left-color: var(--done); }}
    .task-blocked {{ border-left-color: var(--blocked); }}
    .task-deferred {{ border-left-color: var(--deferred); }}
    .task header {{ display: flex; gap: 8px; align-items: baseline; }}
    .task-id {{ font-weight: 700; color: var(--accent); }}
    .messages {{
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(280px, 1fr));
      gap: 10px;
    }}
    .message {{
      border: 1px solid var(--border);
      border-left: 4px solid #64748b;
      border-radius: 8px;
      padding: 10px;
      background: #fff;
    }}
    .message-blocker {{ border-left-color: var(--blocked); }}
    .message-risk {{ border-left-color: var(--running); }}
    .message-question {{ border-left-color: var(--verify); }}
    .message-interface-note {{ border-left-color: var(--accent); }}
    .message-handoff {{ border-left-color: var(--ready); }}
    .message-discovery {{ border-left-color: var(--done); }}
    .message-head {{ display: flex; gap: 8px; align-items: baseline; }}
    .message p {{ margin: 8px 0 0; }}
    .chips {{ margin: 7px 0; }}
    .field {{ border-top: 1px solid #edf0f2; padding-top: 7px; margin-top: 7px; }}
    .label {{ color: var(--muted); font-size: 11px; text-transform: uppercase; letter-spacing: 0; }}
    ul {{ margin: 4px 0 0 18px; padding: 0; }}
    .empty {{ color: var(--muted); padding: 14px 4px; text-align: center; }}
    @media (max-width: 900px) {{
      header.page {{ position: static; }}
      .board {{ grid-template-columns: repeat(7, minmax(220px, 1fr)); padding: 12px; }}
      .panel {{ margin: 12px; }}
    }}
  </style>
</head>
<body>
  <header class="page">
    <h1>{h(plan.get("objective") or plan.get("slug") or "Plan board")}</h1>
    <div class="topline">
      {chip("plan", plan.get("slug"))}
      {chip("status", board.get("status"))}
      {chip("progress", progress)}
      {chip("controller", board.get("controller"))}
      {chip("worktrees", board.get("worktreeRoot"))}
      {chip("open messages", open_message_count)}
      {chip("board updated", board.get("updatedAt"))}
      {chip("rendered", rendered_at)}
    </div>
    <div class="topline">{model_rows}</div>
  </header>
  {render_parallel_audit(tasks, by_id, board)}
  {render_messages(messages)}
  <main class="board">
    {''.join(columns)}
  </main>
</body>
</html>
"""


def parse_args(argv):
    parser = argparse.ArgumentParser(description="Render a plan-loop-executor board as HTML.")
    parser.add_argument("board", help="Path to the board JSON file")
    parser.add_argument("--output", "-o", help="Path to write HTML. Defaults to board.viewer.htmlPath or <board>.html.")
    return parser.parse_args(argv)


def main(argv=None):
    args = parse_args(argv or sys.argv[1:])
    board_path = Path(args.board)
    data = read_json(board_path)
    output_path = output_path_for(board_path, data, args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    rendered_at = utc_now()
    output_path.write_text(render_html(data, rendered_at), encoding="utf-8")
    print(f"rendered board HTML: {output_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
