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

The work is the product. Add only controls missing from the runtime or repository.

## Mode Gate

Make one decision before adding process:

| Mode | Use when | Durable state |
| --- | --- | --- |
| **Native** | Default. Implement and verify without costly reconstruction. | None; use runtime plan/task state. |
| **Portable** | Work must survive a session/model boundary, external wait, or context loss. | `.harness/<slug>/contract.json`, `events.jsonl`, `capsule.md` |
| **Audited** | A protected or disputed boundary needs typed proof. | Only justified witness, receipt, fencing, or trace controls. |

If Native fits, stop routing and start the smallest executable or testable slice. Do not
load references, route models, create harness files, or dispatch a worker solely because
this skill triggered. Saying "main agent" establishes acceptance ownership; this does not
authorize delegation.

## Goal And Acceptance

Name the user-visible outcome, observable `done_when`, constraints, approval boundaries,
non-goals, and decisive evidence.
Use the runtime's existing plan; do not mirror it into another checklist.

Use an available durable goal tool or `define-goal` only when the user requests goal-backed
execution or the objective is not measurable. Do not create a goal merely because this
skill triggered.

Prefer external evidence. Persist observable state, never hidden reasoning, chats, secrets,
or provider sessions. Plans, reports, scores, reviews, and harness PASS are not completion.

## Progress Circuit Breaker

Count progress only when **new evidence**, an **artifact change**, a **test result**, or a
**binding decision** directly advances a named `done_when` criterion or a named critical-path
blocker. Activity outside the current acceptance boundary does not count as progress.
Generated metadata, reports, package rebuilds, broad inventory, and auxiliary tests do not
reset the breaker unless the named criterion requires them.

- Plan only the next one to three actions. Execute a safe reversible action once it can
  distinguish the current hypotheses.
- After two consecutive no-progress cycles, mark the path `STALLED`.
- Separate facts, assumptions, and the current hypothesis, then run the cheapest falsifying
  experiment.
- If it yields no evidence, stop that reasoning chain. Use at most one fresh bounded
  diagnosis with the compact fact packet, or report the blocker.
- Stagnation must not increase reasoning effort or worker fan-out.

## Portable

Materialize only after the plan is actionable and a real durability trigger exists:

```bash
python3 <skill-dir>/scripts/harnessctl.py materialize <project-root> \
  --title "<title>" --goal "<outcome>" \
  --done-when "<observable criterion>" \
  --constraint "<hard constraint>" \
  --next-action "<one literal action>"
```

Checkpoint only at verified boundaries. Use `handoff` for a clean transfer, `resume` to
validate drift and claim ownership, and `close` at a terminal boundary. The contract is the
source of truth; the bounded capsule is generated resume context.

## Audited

Apply controls only at the protected transition or claim:

- state/UI/async/concurrency behavior: Production State Witness tied to the real call chain;
- behavior with meaningful tests: real RED/GREEN chronology, otherwise a concrete substitute;
- protected acceptance: typed evidence receipts and manager re-verification;
- multiple writers or takeover: owner-epoch fencing and drift checks;
- high-impact external action: stop for the required user approval.

New Audited artifacts record `mode: audited`. Existing `mode: full` artifacts remain
readable and resumable through `handoff-v1`; do not rewrite them only to rename the mode.

## Workers And Model Routing

Delegation is independent of mode. Use workers for disjoint, bounded ownership only when the
benefit exceeds coordination cost. The main agent owns goal, merge, and acceptance. Give a
worker its scope, output contract, verification, and stop rule.

When runtime-local model routing is available, a capable parent may plan and judge while a
cheaper worker executes a long, mechanical, verifiable slice. This is optional, not the
default response to "你是主 agent". Review only a concrete candidate against one acceptance
question. Retry only after a diagnosed failure changes the task or evidence; never run an
open-ended planner-worker-judge loop. Record requested and resolved models separately.

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

*Agent Reliability Harness v9.2.0 | 2026-08-11*
