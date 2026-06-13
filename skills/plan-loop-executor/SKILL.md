---
name: plan-loop-executor
description: >
  Execute a substantive implementation plan through a controller loop that requires a
  written plan artifact first. Use when the user says "implement this plan", "execute the
  plan", "work the plan", "run this as a loop", "use sub-agents", "turn this plan into a
  board", "controller loop", "kanban", "show me the board", "parallelize the plan", or
  "requires a plan" for non-trivial coding or product changes. Not for trivial work: if
  the plan yields fewer than ~4 independently verifiable tasks, skip the board and
  implement directly.
---

# Plan Loop Executor

Run substantive work from a real plan, not from ad hoc improvisation.

This skill is for cases where the user already has a plan, or wants execution to require
one before implementation starts.

## Core invariants

1. **No plan artifact, no loop execution.**
2. **Cold-start test.** A fresh controller given only the plan file and the board file
   must be able to continue correctly. If continuing would require the chat transcript,
   the board is incomplete — fix the board, not the transcript.
3. **Tests lead.** A task's verification is written before or with its implementation
   (red, then green) — never bolted on after the loop.
4. **Green trunk.** The loop starts from a verified-green baseline, the repo passes its
   checks after every completed task, and integration points gate on the full suite.
   Never accumulate broken intermediate states to "clean up at the end."
5. **One writer.** The controller owns every board transition. Sub-agents never write
   board state.
6. **No hidden coordination.** Sub-agents do not free-chat with each other. They emit
   structured messages as artifacts; the controller records, routes, and resolves them.
7. **Trust nothing unverified.** A worker's "tests pass" is a hypothesis. The controller
   re-runs verification itself before anything is marked `done`.
8. **Every loop terminates.** Retry caps and stall detection are mandatory, not
   optional.

Accepted plan artifacts:
- a repo file path
- a pasted plan in the conversation
- a structured spec that can be turned into a plan file first

If none exists, stop and ask for the plan.

The referenced plan artifact does not need to be committed on the repo's default
branch before the loop starts. A tracked, modified, untracked, or branch-local plan is
valid input as long as the controller can read its current contents and record the exact
source in the board.

## When not to use this

If the plan decomposes into fewer than ~4 independently verifiable tasks, the board and
controller are overhead with no payoff. Implement directly with ordinary care.

## Outcome

Turn a plan into:
1. a durable execution board
2. a controller-owned task loop
3. a read-only HTML kanban snapshot
4. verified implementation progress

The board is the visible state. The controller loop is the engine.

## Workflow

### 0. Resume check — always first

Before anything else, look for an existing board for this plan at
`docs/plans/<plan-slug>-board.json` (or wherever the repo keeps them).

If one exists with `board.status: "active"`:
- **Resume it. Never recreate it.**
- Reconcile the board against reality before continuing:
  - check `git log` / `git status` since `board.updatedAt` — do commits match `done`
    tasks?
  - if the working tree is dirty, attribute the changes to the in-flight (`running` or
    `verify`) task and continue that task; if the changes cannot be attributed, stop
    and ask before touching anything
  - cheaply re-run verification for recently `done` tasks if anything looks off
  - correct drift on the board, note the correction, then enter the loop at step 7.

### 1. Load the plan

- Read the plan artifact completely.
- Extract:
  - objective
  - scope
  - non-goals
  - constraints
  - acceptance criteria
  - verification commands
  - files/surfaces likely to change
  - explicit rollout or safety boundaries

If the plan is ambiguous on outcome or acceptance criteria, stop and ask — but only
here, before the loop starts. Mid-loop ambiguity is handled by step 11, not by halting.

### 2. Preflight — establish a clean starting state

The loop starts from a known-good baseline or it does not start.

- **Blocking worktree changes.** The repo must be clean enough to create a reliable
  baseline. Uncommitted changes to the referenced plan artifact are allowed, and
  changes under gitignored paths do not block the loop. Other uncommitted tracked or
  untracked changes must be resolved before starting unless they are explicitly part of
  the plan setup. Never stash or discard someone else's work autonomously. (On resume,
  dirty state is reconciled instead — step 0.)
- **Known base.** Default base is the repo's default branch as it currently stands.
  If a remote exists, fetch and fast-forward the default branch when it is behind;
  if the local default branch has diverged from its remote, stop and ask. The plan or
  the user may name a different base branch — honor that.
