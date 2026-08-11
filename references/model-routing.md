# Progress-Bounded Model Routing

Apply model choice **after** selecting Native, Portable, or Audited mode. Mode decides
durability and control depth; model routing is an optional runtime-local execution choice.
A Native one-line edit stays in the current thread because dispatch can cost more than the
work.

## Codex Default Policy

New runs use routing policy `progress-bounded-v2`. This repository intentionally does not
route through Terra. The configured GPT-5.6 profiles are:

| Profile | Model | Reasoning | Use |
|---|---|---|---|
| `fast` | `gpt-5.6-luna` | `max` | Mechanically verifiable execution and repeated bounded batches |
| `main` | `gpt-5.6-luna` | `max` | Long-running implementation and integration execution |
| `planner` | `gpt-5.6-sol` | `max` | One bounded planning or fresh-diagnosis question |
| `critical_reviewer` | `gpt-5.6-sol` | `max` | One concrete high-risk acceptance review or worker-conflict decision |

Run the deterministic selector when the route is not obvious:

```bash
python3 <skill-dir>/scripts/model_router.py --runtime codex --simple --mechanically-verifiable
python3 <skill-dir>/scripts/model_router.py --runtime codex --harness-synthesis
python3 <skill-dir>/scripts/model_router.py --runtime codex
```

Luna `max` is the configured policy for long implementation and mechanical execution. It is
an explicit workload choice, not a general claim that maximum reasoning is always optimal.
Measure success, time to first action, no-progress cycles, latency, and token use against a
lower-effort baseline.

The Codex parent thread may remain on Sol `max` as the planner and acceptance owner. The
`main` profile names a routed execution lane; it does not replace the parent session default.

When the local Codex installation exposes the custom agent type `luna_worker`, use that
named agent for a justified Luna execution route. Give it a self-contained
`fork_turns=none` task. The distributed skill does not install or require this personal
agent configuration; absence falls back to the active thread or another available worker.
Verify the resolved agent type and model before claiming that Luna executed the task.

Existing Audited runs that record `cost-aware-v1` remain resumable and are checked against
the v1 profile map sealed when they were created. New routes never emit that legacy policy;
changing an old run to v2 requires an explicit migration rather than silently reinterpreting
its dispatch history.

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

The second command selects `planner` / Sol `max` for exactly one fresh diagnosis. Pass
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
5. Simple **and** mechanically verifiable → `fast`.
6. Everything else → `main`.

Do not treat higher reasoning effort as a recovery mechanism. On Codex, Luna `max` owns the
configured long-running and mechanical execution paths. Sol owns bounded judgment and
review only; a completed Sol burst returns control to Luna or the active Native thread.
On Grok with only 4.5 available, keep **all** workers on `grok-api` and use profile effort
(and scope) to differentiate work.

## Dispatch And Audit

Model routing does not authorize delegation. First choose Native, Portable, or Audited.
When an Audited run justifies a real worker, persist the route:

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

The profile names are portable; the model mapping is not. Runtime-local maps live in
`scripts/runtime_profiles.py`:

- `codex` → `CODEX_MODEL_PROFILES`
- `grok` → `GROK_MODEL_PROFILES`

Claude Code or another runtime must define its own adapter mapping and availability checks.
If the active runtime cannot select per-worker models, keep the profile in the trace and
use the runtime's safe fallback rather than claiming a model switch occurred.
