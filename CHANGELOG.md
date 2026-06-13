# Changelog

## 0.4.0 - 2026-06-13

- Added a controller-mediated `messages` log for structured sub-agent coordination.
- Added message validation for ids, task references, message types, and statuses.
- Updated board status and HTML rendering to surface open coordination messages.
- Updated dispatch instructions so relevant open messages are included as context for
  future sub-agent runs without allowing peer-to-peer hidden state.

## 0.3.0 - 2026-06-13

- Added `render_board.py`, which generates a read-only HTML kanban snapshot from the
  JSON board.
- Added `board.viewer.htmlPath`, `board.parallelismNote`, and task observability fields
  for worktree, timestamps, and resolved model.
- Updated loop rules to audit available sub-agent capacity, fill safe parallel batches,
  and record why capacity is unused.
- Updated validation/status helpers to surface viewer and parallelization state without
  breaking older boards.

## 0.2.0 - 2026-06-10

- Added model routing: every task carries a `modelTier` (`fast`, `default`, `max`)
  assigned at decomposition based on task complexity.
- Added `board.models`, a per-board map from tiers to concrete models, with
  `"inherit"` as the default so routing is opt-in and model names never live in the
  skill.
- Dispatch now resolves the task tier through `board.models` and passes the model to
  the worker command (for example `codex exec -m <model>`).
- Failed attempts may escalate a task's tier one step as part of a different
  approach; the controller itself always runs on the session model.
- Board validation enforces tier values and the `board.models` shape; the status
  helper shows non-default tiers in flight and tier on next-up tasks.
- Routing guidance: map tiers by a model's demonstrated strength per work type
  (capability is shaped, not scalar) and judge mappings by attempts-per-solve.
- Provider/dispatch failures no longer consume task attempts; dispatch falls back one
  tier (or to `"inherit"`) and records the substitution in task notes.
- Close-out and `board_status.py` report attempts-per-solve by model tier as local
  routing evidence; dispatch announcements include task id, tier, and resolved model.

## 0.1.2 - 2026-06-10

- Added setup guidance to ensure a repo-local gitignored worktree root exists,
  defaulting to `.worktrees/` when no obvious ignored worktree folder is present.
- Documented that sub-agent git worktrees should be created under the recorded ignored
  worktree root.
- Added `board.worktreeRoot` to the board templates and status output.

## 0.1.1 - 2026-06-10

- Clarified that the referenced plan artifact does not need to be committed on `main`
  before the loop can start.
- Clarified that changes under gitignored paths do not block preflight.

## 0.1.0 - 2026-06-10

- Packaged Plan Loop Executor as a Codex plugin with `.codex-plugin/plugin.json`.
- Added Claude Code plugin metadata at `.claude-plugin/plugin.json`.
- Moved the skill into `skills/plan-loop-executor/` with its board assets and helper scripts.
- Documented marketplace source metadata and local validation commands.
- Added proprietary copyright and attribution license notice.
