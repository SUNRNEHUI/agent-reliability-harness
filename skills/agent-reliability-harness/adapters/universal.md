# Universal Runtime Adapter

Use this floor for any model that can read project files. Shell, browser, native Plan,
subagents, and per-worker model selection are optional capabilities.

## Native First

Use the runtime's own planning and task tracking while one active session can finish and
verify the work. Do not serialize a second plan merely because the runtime has a plan UI.

Materialize Portable state only when work must survive a session/model boundary, a long
wait, or multiple workers. Escalate to Audited controls only when consequences or
fake-completion risk justify them.

## Capability Negotiation

Portable contracts name required and optional capabilities, not providers or models.

- Missing optional capability: choose a documented sequential or manual fallback.
- Missing required capability: stop with the exact capability gap.
- No native subagents: execute bounded stages sequentially; never label them parallel.
- No shell: the agent may read the capsule, but must not claim script validation or owner
  mutation occurred.

Runtime identity comes from the active launcher or verified capabilities. An installed
executable does not prove it owns the session.

## Portable Continuation

The replacement runtime runs `harnessctl.py resume` from the project root. It reads the
returned capsule, reconciles workspace drift, satisfies `must_read`, and loads
`read_if_needed` only for a concrete gap. Every writer uses the current owner epoch.

The contract transfers observable state. It cannot transfer hidden reasoning, provider
session state, secrets, or an in-flight external side effect.

## Workers

Delegate only independent responsibility surfaces. Prompts include goal, allowed scope,
constraints, outputs, evidence, and stop rules. Workers return
`templates/worker_result.json`. The manager owns merge and final acceptance.

## Stable Core

Always preserve:

- outcome and observable `done_when`;
- constraints and approval boundaries;
- one literal next action;
- evidence paths and digests;
- workspace drift and owner fencing;
- explicit blockers and stop conditions.

Load provider adapters only when a provider-specific capability changes execution.
