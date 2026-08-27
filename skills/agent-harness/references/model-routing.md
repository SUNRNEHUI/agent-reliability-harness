# Progress-Bounded Model Routing

Select Native, Portable, or Audited for persistence and evidence depth first. Delegation is independent of mode;
a mode choice must not turn a small implementation into a larger workflow. Model routing remains an optional
runtime-local execution choice.

## Codex Default Policy

New runs use routing policy `progress-bounded-v3`. This repository intentionally does not
route through Terra. The configured GPT-5.6 profiles are:

| Profile | Model | Reasoning | Use |
|---|---|---|---|
| `fast` | `gpt-5.6-luna` | `max` | One bounded child execution task for ordinary or execution-heavy implementation |
| `main` | `gpt-5.6-sol` | `high` | Parent manager, including a qualifying micro implementation done directly |
| `planner` | `gpt-5.6-sol` | `high` | One bounded parent planning or fresh-diagnosis question |
| `critical_reviewer` | `gpt-5.6-sol` | `high` | One concrete parent acceptance review or worker-conflict decision |

Run the deterministic selector when the route is not obvious:

```bash
python3 <skill-dir>/scripts/model_router.py --runtime codex --simple --mechanically-verifiable
python3 <skill-dir>/scripts/model_router.py --runtime codex --micro-implementation \
  --micro-scope-local --micro-low-risk --micro-no-protected-boundary \
  --micro-context-complete --micro-short-verification \
  --micro-delegation-cost-higher
python3 <skill-dir>/scripts/model_router.py --runtime codex --implementation
python3 <skill-dir>/scripts/model_router.py --runtime codex --harness-synthesis
python3 <skill-dir>/scripts/model_router.py --runtime codex
```

The parent/main Agent uses Sol `high`; the child execution Agent uses Luna `max`. The `main`
profile names the parent manager route and the direct lane for a qualifying micro implementation,
not a child implementation lane. A micro implementation must be local, low-risk, context-complete,
provable in one short verification cycle, and more expensive to delegate than to execute. Use
`--micro-implementation` only with explicit confirmations for `scope-local`, `low-risk`,
`no-protected-boundary`, `context-complete`, `short-verification`, and `delegation-cost-higher`.
These confirmations are auditable routing assertions, not automatic proof of the facts; the
parent remains responsible for checking their truth. Use `--implementation` for ordinary or
execution-heavy implementation and dispatch one bounded worker. A user's explicit delegation
request selects the worker lane even when the change looks small. A complex task may use parallel
workers only for independent modules; tightly coupled writes stay serial or have one owner. Child
workers are leaves and do not recursively delegate.

`--simple --mechanically-verifiable` remains a separate bounded mechanical route. It does not
classify an implementation as micro, and it must not be used as a synonym for
`--micro-implementation`. The selector rejects missing micro confirmations, protected/public
contract/migration boundaries, mixed direct/worker or micro/mechanical flags instead of guessing
which intent wins. The micro-direct route exists only in current `progress-bounded-v3`; passing
it with sealed `progress-bounded-v2` or legacy `cost-aware-v1` is rejected rather than
reinterpreting a historical profile map.

The prior `progress-bounded-v2` Codex map is sealed for existing runs: `main` remains Luna
`max`, while `planner` and `critical_reviewer` remain Sol `max`. A v2 run is not silently
reinterpreted with the v3 parent/worker map; changing it requires an explicit migration.
To inspect or resume that route, pass `--routing-policy progress-bounded-v2` to
`model_router.py`; dispatch validation reads the same policy from `run_state.json`.

These are workload choices, not a claim that maximum reasoning is always optimal. Measure
success, time to first action, no-progress cycles, latency, and token use against a
lower-effort baseline.

When the local Codex installation exposes the custom agent type `luna_worker`, use that
named agent for a justified Luna execution route. Give it a self-contained
`fork_turns=none` task. The distributed skill does not install or require this personal
agent configuration; absence tries another verifiable bounded worker. If no such worker is
available, implementation is blocked; direct parent execution requires explicit user
authorization. Verify the resolved agent type and model before claiming that Luna executed the
task. If the worker or requested model is unavailable, malformed, or cannot be resolved by the
runtime, record the unresolved route and never claim that the child or model ran.

Existing runs that record `cost-aware-v1` or `progress-bounded-v2` remain resumable and are
checked against the profile map sealed when they were created. New routes emit v3; changing an
old run to v3 requires an explicit migration rather than silently reinterpreting its dispatch
history.

## Bounded Sol Bursts

Sol must receive one question, one output contract, and one stop condition. Use it to settle
an ambiguity or review a concrete candidate, not to run an open-ended implementation loop.
Do not ask it to explore exhaustively, keep thinking, or improve a plan after a reversible
falsifying action is available.

A stalled path is not a reason to increase effort. Two validation failures or two
no-progress cycles block routing until the manager records a new diagnosis:

