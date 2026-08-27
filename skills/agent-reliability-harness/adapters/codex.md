# Codex Runtime Adapter

Use Codex Plan mode for difficult or ambiguous work. It can inspect repository context,
ask material clarifying questions, and form the implementation plan. The harness must not
mirror that plan into another checklist while the session remains sufficient.

## Mode Mapping

- **Native:** Codex Plan plus the active task state; no harness files.
- **Portable:** materialize the approved plan when work must survive a task, model, or
  runtime boundary.
- **Audited:** use targeted controls for high-risk work; continue to accept legacy Full
  artifacts during resume.

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

Count only new evidence, an artifact change, a test result, or a binding decision that
advances the named acceptance boundary. After two no-progress cycles, stop the current
chain. Pass facts, assumptions, the current hypothesis, and one falsifying experiment to at
most one fresh bounded diagnosis; do not pass the full transcript or increase reasoning
effort.

## Subagents

Use three implementation lanes. The v3 micro lane requires explicit, auditable confirmations of
`scope-local`, `low-risk`, `no-protected-boundary`, `context-complete`, `short-verification`, and
`delegation-cost-higher`; these assertions are not automatic proof, and the parent must verify
their truth. A confirmed micro implementation may stay in the parent/main thread. Ordinary or
execution-heavy implementation uses one bounded native child worker by default when the runtime
exposes one. Complex work may use parallel workers only for independent modules; tightly coupled
writes stay serial or under one owner. Keep shared configuration, entrypoints, lockfiles, shared
tests, and generated files with the integration owner. A user's explicit delegation request
overrides the micro direct choice. Non-implementation work stays in the active thread when
delegation adds no value. The parent owns the goal, short plan, dispatch, status, integration, and
acceptance. Child workers are leaves and do not recursively delegate.

Persist only worker goal, ownership, result envelope, and evidence needed for continuation.
Native thread IDs may be supporting metadata but cannot be required by another runtime.

### Named Luna Worker

When Codex exposes an installed custom agent named `luna_worker`, it is the preferred
Luna `max` lane for a bounded long, mechanical, or independently verifiable task. Its use is
conditional: do not assume another installation has the same agent.

- Start it with `fork_turns=none`; provide a self-contained task, allowed scope, expected
  output, verification, and stop rule.
- Do not send it fuzzy architecture, product decisions, or final acceptance ownership.
- Confirm the spawned agent type and resolved model from runtime evidence before reporting
  that Luna ran.
- If the named agent is unavailable, try another verifiable bounded worker. If no such worker
  is available, block implementation unless the user explicitly authorizes parent direct execution
  for that task. This authorization is a fallback for a failed worker route, not a reason to turn
  ordinary implementation into an untracked parent loop. If the requested model cannot be parsed
  or resolved, record the unresolved route and do not claim that the requested child or model ran.
  Do not create configuration as a side effect of a task.

Parent direct execution requires explicit user authorization when it is used as a worker-route
fallback.

## Optional Model Routing

Model selection follows mode selection and remains adapter-local. The parent/main Agent uses
`gpt-5.6-sol` with `high` for the goal, short plan, dispatch, status, integration, acceptance,
and a confirmed v3 micro implementation. A child execution Agent uses `gpt-5.6-luna` with `max`
for one bounded ordinary, heavy, mechanical, or independently verifiable task. The `main`
profile is the parent manager/direct-micro route; `fast` is the child route. Keep mechanical
batch routing distinct from the `--micro-implementation` selector signal. Do not use the micro
route with sealed v1/v2 policies; historical runs retain their original maps.

Use Sol `high` for one bounded planning or diagnosis question, or one concrete high-risk
acceptance review. Give it an explicit output contract and stop rule. Do not route a stalled
path to Sol until a new diagnosis exists; use `model_router.py --new-diagnosis` after
recording the changed hypothesis or evidence.

Before acceptance, inspect the actual diff and integration boundary and run decisive
verification; never rely only on a worker report. Record requested and resolved models
separately. If the runtime cannot honor an implementation profile, try another verifiable
bounded worker; otherwise block unless the user explicitly authorizes parent execution.

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
