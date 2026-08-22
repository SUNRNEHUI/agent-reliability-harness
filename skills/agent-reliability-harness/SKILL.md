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

If Native fits, stop routing and start the smallest executable or testable slice. Do not
load references, route models, create harness files, or dispatch a worker solely because
this skill triggered. Task size alone does not require durable state.

## Execution Shape

If work is small and clear, execute it directly in the current thread. For large or complex
work, write one runtime plan before dispatch. Split only at independent module or ownership
boundaries; when modules can progress independently, delegate them and track each
worker's status and evidence in runtime task state. Do not delegate tightly coupled work or
when coordination costs more than execution.

Saying "main agent" establishes acceptance ownership; this does not authorize delegation.
The main agent owns planning, integration, and acceptance. Workers need bounded scope, an
output contract, verification, and a stop rule. Retry only when diagnosis changes the task
or evidence.

## Goal And Acceptance

Name outcome, observable `done_when`, constraints, approval boundaries, non-goals, and
decisive evidence. Use the runtime plan; do not mirror it into another checklist. Use a
durable goal tool only at user request or when the objective is not measurable.

Prefer external evidence. Persist observable state, never hidden reasoning, chats, secrets,
or provider sessions. Plans, reports, scores, reviews, and harness PASS are not completion.

## Progress Circuit Breaker

Count only **new evidence**, an **artifact change**, a **test result**, or a **binding
decision** that advances a named `done_when` criterion or named critical-path blocker.
Activity outside that boundary does not count as progress. Generated metadata, reports,
package rebuilds, broad inventory, and auxiliary tests do not reset the breaker unless the
criterion requires them.

After two consecutive no-progress cycles, mark the path `STALLED`, separate facts from
assumptions, and run the cheapest falsifying experiment. If it yields no evidence, stop that
reasoning chain; use at most one fresh bounded diagnosis or report the blocker. Stagnation
must not increase reasoning effort or worker fan-out.

## Durable And Audited Work

Materialize Portable state only after the plan is actionable and a real durability trigger
exists. Checkpoint only at verified boundaries; the contract is source of truth and the
bounded capsule is generated resume context. Read `references/portable-contract.md` before
materialize, handoff, resume, or close.

For Audited work, protect only the risky transition or claim with the necessary witness,
test chronology, receipt, fencing, or approval. Read `references/harness-protocol.md` and
the one control-specific reference before adding artifacts. New runs use `mode: audited`;
legacy `mode: full` remains readable and resumable.

## Accept And Stop

Inspect the smallest decisive evidence before completion. Stop for unresolved approval,
scope expansion, ownership conflict, missing environment, unsafe effects, or repeated
failure without new diagnosis. Report changed files, verification, risk, and next action.

## Load On Demand

| Need | Read |
| --- | --- |
| Mode unclear or progress stalled | `references/proportionality.md` |
| Portable schema or resume | `references/portable-contract.md` |
| Audited or legacy state | `references/harness-protocol.md` |
| Stateful behavior | `references/state-witness.md` |
| Protected TDD chronology | `references/tdd-gates.md` |
| Detailed stop rules | `references/stop-conditions.md` |
| Runtime behavior | one relevant file under `adapters/` |
| Optional model routing | `references/model-routing.md` plus the runtime adapter |

Default to this file only. Load one additional reference only when the selected mode or a
real blocker requires it.

---

*Agent Reliability Harness v9.2.0 | 2026-08-22*
