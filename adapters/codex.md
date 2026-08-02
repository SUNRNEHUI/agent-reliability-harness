# Codex Runtime Adapter

Use Codex Plan mode for difficult or ambiguous work. It can inspect repository context,
ask material clarifying questions, and form the implementation plan. The harness must not
mirror that plan into another checklist while the session remains sufficient.

## Mode Mapping

- **Native:** Codex Plan plus the active task state; no harness files.
- **Portable:** materialize the approved plan when work must survive a task, model, or
  runtime boundary.
- **Audited:** enable legacy Full controls or targeted extensions for high-risk work.

Plan mode does not itself provide cross-provider durability. Before transfer, materialize
the outcome, criteria, decisions, next action, workspace fingerprint, and evidence index.

## Context Efficiency

Keep `SKILL.md` as the stable prompt prefix and dynamic task state in the generated
capsule. On resume, read `capsule.md` first. Do not load full trace, TDD history, lessons,
or old reports unless `read_if_needed` identifies a real gap.

Codex may preserve reasoning within its own multi-turn runtime. Treat that as an execution
optimization, never as portable source of truth. A stale plan or reasoning item must not
override current workspace evidence.

## Progress Circuit Breaker

Count only new evidence, an artifact change, a test result, or a binding decision as
progress. After two no-progress cycles, stop the current chain. Pass facts, assumptions, the
current hypothesis, and one falsifying experiment to at most one fresh bounded diagnosis;
do not pass the full transcript or increase reasoning effort.

## Subagents

Use native subagents for disjoint, read-heavy exploration, tests, triage, or review when
parallel work materially improves time or quality. They consume additional tokens, so do
not dispatch a worker for work the main thread can finish more cheaply. Avoid parallel
writes to shared files or state.

Persist only worker goal, ownership, result envelope, and evidence needed for continuation.
Native thread IDs may be supporting metadata but cannot be required by another runtime.

## Optional Model Routing

Model selection follows mode selection and remains adapter-local. When explicit routing is
available, use `gpt-5.6-luna` with `max` for both long-running implementation/integration and
mechanically verifiable execution. A tiny task stays in the active thread when dispatch
would cost more than the work.

The active Codex parent may remain on `gpt-5.6-sol` with `max` as planner and acceptance
owner. The `main` profile below is an execution route, not the parent session default.

Use `gpt-5.6-sol` with `max` only as a bounded burst for one planning or diagnosis question,
or one concrete high-risk acceptance review. Give it an explicit output contract and stop
rule. Do not route a stalled path to Sol until a new diagnosis exists; use
`model_router.py --new-diagnosis` after recording the changed hypothesis or evidence.

Record requested and resolved models separately. If the runtime cannot honor a profile,
continue with its safe fallback and never claim that a model switch occurred.

## Permissions And Tools

Read relevant `AGENTS.md` files before edits. Record sandbox, writable scope, network,
browser, specialized tools, and worktree safety only when they affect the task. Missing
permission is a blocker or fallback, never fabricated evidence.

Use browser or device verification for meaningful user-visible behavior when available.
Run the smallest relevant tests, inspect the diff, and state any unverified path.

## Resume

```bash
python3 <skill-dir>/scripts/harnessctl.py resume <project-root> \
  --runtime codex --actor-id <session-id>
```

If another owner is active, add a concrete takeover reason. Carry the returned epoch on
later mutations. Reconcile drift before the recorded action.