- **Green baseline.** Run the plan-level `verificationCommands` (or the repo's
  standard checks if the plan names none) once on the base, before any task starts.
  - Green: record it in `board.base` (`branch`, `commit`, `verifiedGreen: true`) and
    proceed.
  - Red: stop and report. Green trunk cannot be enforced from a red baseline. If the
    user explicitly authorizes proceeding over known failures, record the exact
    exclusions in the plan constraints — those failures are the baseline, and nothing
    new may join them.
- **Own branch.** Create `plan/<plan-slug>` from the base before the first commit. An
  unattended loop does not commit to the default branch.
- **Ignored worktree root.** Ensure the repo has a repo-local gitignored directory for
  sub-agent git worktrees before any dispatch. Reuse an existing ignored directory only
  when it is obviously intended for git worktrees. If none exists, create
  `.worktrees/` and add `.worktrees/` to `.gitignore` as a setup change. This
  setup change is allowed even though other unrelated uncommitted changes still gate
  startup. Record the selected path in `board.worktreeRoot` and use that root for
  subsequent sub-agent worktrees.

### 3. Create the execution board

Create a board file in the working repo before implementation starts.

Default location:
- `docs/plans/<plan-slug>-board.json`

If that location is unsuitable for the repo, choose another obvious repo-local path and
state it.

Use the template in `assets/board-template.json`. A filled, mid-flight example is in
`assets/example-board.json`.

Every task must include:
- `id`
- `title`
- `status`
- `priority`
- `dependsOn`
- `ownerLane`
- `modelTier`
- `files`
- `context`
- `doneWhen`
- `verification`
- `outputs`
- `attemptCount`
- `lastFailure`
- `commit`
- `notes`

Allowed task statuses:
- `backlog` — not yet ready; dependencies outstanding
- `ready` — all dependencies `done`; eligible for selection
- `running` — being executed by controller or sub-agent
- `verify` — artifacts returned; controller verification not yet run
- `done` — verification passed, repo green, commit recorded
- `blocked` — cannot proceed; exact blocker recorded
- `deferred` — intentionally postponed; reason recorded

Allowed `ownerLane` values:
- `controller` — the controller executes it directly
- `subagent` — independent; dispatchable under step 6

Allowed `modelTier` values (assigned in step 4, resolved at dispatch in step 6):
- `fast` — mechanical, tightly specified work; cheapest capable model
- `default` — ordinary implementation work
- `max` — judgment-heavy or high-blast-radius work; strongest available model

`board.models` maps each tier to a concrete model for this board, with `"inherit"`
meaning "use the session model". Concrete model names live only on the board — never
in this skill — so routing survives model renames and price changes.

Board lifecycle: `board.status` is `active` while the loop runs, `complete` when all
acceptance criteria pass, `abandoned` if the effort is stopped early (record why).
`board.base` records the preflight baseline from step 2.
`board.worktreeRoot` records the repo-local ignored directory used for sub-agent git
worktrees, usually `.worktrees/`.
`board.viewer.htmlPath` records the generated read-only HTML snapshot path, usually
`docs/plans/<plan-slug>-board.html`.
`board.parallelismNote` records the controller's current reason when capacity is not
being filled or when a fan-out decision matters.

Tasks may also include observability fields:
- `worktree` — repo-local worktree path used by a dispatched sub-agent
- `startedAt` — when the current/last active attempt started
- `updatedAt` — when this task last changed
- `resolvedModel` — concrete model used for the active/last dispatch, or `"inherit"`

The board may also include a controller-owned `messages` array. Messages are for
coordination only; they do not change task state by themselves. Every message includes:
- `id`
- `fromTask` — a task id or `controller`
- `toTasks` — task ids and/or `controller`; empty means generally relevant
- `type` — `blocker`, `interface-note`, `handoff`, `discovery`, `question`, or `risk`
- `subject`
- `body`
- `createdAt`
- `status` — `open`, `acknowledged`, `resolved`, or `superseded`

After every board write, validate it and render the HTML snapshot:

```
python3 scripts/validate_board.py docs/plans/<plan-slug>-board.json
python3 scripts/render_board.py docs/plans/<plan-slug>-board.json
```

