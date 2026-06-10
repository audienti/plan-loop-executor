# Changelog

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
