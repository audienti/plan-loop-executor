# Plan Loop Executor

Plan Loop Executor is a Codex and Claude Code plugin that turns a substantive
written implementation plan into a durable execution board and a controller-owned
task loop.

It is meant for work that is too large to execute safely from chat memory alone:
multi-task implementation plans, dependency sequencing, test-first execution,
sub-agent fan-out, structured coordination messages, resumable state, and explicit
verification gates.

## What the plugin provides

- A `plan-loop-executor` skill under `skills/plan-loop-executor/`
- Board templates and examples under `skills/plan-loop-executor/assets/`
- Board validation, status, and HTML rendering helpers under
  `skills/plan-loop-executor/scripts/`
- Codex marketplace metadata at `.codex-plugin/plugin.json`
- Claude Code marketplace metadata at `.claude-plugin/plugin.json`

## When to use it

Use this plugin for substantive coding or product implementation plans that can
be decomposed into roughly four or more independently verifiable tasks.

Skip it for small jobs. If a task can be completed directly with normal
engineering care, the board is overhead.

Good triggers:

- "Execute `docs/plans/my-feature.md` with the plan loop executor."
- "Turn this plan into a controller board and work it."
- "Resume the active plan loop board in this repo."
- "Work this implementation plan with sub-agents where safe."

## Runtime behavior

The skill requires a real plan artifact before it starts. The artifact can be a
repo file, a pasted plan, or a structured spec that the agent first turns into a
plan file.

The controller then:

1. Checks for an existing active board and resumes it if present.
2. Establishes a clean, verified baseline.
3. Creates or updates a repo-local board file.
4. Renders a read-only HTML kanban snapshot beside the board.
5. Breaks the plan into narrow, verifiable tasks.
6. Writes verification before or with implementation.
7. Fills safe sub-agent capacity when tasks are independent.
8. Records structured sub-agent messages through the controller.
9. Runs task verification and repo checks before marking work done.
10. Commits one green task at a time.
11. Stops only when acceptance criteria pass, the board stalls, or a real blocker
   needs user input.

The board is the source of truth, not the transcript.

Preflight allows the referenced plan artifact to be uncommitted or branch-local; it
does not need to be committed on `main` before the loop starts. Changes under
gitignored paths also do not block startup.

During setup, the controller also ensures there is a repo-local gitignored worktree
root for sub-agent work. It reuses an obvious ignored worktree folder when one already
exists; otherwise it creates `.worktrees/` and adds `.worktrees/` to
`.gitignore`. Sub-agent git worktrees should then be created under that ignored root.

The HTML board is generated from the JSON board and is read-only. Refresh the HTML file
to see current task titles, columns, in-flight worktrees, model routing, blockers, and a
parallelization audit that explains whether available sub-agent capacity is being used.

Sub-agents do not use peer-to-peer chat. They can emit structured messages such as
`blocker`, `interface-note`, `handoff`, `discovery`, `question`, and `risk`; the
controller records them on the board, routes relevant open messages into future
dispatch prompts, and resolves them once incorporated.

## Model routing

Plan with a strong model, execute with the cheapest model that can pass verification.

- Every task gets a `modelTier` at decomposition: `fast` for mechanical, tightly
  specified work, `default` for ordinary implementation, and `max` for interfaces,
  cross-cutting changes, and hard debugging.
- `board.models` maps tiers to concrete models per board. `"inherit"` uses the
  session model, so routing is off until a board opts in — and model names never live
  in the skill itself, so nothing rots when models change.
- Dispatch resolves the tier and passes the model to the worker (for example
  `codex exec -m <model>`).
- A failed attempt may escalate the task's tier one step as part of trying a
  different approach, recorded on the board.
- Choose tier mappings by a model's demonstrated strength on that kind of work and by
  attempts-per-solve, not by size or price-per-token. Close-out (and
  `board_status.py`) report attempts-per-solve by tier, so every board builds local
  routing evidence for the next one.
- Provider errors — rate limits, stale model names — are not task failures: dispatch
  falls back one tier (or to `"inherit"`) without consuming an attempt, and the
  substitution is noted on the board.
- The controller always runs on the session model. The loop economizes on workers,
  never on the judge — tests-first plus controller re-verification is what makes
  cheap workers safe, bounding a weak model's failure to one retried task.

## Helper commands

From the skill directory:

```bash
python3 scripts/validate_board.py docs/plans/<slug>-board.json
python3 scripts/board_status.py docs/plans/<slug>-board.json
python3 scripts/render_board.py docs/plans/<slug>-board.json
```

When invoked by the plugin, these paths are relative to
`skills/plan-loop-executor/`.

## Repository layout

```text
.codex-plugin/plugin.json
.claude-plugin/plugin.json
skills/plan-loop-executor/SKILL.md
skills/plan-loop-executor/assets/board-template.json
skills/plan-loop-executor/assets/example-board.json
skills/plan-loop-executor/scripts/board_status.py
skills/plan-loop-executor/scripts/render_board.py
skills/plan-loop-executor/scripts/validate_board.py
.worktrees/                       # created in target repos during loop setup when needed
```

## Marketplace source

Marketplace entries can reference this repository:

```text
https://github.com/audienti/plan-loop-executor.git
```

For the Audienti Codex marketplace catalog, the entry should use:

```json
{
  "name": "plan-loop-executor",
  "source": {
    "source": "url",
    "url": "https://github.com/audienti/plan-loop-executor.git"
  },
  "policy": {
    "installation": "AVAILABLE",
    "authentication": "ON_INSTALL"
  },
  "category": "Engineering"
}
```

## License

Copyright (c) 2026 OMALab, Inc. All rights reserved.

This plugin is not open source. Wholesale copying, redistribution, resale, or
publication of substantial portions requires prior written permission. Fair use,
short quotations, references, summaries, links, and commentary are not limited;
attribution to OMALab, Inc. and a link to this repository are requested when
quoting or referencing the work.

## Validation

Validate the plugin manifest and skill packaging with:

```bash
python3 /Users/williamflanagan/.codex/skills/.system/plugin-creator/scripts/validate_plugin.py .
python3 /Users/williamflanagan/.codex/skills/.system/skill-creator/scripts/quick_validate.py skills/plan-loop-executor
python3 skills/plan-loop-executor/scripts/validate_board.py skills/plan-loop-executor/assets/example-board.json
python3 skills/plan-loop-executor/scripts/render_board.py skills/plan-loop-executor/assets/example-board.json --output /tmp/plan-loop-example-board.html
```
