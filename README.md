# Plan Loop Executor

Plan Loop Executor is a Codex and Claude Code plugin that turns a substantive
written implementation plan into a durable execution board and a controller-owned
task loop.

It is meant for work that is too large to execute safely from chat memory alone:
multi-task implementation plans, dependency sequencing, test-first execution,
sub-agent fan-out, resumable state, and explicit verification gates.

## What the plugin provides

- A `plan-loop-executor` skill under `skills/plan-loop-executor/`
- Board templates and examples under `skills/plan-loop-executor/assets/`
- Board validation and status helpers under `skills/plan-loop-executor/scripts/`
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
4. Breaks the plan into narrow, verifiable tasks.
5. Writes verification before or with implementation.
6. Runs task verification and repo checks before marking work done.
7. Commits one green task at a time.
8. Stops only when acceptance criteria pass, the board stalls, or a real blocker
   needs user input.

The board is the source of truth, not the transcript.

## Helper commands

From the skill directory:

```bash
python3 scripts/validate_board.py docs/plans/<slug>-board.json
python3 scripts/board_status.py docs/plans/<slug>-board.json
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
skills/plan-loop-executor/scripts/validate_board.py
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
```