(`scripts/validate_board.py` and `scripts/render_board.py` live in this skill's
directory.) A board that fails validation is fixed before anything else happens.

### 4. Turn the plan into a task graph

Break the plan into atomic tasks.

Task rules:
- one owner lane
- one real deliverable
- explicit verification — if a task's verification cannot be written down concretely,
  it is not yet a task
- explicit dependency list
- narrow enough to complete and verify cleanly
- self-contained `context`: the relevant plan excerpt, files to read, and constraints a
  cold worker needs to execute without the chat transcript. Write it at decomposition
  time, while the controller still has full context.

Sequencing rules:
- **Interfaces first.** Contracts, types, schemas, and function signatures that multiple
  tasks build on are their own tasks, completed serially before implementations fan
  out. The classic parallel failure is two workers implementing against different
  assumed interfaces — prevent it structurally, not by hoping.
- **Calendar time matters.** After interface tasks are complete, bias toward exposing
  independent `subagent` tasks with non-overlapping file ownership and concrete
  verification. A plan that could safely run in parallel should not be decomposed as a
  serial queue by default.
- **Tests first.** Where practical, a task starts by writing its verification as a
  failing test, then implementing to green. For behavior changes, the regression test
  is part of the task, not a follow-up task.
- **No broken commit points.** Every task must leave the repo green at its commit. If a
  change inherently passes through a broken state, widen the task to contain the whole
  transition, or resequence — never park breakage on the board for later.

Model routing:
- Assign every task a `modelTier` at decomposition time, while its complexity is
  already being judged:
  - `fast`: mechanical and tightly specified — renames, boilerplate, test scaffolding
    from a clear spec, doc updates, config plumbing.
  - `default`: ordinary implementation tasks.
  - `max`: interface and contract tasks, cross-cutting changes, hard debugging, and
    anything security- or data-sensitive.
- When in doubt, route up. A cheap worker that fails verification twice costs more in
  tokens and wall-clock than a strong worker that passes once.
- Capability is shaped, not scalar. A model can be strong at tool-heavy mechanical
  work and weak at code synthesis, or the reverse. Choose `board.models` mappings by a
  model's demonstrated strength on that kind of work, not by size or price.
- Judge mappings by attempts-per-solve, not cost-per-token. The board records
  `attemptCount` per task and close-out reports it by tier — that local evidence beats
  public leaderboards for tuning the next board's map.
- Tiers route dispatched sub-agents only. The controller always runs on the session
  model: decomposition, verification judgment, and retry decisions are the most
  expensive tokens to get wrong. Economize on workers, never on the judge.
- Tag `controller`-lane tasks `default`; their tier is not used for dispatch.
- Set the `board.models` map when creating the board. Leaving every tier `"inherit"`
  disables routing — tier tags still document complexity and can be activated later by
  editing the map.

Selection order for `ready` tasks: dependency order first, then highest `priority`,
then the task that unblocks the most others, then risk-first.

Do not create vague tasks like:
- "implement feature"
- "fix code"
- "improve system"

Prefer:
- "add repair override schema and store"
- "wrap buildNextView in repairable executor"
- "add regression tests for one-retry repair path"

### 5. Controller owns the workflow

One agent acts as controller.

The controller is responsible for:
- selecting the next safe batch of `ready` tasks
- deciding what can run in parallel
- dispatching sub-agents only for independent work
- re-running verification itself on every returned task — worker reports are inputs,
  never proof
- updating board state
- deciding whether to continue, split, retry, or block

Sub-agents do not own workflow state.

Sub-agents may:
- execute a narrow task
- return artifacts
- report blockers
- suggest follow-on tasks
- emit structured coordination messages for the controller to record

The controller decides what becomes real board state.

### 6. Dispatch rules and contract

Only dispatch sub-agents when all are true:
- the task is independent
- file ownership will not overlap
- verification is clear
- the task can be judged from artifacts

Do not parallelize if tasks touch the same files or same behavioral seam.

Default concurrency cap: 3 in-flight sub-agents (`running` + `verify`).

On every loop pass, calculate available sub-agent capacity and try to fill it with the
largest safe batch of independent `ready` sub-agent tasks. If capacity remains unused,
record the reason in `board.parallelismNote` before continuing. Valid reasons include
dependency gating, overlapping files, no available dispatch mechanism, pending
controller verification, or a controller-lane task that must complete before fan-out.

