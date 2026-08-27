---
name: agent-harness
description: >
  Use when user says “你是主 agent”, “写一个 harness” / “write a harness”, multi-agent
  delegation, parallel workers, durable handoff, cross-model continuation, resumable execution,
  or protected evidence-based acceptance. Explicit requests compile intent before choosing Native,
  Portable, or Audited; ordinary implementation, planning, and testing do not trigger this skill.
---

# Agent Harness

Add only controls missing from the runtime. “写一个 harness” first turns user intent into a
reviewable contract; it does not itself create `.harness` artifacts, select Audited, or dispatch a
worker.

## Intent-to-Contract Gate

For an explicit harness request, read `references/spec-synthesis.md` and run its synthesis
protocol before the Mode Gate or any dispatch, even with a measurable plan.
Produce a user-reviewable alignment packet and contract; for non-implementation work, return them
and stop. The contract names:

- user-facing and system outcomes, observable `done_when`, and explicit `success_not`;
- allowed scope, ownership, non-goals, compatibility, constraints, relevant edge/failure
  handling, and approval boundaries;
- evidence plus a decidable pass algorithm for every acceptance criterion;
- `fact`, `assumption`, `recommended_default`, and `open_decision` labels.

Use `recommended_default` only for low-risk, reversible gaps. A material choice, conflict, missing
owner/capability, public-contract change, security/privacy issue, cost, irreversible behavior, or
approval need is an `open_decision`: expose it and do not dispatch. The packet precedes the first
worker and includes false-success signals, phase map, and the first narrow task.

## Dispatch Readiness

Dispatch only after outcome, system completion, `done_when`, `success_not`, scope, ownership,
non-goals, constraints, edge/failure handling, approvals, evidence/pass algorithms, and
defaults are explicit with no material open decision. The first task needs one responsibility,
dependencies, bounded inputs/outputs, allowed scope, execution guidance, verification gate,
decidable PASS, and Stop rule. Write one runtime plan; track worker status and evidence.

## Workflow Composition

For code changes, use the repository's established coding workflow or an available matching coding
skill. This skill does not replace, copy, or weaken it; do not require a particular companion skill
by name.

## Mode Gate

Choose once after synthesis:

| Mode | Use when | Durable state |
| --- | --- | --- |
| **Native** | Session can implement and verify the slice. | None; use the runtime Plan |
| **Portable** | Work crosses a session/model boundary, external wait, or context loss. | `.harness/<slug>/contract.json`, `events.jsonl`, `capsule.md` |
| **Audited** | Protected/disputed transition needs typed proof. | Only justified witness, receipts, fencing, trace, and registry controls |

Mode controls persistence and evidence depth; synthesis is orthogonal. If Native fits, do not load references, create
harness files, or add audit controls solely because this skill triggered.

## Execution Shape

Delegation is independent of mode. V3 micro work may stay on the parent/main route only after
explicit `scope-local`, `low-risk/no-protected-boundary`, `context-complete`,
`short-verification`, and `delegation-cost-higher` confirmations. Explicit user delegation
overrides the micro direct route. Ordinary or execution-heavy work uses one bounded worker;
complex work uses parallel workers only at independent modules or ownership boundaries; coupled
writes stay serial or with one owner. Try another verifiable bounded worker first; if none
exists or resolution fails, block. Parent direct fallback requires explicit user authorization.
Workers do not redefine the contract; they do not recursively delegate. Keep
requested and resolved models separate; only runtime evidence establishes the route.

The main agent owns goal, contract, plan, dispatch, status, integration, and acceptance. Each worker
gets a self-contained packet with constraints, edge cases, evidence requirements, PASS, and Stop; it
returns actual changed paths, verification output and exit status, unverified paths, assumptions, and
blockers. A worker report or PASS never establishes completion; the parent inspects actual diff and
decisive evidence.

## Progress Circuit Breaker

Progress is new evidence, an artifact change, a test result, or a binding decision advancing a named
`done_when` criterion or named critical-path blocker. Generated metadata, reports, package rebuilds
are activity that does not count as progress. After two consecutive no-progress
cycles, run the cheapest falsifying experiment; if it yields no evidence, stop and report `STALLED`.
This policy must not increase reasoning effort because work stalled.

## Durable And Audited Work

Materialize Portable state only after an actionable plan and durability trigger; read
`references/portable-contract.md` before materialize, handoff, resume, or close. Preserve
legacy `handoff-v1`/Full reads and resumability. For Audited work, read
`references/harness-protocol.md` and one control reference; add only justified protected
controls. Persist observable facts, never hidden reasoning, chats, secrets, or provider
sessions.

## Load On Demand

Use `references/proportionality.md` for mode/stall decisions, `references/public-contracts.md`
for public JSON/CLI contracts, `references/state-witness.md` for stateful behavior,
`references/tdd-gates.md` for protected chronology, `references/stop-conditions.md` for
detailed stops, and `references/model-routing.md` plus the adapter for optional routing.

---

*Agent Harness v10.0.0 | 2026-08-27*
