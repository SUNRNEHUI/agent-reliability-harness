---
name: agent-reliability-harness
description: >
  Use when the user says "你是主 agent" or "写一个 harness", explicitly requests a
  harness, multi-agent delegation, parallel workers, durable handoff, cross-model
  continuation, resumable execution, or protected evidence-based acceptance beyond the
  repository's normal workflow. Route through Native, Portable, or Audited execution.
  Ordinary implementation, planning, and testing do not trigger this skill by themselves.
---

# Agent Reliability Harness

Add only controls missing from the runtime or repository.

## Workflow Composition

For code changes, apply the repository's established coding workflow or an available matching
coding skill. Harness does not replace, copy, or weaken it. Do not require a particular
companion skill by name.

## Mode Gate

Choose once before adding process:

| Mode | Use when | Durable state |
| --- | --- | --- |
| **Native** | Default. Implement and verify without costly reconstruction. | None; use runtime plan/task state. |
| **Portable** | Work must survive a session/model boundary, external wait, or context loss. | `.harness/<slug>/contract.json`, `events.jsonl`, `capsule.md` |
| **Audited** | A protected or disputed boundary needs typed proof. | Only justified witness, receipt, fencing, or trace controls. |

If Native fits, keep persistence/evidence light. Do not load references, create harness files, or
add audit controls solely because this skill triggered. Mode controls persistence and evidence depth;
delegation is independent of mode.

## Execution Shape

Use three routes. V3 micro work may stay on the parent/main route only after explicit
`scope-local`, `low-risk/no-protected-boundary`, `context-complete`, `short-verification`, and
`delegation-cost-higher` confirmations; the parent checks their truth. Ordinary or execution-heavy
work uses one bounded worker. Complex work parallelizes only independent modules or ownership
boundaries; coupled writes stay serial or have one owner. Explicit user delegation overrides the
micro direct route. Non-implementation work may stay in the current thread. Write one runtime
plan before dispatch and track worker status and evidence in runtime state.

Main agent owns goal, plan, dispatch, status, integration, and acceptance. It inspects the
diff/boundary and runs decisive verification; worker reports never establish completion. Workers
need bounded scope, output, verification, and a stop rule; they do not recursively delegate.
Try another verifiable bounded worker first. If none exists or resolution fails, block; parent
fallback needs explicit user authorization. Never claim an unverified route. Retry only when
diagnosis changes the task or evidence.

## Goal And Acceptance

Name outcome, observable `done_when`, constraints, approval boundaries, non-goals, and evidence.
Use runtime plan; do not mirror it. Use a durable goal tool at user request or
when the objective is not measurable.

Prefer evidence. Persist observable state, never hidden reasoning, chats, secrets, or provider
sessions. Plans, reports, scores, reviews, and PASS are not completion.

## Progress Circuit Breaker

Count only **new evidence**, an **artifact change**, a **test result**, or a **binding
decision** that advances a named `done_when` criterion or named critical-path blocker.
Activity outside it does not count as progress. Generated metadata, reports,
package rebuilds, broad inventory, and auxiliary tests do not reset the breaker unless the
criterion requires them.

After two consecutive no-progress cycles, mark `STALLED`, separate facts/assumptions, and run
the cheapest falsifying experiment. If no evidence, stop; use at most one fresh bounded
diagnosis or report the blocker. Stagnation must not increase reasoning effort or fan-out.

## Durable And Audited Work

Materialize Portable state after an actionable plan and durability trigger. Checkpoint at
verified boundaries; contract is source of truth and capsule is generated resume context. Read
`references/portable-contract.md` before materialize, handoff, resume, or close.

For Audited work, protect the risky transition or claim with witness, test chronology, receipt,
fencing, or approval. Read `references/harness-protocol.md` and one control reference before
adding artifacts. New runs use `mode: audited`; legacy `mode: full` remains readable and resumable.

## Accept And Stop

Inspect decisive evidence before completion. Stop for unresolved approval, scope expansion,
ownership conflict, missing environment, unsafe effects, or repeated failure without new
diagnosis. Report files, verification, risk, and next action.

## Load On Demand

| Need | Read |
| --- | --- |
| Mode unclear or progress stalled | `references/proportionality.md` |
| Portable schema or resume | `references/portable-contract.md` |
| Audited or legacy state | `references/harness-protocol.md` |
| Stateful behavior | `references/state-witness.md` |
| Protected TDD chronology | `references/tdd-gates.md` |
| Detailed stop rules | `references/stop-conditions.md` |
| Public JSON/CLI contracts | `references/public-contracts.md` |
| Runtime behavior | one relevant file under `adapters/` |
| Optional model routing | `references/model-routing.md` plus the runtime adapter |

Default here. Load one reference only when the mode or a blocker requires it.

---

*Agent Reliability Harness v9.3.0 | 2026-08-27*