```bash
python3 <skill-dir>/scripts/model_router.py --runtime codex --no-progress-cycles 2
# ERROR: stalled execution requires a new diagnosis before routing

python3 <skill-dir>/scripts/model_router.py --runtime codex \
  --no-progress-cycles 2 --new-diagnosis
```

The second command selects `planner` / Sol `high` for exactly one fresh diagnosis. Pass
only facts, assumptions, the invalidated hypothesis, new evidence, and the cheapest next
falsifying experiment. Do not pass the full transcript.

## Grok Policy

Grok uses the same portable profiles with a **local slug** map (see `adapters/grok.md`).

**Default when only 4.5 is configured:** every profile (including sub-agents) uses
`grok-api`. Effort still varies by profile.

| Profile | Model slug | Reasoning | Use |
|---|---|---|---|
| `fast` | `grok-api` | `low` | Simple, mechanically verifiable work |
| `main` | `grok-api` | `high` | High-frequency manager, implementation, integration |
| `planner` | `grok-api` | `high` | Fuzzy intent, architecture, Spec Synthesis, harness design |
| `critical_reviewer` | `grok-api` | `xhigh` | High risk, repeated validation failure, worker conflict |

```bash
python3 <skill-dir>/scripts/model_router.py --runtime grok --simple --mechanically-verifiable
python3 <skill-dir>/scripts/model_router.py --runtime grok --implementation
python3 <skill-dir>/scripts/model_router.py --runtime grok --harness-synthesis
python3 <skill-dir>/scripts/model_router.py --runtime grok --high-risk
```

A cheaper second model is **opt-in only** (env override / extra config example
`references/examples/grok-fast-model-config.toml`). Do not seal `grok-fast` as the default
when the install only has 4.5.

## Selection Rules

Apply these in order:

1. Two validation failures or two no-progress cycles without a new diagnosis → stop routing.
2. A recorded fresh diagnosis after a stall → `planner` for one bounded Sol call.
3. High risk or worker conflict with a concrete decision surface → `critical_reviewer`.
4. Fuzzy goal or harness/spec synthesis → `planner` for one bounded output.
5. Explicit `--micro-implementation` plus all six v3 confirmations, with no conflicting
   decision/protected-boundary or mechanical flags → `main` parent direct lane.
6. Explicit `--implementation` (simple or complex) → `fast` child worker.
7. Simple **and** mechanically verifiable non-implementation → `fast` bounded execution.
8. Everything else → `main` parent manager.

Do not treat higher reasoning effort as a recovery mechanism. On Codex, Sol `high` owns the
parent manager and micro-direct paths, while Luna `max` owns bounded child execution. If a worker
is unavailable or cannot be resolved, try another verifiable bounded worker first. Only an explicit
user authorization permits the parent to take over that worker task; record that fallback and keep
requested versus resolved models separate. A completed Sol planning or review burst returns control
to the parent manager; it does not become an open-ended worker loop.
On Grok with only 4.5 available, keep **all** workers on `grok-api` and use profile effort
(and scope) to differentiate work.

## Dispatch And Audit

Model routing does not authorize delegation. First choose the execution shape and the
Native/Portable/Audited persistence and evidence depth. When the shape calls for a real
worker, persist the route:

```bash
python3 <skill-dir>/scripts/harnessctl.py dispatch-create <artifact-dir> \
  --worker-id <runtime-id> --task-id 1.1 \
  --contract-path tasks/1.1-worker.md --report-path 1.1-worker-report.md \
  --runtime codex --profile fast \
  --requested-model gpt-5.6-luna --reasoning-effort max \
  --route-reason "simple mechanically verifiable batch"
```

Grok example:

```bash
python3 <skill-dir>/scripts/harnessctl.py dispatch-create <artifact-dir> \
  --worker-id <runtime-id> --task-id 1.1 \
  --contract-path tasks/1.1-worker.md --report-path 1.1-worker-report.md \
  --runtime grok --profile fast \
  --requested-model grok-api --reasoning-effort low \
  --route-reason "simple mechanically verifiable batch on 4.5"
```

Record the resolved model separately when the runtime exposes it. A requested model is
not proof that the runtime honored the request.

Before routing reviewers, require a concrete candidate and a blocking acceptance question.
Use at most one critical reviewer per surface at a time. Keep an implementation or runtime
verification lane active. Prefer the active runtime's native worker capability map over
creating a user-visible task solely to obtain a model unavailable to ephemeral subagents.

## Cross-Runtime Rule

The profile names and delegation rules are portable; the model mapping is not. Runtime-local maps live in
`scripts/runtime_profiles.py`:

- `codex` → `CODEX_MODEL_PROFILES`
- `grok` → `GROK_MODEL_PROFILES`

Claude Code or another runtime must define its own adapter mapping and availability checks.
If an implementation worker cannot be verified, block implementation; direct parent execution
requires explicit user authorization. For non-implementation work, keep the profile in the
trace and use the runtime's safe fallback rather than claiming a model switch occurred.
