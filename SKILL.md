---
name: agent-reliability-harness
description: >
  Use when the user says "你是主 agent" or "写一个 harness", requests a harness,
  multi-agent delegation, parallel workers, durable handoff, cross-model continuation,
  resumable execution, or protected evidence-based acceptance; also use when high-risk or
  easy-to-fake completion needs controls beyond the repository's normal workflow. Route
  work through progress-bounded Native, Portable, or Audited execution without forcing
  artifacts, subagents, or extended reasoning.
---

# Agent Reliability Harness

Use the runtime's native planning and execution first. The product artifact is the work;
the harness is only a control plane. Add durability and verification only when they reduce
false completion, unsafe continuation, or expensive reconstruction.

## Invariants

1. Define the user-visible outcome, `done_when`, hard constraints, approval boundaries,
   and required evidence before substantial implementation.
2. Prefer external evidence over agent self-report.
3. Persist decisions and observable state, never hidden reasoning or full chat history.
4. Use the lightest mode that makes false completion and unsafe continuation unlikely.
5. Keep provider/model choices in runtime adapters, not portable state.
6. Never treat a plan, report, review, ledger, or harness PASS as user-visible delivery.

## Choose One Mode

| Mode | Choose when | Durable files |
| --- | --- | --- |
| **Native** | Default. The active session can implement and verify the next slice without costly reconstruction. | None. Use the runtime's Plan and task tracking. |
| **Portable** | Work may cross sessions/models, wait on external state, or use workers whose results must survive context loss. | `.harness/<slug>/contract.json`, `events.jsonl`, `capsule.md` |
| **Audited** | Production, release, permissions, security, destructive changes, disputed ownership, or high fake-success risk requires stronger receipts and review. | Portable state plus the existing typed evidence, witness, fencing, and trace controls. |

Parallelism is an execution choice, not a mode. A vague goal needs planning, not
automatically Portable or Audited state.

## Delivery First

Name the smallest executable, user-visible, or testable slice before coordinating:

- Use Native unless a real durability trigger exists.
- Spend at most one coordination pass, and keep an implementation or verification lane active.
- Review a concrete candidate and prefer one decisive result over duplicate narratives.

An `EXPERIMENTAL`, `UNVERIFIED`, or `UNALIGNED` result may guide work, but is not complete.

## Progress Circuit Breaker

Count a cycle as progress only when it produces at least one observable event: **new
evidence**, an **artifact change**, a **test result**, or a **binding decision** that removes
an open branch.

- Plan only the next one to three actions. Once a safe, reversible action can distinguish
  the current hypotheses, execute it instead of refining the plan.
- Do not repeat broad file reads, full test matrices, reviews, or speculative redesigns
  unless the previous result created a new question.
- After two consecutive cycles without a progress event, mark the path `STALLED`.
- On `STALLED`, separate facts, assumptions, and the current hypothesis, then run one
  cheapest falsifying experiment.
- If that experiment yields no new evidence, stop the current reasoning chain. Use one
  fresh, bounded diagnosis with only the compact fact packet, or report the blocker.
- Stagnation must not increase reasoning effort. A higher-effort model is not a substitute
  for a new diagnosis or discriminating evidence.

## Native Workflow

- Use the runtime's Plan mode; do not mirror it into another checklist.
- Stay Native while the session can execute and verify safely. Materialize only when context
  loss would make continuation unsafe or expensive.
- Normal tests and diffs are evidence; add a trace only when chronology is required.

Durability triggers include an expected session/runtime switch, a long external wait,
multiple writers, or important decisions that are expensive to reconstruct.

## Portable Workflow

After the plan is ready and a durability trigger exists, compile only the portable facts:

```bash
python3 <skill-dir>/scripts/harnessctl.py materialize <project-root> \
  --title "<title>" --goal "<outcome>" \
  --done-when "<observable criterion>" \
  --constraint "<hard constraint>" \
  --next-action "<one literal action>"
```

Checkpoint only at verified boundaries:

```bash
python3 <skill-dir>/scripts/harnessctl.py checkpoint <project-root> \
  --runtime <runtime> --actor-id <actor> --owner-epoch <epoch> \
  --completed "<result>" --next-action "<literal action>" \
  --pending-verification "<check>" --reason "<why now>"
```

Use `handoff` for clean transfer. A replacement runs `resume`, validates drift, claims a new
owner epoch, and reads the bounded capsule. Run `close` at terminal boundaries; `accepted`
requires evidence and no blocker or pending verification. The contract is the current
snapshot; the capsule is generated context, not a second truth.

Read `references/portable-contract.md` when creating, resuming, migrating, or debugging a
Portable run.

## Audited Extensions

Escalate only the controls justified by risk:

- State/UI/async/concurrency behavior: require a Production State Witness tied to the real
  production call chain and failing state combination.
- Protected acceptance: use typed evidence receipts and manager re-verification.
- Multiple writers or runtime takeover: retain owner epoch fencing and drift checks.
- Behavior changes with meaningful tests: preserve real RED/GREEN chronology; otherwise
  record the substitute verification and why tests were not viable.
- High-impact actions: stop for confirmation before external writes, publish, destructive
  operations, purchases, permissions, or production data changes.

Apply Audited controls at the risky transition or final claim, not automatically to every
reversible precursor.

Legacy Full artifacts remain readable as `handoff-v1`. Use
`references/harness-protocol.md` only for Audited or legacy runs.

## Workers

Use native subagent orchestration only when ownership is disjoint and parallel work saves
more than coordination costs. At least one lane must advance the executable critical path.
Give each worker a self-contained goal, allowed scope, outputs, verification, progress event,
and stop rules. Use a concise result in Native mode; require a durable report only for
handoff or audit. The manager still owns merge and acceptance.

## Accept And Stop

- Re-run or inspect the critical evidence before claiming completion.
- Re-run the smallest decisive check, not a worker's complete matrix without a concrete
  integration concern.
- UI acceptance needs user-visible or controlled-flow evidence when available; a policy
  unit test alone cannot close a visible symptom.
- Stop on unresolved scope expansion, ownership conflict, missing environment, unsafe side
  effects, budget exhaustion, or two repeated failures without a new diagnosis.
- A high harness score is plan-quality evidence, never product acceptance.

## Load On Demand

| Need | Read |
| --- | --- |
| Mode unclear, execution slow, or reasoning stalled | `references/proportionality.md` |
| Portable schema, capsule, resume | `references/portable-contract.md` |
| Audited state and receipts | `references/harness-protocol.md` |
| Stateful/UI/async behavior | `references/state-witness.md` |
| TDD chronology | `references/tdd-gates.md` |
| Stop and rollback detail | `references/stop-conditions.md` |
| Runtime behavior | one relevant file under `adapters/` |
| Optional model/cost routing | `references/model-routing.md` plus the runtime adapter |

Default to this file only. Load one additional reference when the selected mode or a real
blocker requires it.

At the end, report the selected mode only when it affected execution, plus changed files,
decisive verification, unresolved risk, and the next action. For Portable or Audited work,
point to the capsule/artifact instead of pasting its full state.

---

*Agent Reliability Harness v9.1.0 | 2026-08-02*