**Mechanism.** Dispatch means a real, fresh, non-interactive run per task — for
example `codex exec "<dispatch prompt>"` from the repo root, Claude Code's
non-interactive prompt mode, or this harness's native sub-agent primitive if one
exists. Never simulate a sub-agent by role-playing one inside the controller's own
context. If no dispatch mechanism is available, execute tasks sequentially as the
controller and say so — do not pretend the fan-out happened.

**Model selection.** Resolve the task's `modelTier` through `board.models` before
dispatch:
- `"inherit"` or unmapped: pass no model flag — the worker uses the session default.
- anything else: pass the mapped model to the dispatch command (for example
  `codex exec -m <model> ...`, or this harness's equivalent model option).

Where the harness supports a reasoning-effort setting, the controller may raise it for
`max`-tier and escalated tasks instead of, or in addition to, changing the model. The
controller itself never runs on a downgraded model.

**Dispatch failure is not task failure.** Provider errors — rate limits, auth
failures, stale or unavailable model names — never touch `attemptCount` or
`lastFailure`; those fields measure the work, not the infrastructure. On a provider
error, retry the dispatch on the next tier up (fast → default → max), or `"inherit"`
if already at `max`, and record the substitution in the task's `notes`. If even
`"inherit"` cannot dispatch, the controller executes the task directly.

When dispatch uses git worktrees, create them under `board.worktreeRoot` (for example
`.worktrees/<plan-slug>/<task-id>/`) so task-local checkouts stay out of tracked
repo state. Record that path in the task's `worktree`. Do not create ad hoc sibling
worktree folders outside the recorded ignored root.

**Dispatch prompt** is assembled mechanically from the board and plan, nothing else:
- plan objective, non-goals, constraints
- the task's `title`, `context`, `files`, `doneWhen`, `verification`
- relevant open `messages`: any addressed to this task, addressed to `controller`,
  or with an empty `toTasks` list. Include them as context, not as authority.
- instructions to: write the failing test first where applicable, run the task's
  verification before returning, return artifacts (diff, file list, command output) —
  not summaries — plus any blockers, structured messages, and suggested follow-on tasks,
  and write no board state.

### 7. Execution loop

Repeat until acceptance criteria pass, a stall is detected, or a real blocker requires
user input:

1. Promote newly unblocked tasks to `ready`.
2. Run a parallelization audit:
   - available capacity = `board.concurrencyCap` minus sub-agent tasks in `running` or
     `verify`
   - eligible tasks = `ready`, `ownerLane: "subagent"`, dependencies `done`, clear
     verification, no overlapping files or behavioral seam with in-flight work
   - dispatch the highest-priority safe batch up to available capacity
   - if capacity remains unused, update `board.parallelismNote` with the concrete
     reason instead of leaving the user to infer it
3. For each dispatched task, mark it `running`, set `startedAt`, `updatedAt`,
   `resolvedModel`, and `worktree` where applicable, then render the HTML board.
4. If no dispatchable sub-agent work exists, select the next controller-lane `ready`
   task by the selection order in step 4. Prefer controller tasks that unblock more
   parallel work before ordinary serial implementation.
5. If a selected task's verification does not exist yet, write the failing test first
   and confirm it fails for the right reason. Red before green.
6. Execute directly or dispatch per step 6.
7. When work returns, mark the task `verify`, update `updatedAt`, and collect
   artifacts — diffs, files, command output, and structured messages. Not summaries.
   Add valid messages to `messages` with controller-assigned ids if needed.
8. Controller runs the task's `verification` commands itself.
9. Controller runs the fast repo-wide checks (lint, typecheck, affected tests). Green
   trunk is part of every task's done condition.
10. If everything passes:
   - commit, message referencing the task id; record the SHA in `commit`
   - mark the task `done`, record `outputs`, promote newly-unblocked tasks to `ready`
11. If verification fails:
   - increment `attemptCount`, record the cause in `lastFailure`
   - attempt 2 must take a meaningfully different approach — the board says why the
     last attempt failed; use it
   - for dispatched tasks, escalating `modelTier` one step (fast → default → max) is a
     valid part of a different approach — update the task's tier and record the
     escalation in `notes`
   - at attempt 3, stop retrying: mark `blocked` with the exact blocker, or split into
     smaller tasks
12. **Integration gate.** Whenever a dependency chain completes — and before starting
    any task that builds on multiple `done` tasks — run the plan-level
    `verificationCommands` (full suite). All green before moving on. Per-task green
    does not imply composed green; catch integration breakage here, not at close-out.
13. **Stall check.** If a full pass over the board produces zero status transitions,
    the loop is stalled. Stop and report the true state. Do not keep iterating.
14. Update the board, validate it, render the HTML snapshot, continue.

### 8. Verification is mandatory

Never mark a task done without running its verification field.

Verification can include:
- targeted tests
- full test suite
- lint/typecheck
- CLI output
- artifact inspection
- repo-local proof commands

Rules:
- Tests are written before or alongside implementation, never bolted on at the end.
- A failing full suite blocks all `done` transitions until it is green again. There is
  no "fix the tests later" lane on this board.
- If the repo already has stronger verification than the plan states, prefer the
  stronger signal when practical.

### 9. Safety boundaries

Default to fail-closed on risky side effects unless the plan explicitly authorizes
them.

Examples:
- real sends
- destructive migrations
- live external writeback
- production deploys

If the plan defines phased rollout boundaries, preserve them.

### 10. Board maintenance rules

Update the board after every meaningful task transition, set `board.updatedAt`
(`date -u +%FT%TZ`), validate with `scripts/validate_board.py`, and render with
`scripts/render_board.py`. For progress updates to the user, `scripts/board_status.py`
prints a human-readable summary. The generated HTML is a read-only snapshot; never
edit it by hand or treat it as source state.

For coordination messages:
- record worker messages verbatim when safe, but assign/fix ids, timestamps, targets,
  and statuses as controller-owned metadata
- keep messages short and task-relevant
- resolve or supersede messages once they have been incorporated into a task, retry, or
  follow-on board change
- never let a message override the plan, dependency graph, or verification without the
  controller updating the board explicitly

Keep notes short and factual:
- what changed
- what verified
- what blocked

Do not let the board drift from reality. On any resume or doubt, reconcile per step 0.

### 11. Mid-loop questions

The loop runs unattended. Mid-loop, prefer momentum over questions:
- ambiguity with a safe, reversible default → record the assumption in the task's
  `notes` and proceed
- ambiguity without a safe default → mark the task `deferred` or `blocked`, continue
  other lanes, and batch the question for close-out
- safety-boundary ambiguity (step 9) → stop. That is the only mid-loop hard stop.

### 12. Final close-out

When all acceptance criteria pass:
- run the plan-level `verificationCommands` one final time
- mark all completed tasks accurately; set `board.status: "complete"`
- summarize remaining deferred items and batched questions
- report what verified
- report attempts-per-solve by model tier (and mapped model) — the local routing
  evidence for tuning the next board's `board.models`
- report any residual risks

If the effort is stopped early, set `board.status: "abandoned"` and record why.

## Deliverable format

During execution:
- give short progress updates
- reference the active board path and generated HTML path
- say what task is being worked
- announce routing on dispatch: task id, tier, and resolved model
- if fewer sub-agents are running than `concurrencyCap`, say why in
  `board.parallelismNote`
- say what verified or blocked

At completion:
- objective status
- acceptance criteria status
- high-signal summary of what changed
- verification run
- batched questions and assumptions made
- remaining risks or deferrals

## Default assumptions

If the user does not specify otherwise:
- resume an existing active board; otherwise create a repo-local board file
- start from the repo's current default branch, verified green, on a fresh
  `plan/<plan-slug>` branch, allowing the referenced plan artifact to be uncommitted
  and ignoring changes under gitignored paths
- create or reuse a repo-local ignored git worktree root, defaulting to
  `.worktrees/`, and record it as `board.worktreeRoot`
- use one controller and record the active runtime name in `board.controller`
- use sub-agents only for clearly independent tasks
- tag every task with a `modelTier` and map tiers in `board.models`, leaving every
  tier `"inherit"` (routing off) until a board opts in
- write tests first; one commit per task; repo green at every commit
- keep the loop running until the plan is actually implemented, a stall is detected, or
  a real blocker appears
