# Agent Reliability Harness

[简体中文](README.zh-CN.md) | English

Agent Reliability Harness is a Plan-native skill for reliable execution across Codex,
Claude Code, Grok, and other file-and-shell capable agents. It uses the runtime's own Plan
for ordinary work, materializes a compact provider-neutral contract only when work must
survive a boundary, and adds audit controls only when risk requires them.

Current version: **v9.1.0** · 2026-08-02

---

## Overview

Modern agents already plan, track tasks, use tools, and manage workers. Repeating those
capabilities in a second prompt-level state machine wastes context and creates competing
sources of truth. This skill adds only what a runtime cannot reliably carry across a
session or model boundary.

The manager remains responsible for:

- selecting Native, Portable, or Audited mode
- defining the outcome, constraints, approval boundaries, and observable `done_when`
- materializing only facts that are expensive or unsafe to reconstruct
- assigning bounded work only when ownership is disjoint
- stopping reasoning loops that produce no observable progress
- verifying acceptance evidence before claiming completion

Sub-agents are used only for bounded execution, investigation, review, or evaluation tasks. They do not replace the manager's responsibility for final acceptance.

---

## Core Capabilities

- **Plan-native routing:** reuse the runtime Plan instead of generating a second checklist.
- **Portable Contract v2:** preserve only objective, decisions, milestones, blockers, next
  action, workspace fingerprint, evidence digests, capabilities, and tiered reads.
- **Bounded resume context:** regenerate `capsule.md` under a deterministic character budget.
- **Fail-closed continuation:** detect corruption, drift, stale ownership, multiple active
  runs, and Portable/legacy ambiguity before mutation.
- **Audited extensions:** retain typed receipts, Production State Witness, protected TDD
  chronology, evaluator separation, and stronger fencing for high-risk work.
- **Legacy compatibility:** continue to validate and resume `handoff-v1` Full artifacts.
- **Adapter-local routing:** keep provider and model slugs outside the portable core.
- **Progress Circuit Breaker:** require new evidence, an artifact change, a test result, or a
  binding decision; stop after two no-progress cycles without a new diagnosis.
- **Clean packaging:** exclude repository docs, generated `.harness/` and `workspace/`
  artifacts, caches, sessions, and private configuration.

---

## Execution Modes

| Mode | Use When | Durable State |
| --- | --- | --- |
| **Native** | The active session can finish and verify without costly reconstruction. | None; use the runtime Plan and task tracking. |
| **Portable** | Work may cross sessions/models, wait externally, or use workers whose results must survive context loss. | `.harness/<slug>/contract.json`, `events.jsonl`, `capsule.md` |
| **Audited** | Production, release, permissions, security, destructive changes, disputed ownership, or high fake-success risk needs stronger proof. | Portable state plus justified evidence and review extensions; legacy Full remains supported. |

Parallelism is independent of mode. A large sequential task can remain Native; a small
handoff can be Portable; a high-risk one-file change can be Audited.

---

## When To Use

Use this skill when the request involves:

- saying "You are the main agent" or "write a harness" to activate the density router
- writing a harness to solve this problem
- durable handoff or cross-model continuation
- resumable execution or a long external wait
- multi-agent, sub-agent, parallel, DAG, or worktree coordination
- 分头处理 / 分别派 / 拆给不同 agent
- evidence-based acceptance or a high fake-success risk

The trigger selects the skill, not the heaviest mode. Ordinary work should still remain
Native, and workers should be used only when parallel ownership is real.

---

## Operating Flow

```text
Native Plan
-> define outcome / constraints / done_when / approval boundary
-> choose Native / Portable / Audited
-> execute, optionally with bounded workers
-> stop or re-diagnose after two no-progress cycles
-> verify against observable evidence
-> checkpoint or hand off only at a durable boundary
```

The manager should choose the lightest mode that preserves safe execution and honest
completion. Do not mirror a native Plan into JSON or Markdown.

## Progress And Codex Routing

Progress means new evidence, an artifact change, a test result, or a binding decision. Once
a reversible action can distinguish the current hypotheses, execute it instead of extending
the plan. After two no-progress cycles, record facts, assumptions, the current hypothesis,
and one falsifying experiment. If it yields no evidence, stop that reasoning chain.

When explicit Codex routing is available, the configured policy keeps the parent on Sol
`max` for planning and acceptance, and uses Luna `max` for justified long implementation,
integration, and mechanically verifiable execution. Sol workers remain bounded to one
planning, fresh-diagnosis, or concrete high-risk review question. Stagnation never raises
reasoning effort automatically. New runs record
`progress-bounded-v2`; legacy `cost-aware-v1` Audited runs keep their sealed v1 profile map
so resume validation does not reinterpret historical dispatches.

---

## Portable And Audited Protocol

Portable v2 is the default durable protocol. Audited controls are extensions, not a second
mandatory workflow.

### 1. Materialize A Contract

Materialize only after the native Plan is actionable and a durability trigger exists:

```bash
python3 <skill-dir>/scripts/harnessctl.py materialize . \
  --title "Checkout refactor" \
  --goal "Complete the checkout refactor without changing public behavior" \
  --done-when "Focused and regression tests pass" \
  --constraint "Preserve unrelated changes" \
  --next-action "Inspect the checkout state boundary"
```

This creates exactly three core files under `.harness/<slug>/`:

- `contract.json`: the only mutable source of truth
- `events.jsonl`: append-only transition and evidence index
- `capsule.md`: bounded, regenerated context for the receiving model

### 2. Checkpoint Verified Boundaries

Checkpoint after a meaningful verified result or before a likely interruption, not after
every tool call. Evidence remains in the project; the contract stores only a relative path,
SHA-256 digest, and size.

```bash
python3 <skill-dir>/scripts/harnessctl.py checkpoint . \
  --runtime codex --actor-id codex-main --owner-epoch 1 \
  --completed "Focused regression passes" \
  --next-action "Run the package verification" \
  --evidence-file reports/focused-test.txt \
  --reason "Verified implementation boundary"
```

The first checkpoint claims epoch 1 and omits `--owner-epoch`.

### 3. Handoff And Resume

Use `handoff` for a clean transfer. The replacement runtime starts from the project root:

```bash
python3 <skill-dir>/scripts/harnessctl.py resume . \
  --runtime claude --actor-id claude-main
```

`resume` validates the contract, rejects ambiguous active Portable/Full state, checks
workspace drift, transfers ownership, regenerates the capsule, and returns `must_read`,
`read_if_needed`, blockers, pending verification, and one safe next action. An abrupt active
owner takeover additionally requires `--takeover-reason`.

At a terminal boundary, run `close --status accepted|failed|cancelled`. Accepted closure
requires evidence and no unresolved blocker or pending verification; closed contracts no
longer participate in active-run selection.

### 4. Portable Data Boundary

Persist observable facts only: goal, `done_when`, constraints, completed milestones,
blockers, decisions with short rationale, changed paths, evidence digests, capabilities,
and tiered reads. Do not persist hidden reasoning, full chats, provider session objects,
secrets, or in-flight external side effects.

### 5. Audited Escalation

Add only the control required by the risk:

- typed acceptance receipts and manager re-verification
- Production State Witness for UI/state/async/concurrency paths
- protected RED/GREEN chronology for behavior changes
- evaluator separation, stronger rollback, and detailed trace
- owner epoch fencing for disputed or concurrent writers

Audited does not imply parallel workers. Worker use remains an independent cost/ownership
decision.

### 6. Legacy Full Compatibility

Existing `handoff-v1` artifacts under `workspace/<slug>/` remain valid. The same
`checkpoint`, `handoff`, `resume`, and `validate` commands continue to support them. Do not
rewrite a valid legacy artifact only to change its format.

### 7. Acceptance Boundary

Worker self-report and harness scores are not completion evidence. The manager must re-run
or inspect critical checks. For user-visible failures, policy-only unit tests cannot replace
flow or visible evidence when those tiers are available.

---

## Installation

Clone the repository:

```bash
git clone https://github.com/SUNRNEHUI/agent-reliability-harness.git
cd agent-reliability-harness
```

Create a clean runtime package:

```bash
python3 scripts/sync_version.py
python3 scripts/package_skill.py --verify-source
python3 scripts/package_skill.py --output /tmp/agent-reliability-harness-runtime --force
```

Install the runtime package into Codex:

```bash
mkdir -p ~/.codex/skills/agent-reliability-harness
rsync -a --delete --exclude workspace --exclude .harness \
  /tmp/agent-reliability-harness-runtime/ ~/.codex/skills/agent-reliability-harness/
python3 scripts/package_skill.py --check ~/.codex/skills/agent-reliability-harness
```

The runtime package contains only the files needed by the skill at execution time.

Recommended Codex defaults for this routing policy:

```toml
model = "gpt-5.6-sol"
model_reasoning_effort = "max"
service_tier = "fast"

[agents]
default_subagent_model = "gpt-5.6-luna"
default_subagent_reasoning_effort = "max"
```

This configuration is optional and remains user-owned. Do not copy a private model cache
or set `model_catalog_json` as part of skill installation. If Luna is unavailable, retain
the requested route in evidence, record the runtime-resolved fallback separately, and do
not claim that a Luna worker ran.

---

## Migration From Earlier Names

Earlier releases used Agent Dispatch Harness as the public project and runtime name; older releases used `multi-agent-dispatcher` and some local installs used `multi-agent-orchestrator`. New installs should use `agent-reliability-harness`.

When upgrading an existing local install, install the new runtime directory first, then remove old local runtime folders if they are still present and no longer needed:

```bash
rm -rf ~/.codex/skills/agent-dispatch-harness ~/.codex/skills/multi-agent-dispatcher ~/.codex/skills/multi-agent-orchestrator
```

This avoids duplicate skill entries that describe the same workflow.

---

## Runtime Package Contents

The runtime package includes:

- `VERSION`
- `SKILL.md`
- `master-prompt.md`
- `sub-prompt.md`
- `agents/openai.yaml`
- `adapters/`
- `references/`
  - `references/portable-contract.md`
  - `references/harness-protocol.md`
  - `references/state-memory-boundary.md`
  - `references/model-routing.md`
- `templates/`
- `scripts/harnessctl.py`
- `scripts/init_run.py`
- `scripts/harness_test_run.py`
- `scripts/protocol_regression_harness.py`
- `scripts/runtime_profiles.py`
- `scripts/status.py`
- `scripts/tdd_gate_check.py`
- `scripts/validate_report.py`
- `templates/lite_plan.md`
- `templates/lite_review.md`
- `templates/tdd_trace.jsonl`

The authoritative file list is `scripts/package_skill.py:RUNTIME_FILES`; this section summarizes the runtime categories.

It intentionally excludes:

- `README.md`
- `README.zh-CN.md`
- `scripts/sync_version.py`
- `scripts/package_skill.py`
- `.git`
- generated `.harness/` artifacts
- generated workspace artifacts
- local memory files
- session logs
- caches and bytecode
- private configuration
- credentials or API keys

---

## Usage Examples

Explicit multi-agent request:

```text
This project has frontend, backend, and test work. Use multiple agents where useful, and provide verification evidence.
```

Small task with multi-agent wording:

```text
Use multi-agent if needed to fix this typo.
```

Expected behavior: stay Native and do not delegate because dispatch overhead is not justified.

Long task requiring durable coordination:

```text
Refactor checkout, update API contracts, migrate tests, and verify the UI flow. Use sub-agents and keep the work resumable.
```

Expected behavior: materialize Portable state because the work must resume; add Audited
extensions only if the actual risk requires them. Worker use remains a separate decision.

---

## Portable Materialization And Audited Initialization

For new resumable work, materialize Portable v2:

```bash
python3 scripts/harnessctl.py materialize /path/to/project \
  --title "Checkout Refactor" \
  --goal "Refactor checkout while preserving behavior" \
  --done-when "Checkout regression suite passes" \
  --next-action "Inspect the production checkout flow"
```

This creates only:

```text
/path/to/project/.harness/checkout-refactor/
├── contract.json
├── events.jsonl
└── capsule.md
```

For Audited controls or legacy Full workflows, initialize the full record set:

```bash
python3 scripts/init_run.py \
  --project-root /path/to/project \
  --mode audited \
  --title "Checkout Refactor" \
  --agents frontend,backend,tests
```

This creates:

```text
/path/to/project/workspace/checkout-refactor/
├── acceptance_registry.json
├── capability_snapshot.md
├── task_spec.md
├── progress.md
├── run_state.json
├── trace.jsonl
├── tdd_trace.jsonl
├── evaluator_report.md
└── tasks/
    ├── 1.1-frontend.md
    ├── 1.2-backend.md
    └── 1.3-tests.md
```

---

## Report Validation

Validate a Portable contract directly:

```bash
python3 scripts/harnessctl.py validate /path/to/project/.harness/checkout-refactor
```

For Audited or legacy artifacts, validate generated reports before relying on them:

```bash
python3 scripts/validate_report.py <artifact-dir>/1.1-frontend-report.md --type subagent
```

Supported artifact types:

- `spec`
- `progress`
- `subagent`
- `evaluator`

When protocol files such as `acceptance_registry.json` or `run_state.json` sit next to a validated artifact, the validator also checks those files.

For TDD-sensitive work, validate the dedicated TDD trace:

```bash
python3 scripts/tdd_gate_check.py <artifact-dir>/tdd_trace.jsonl
```

The checker validates chronology for strict TDD, accepts test-first gap evidence when recorded, and rejects missing substitute reasons.

Use the test wrapper when available so trace events are generated by the runtime command runner rather than hand-written by an agent:

```bash
python3 scripts/harness_test_run.py \
  --trace <artifact-dir>/tdd_trace.jsonl \
  --task-id 1.1 \
  --gate-mode strict_tdd \
  --phase RED \
  --run-state <artifact-dir>/run_state.json \
  -- pytest path/to/test.py
```

For strict TDD cycles, `tdd_gate_check.py --source-path <file>` can add filesystem mtime checks for the files changed in that cycle.

For CI or release gates, require the run to reach high completion confidence:

```bash
python3 scripts/status.py <artifact-dir>/run_state.json --require-high-confidence
```

---

## Repository Layout

```text
agent-reliability-harness/
├── SKILL.md
├── README.md
├── README.zh-CN.md
├── adapters/
├── agents/
├── references/
├── scripts/
├── templates/
├── master-prompt.md
└── sub-prompt.md
```

Detailed protocol material lives in `references/`. Runtime-specific guidance lives in `adapters/`.

---

## Runtime Adapters

The protocol is runtime-neutral. Adapters describe how to apply it in specific agent environments:

- [Codex adapter](adapters/codex.md)
- [Grok adapter](adapters/grok.md)
- [Claude Code adapter](adapters/claude-code.md)
- [Portable Contract v2](references/portable-contract.md)
- [Audited and legacy protocol](references/harness-protocol.md)

Adapters map native planning, worker controls, and optional model profiles to each runtime.
They must not add provider-specific fields to the Portable contract.

---

## Relationship To Superpowers

This project is independent and does not require Superpowers to run.

The design is influenced by [obra/superpowers](https://github.com/obra/superpowers), a software development methodology by Jesse Vincent. Agent Reliability Harness adopts compatible engineering patterns such as test-first evidence, fresh-context sub-agents, review gates, worktree isolation, and verification before completion.

The project does not copy Superpowers skill bodies and does not require the Superpowers plugin. The relationship is:

```text
agent-reliability-harness = durability and acceptance authority
Superpowers-style methods = optional supporting engineering practices
```

Native / Portable / Audited selection runs first. Supporting methods are applied only when
they fit the selected mode and measured risk.

---

## Release History

### v9.1.0

- Aligned Codex planning and acceptance with Sol `max`, while keeping justified execution
  routes on Luna `max`.
- Documented the optional Codex parent/sub-agent configuration and kept private model-cache
  overrides outside the distributed skill.
- Clarified that routed profiles do not replace the active parent session and that requested
  versus resolved models must be recorded separately.

### v9.0.0

- Added an observable Progress Circuit Breaker that stops after two no-progress cycles and
  requires a fresh diagnosis before rerouting.
- Routed long-running and mechanical Codex execution to Luna `max`; limited Sol to bounded
  diagnosis, planning, and concrete acceptance review.
- Versioned the new route as `progress-bounded-v2` while preserving sealed validation for
  legacy `cost-aware-v1` Audited runs.
- Removed domain-specific effect-reconstruction policy from the generic skill entry and
  reduced duplicate planning, reporting, and review instructions.

### v8.0.0

- Replaced the prompt-level Direct/Lite/Full router with Plan-native Native, Portable, and
  Audited modes.
- Added Portable Contract v2 with a three-file core, bounded resume capsule, tiered reads,
  evidence digests, workspace drift checks, cross-runtime owner transfer, and terminal close.
- Kept `handoff-v1` Full compatibility while moving provider/model maps outside the
  portable schema and retaining heavy evidence controls only for Audited work.

### v7.5.0

- Added typed evidence hardening, artifact binding, lessons integrity, protected TDD
  chronology, and adversarial protocol regression coverage for Full runs.

### v7.4.0

- Added unique-active-run discovery, transaction recovery, atomic cross-runtime ownership transfer, complete resume packets, explicit checkpoint/handoff commands, and legacy Full artifact upgrade.
- Added actor-plus-epoch fencing, fail-closed ambiguity/corruption handling, repository content drift detection, and continuation status output.
- Brought the existing v7.3 Grok model routing and evidence refresh commands back into source, then aligned Codex/Grok/universal adapters and package contents.

### v7.3.0

- Added sealed Grok model profiles, deterministic `--runtime grok` routing, a Grok adapter, and opt-in cheaper-model configuration without inventing unavailable defaults.
- Added `task-refresh` and `acceptance-refresh` for transactionally replacing stale artifact receipts by path.

### v7.2.0

- Added a Production State Witness contract for state/UI/async/concurrency work, including source locators, reachable truth-table rows, observed-before/expected-after values, and preserved blocking cases.
- Enforced the witness at runtime: invalid stateful artifacts cannot seal, dispatch, validate, or reach protected acceptance; independent review evidence must meet the configured policy/flow/user-visible tier.
- Added `witness-set`, sealed witness digests, sealed-baseline dispatch checks, adversarial pressure tests, and source/install package drift checks.

### v7.0.0

- Rebranded the project and runtime skill as Agent Reliability Harness.
- Reworked the public README and runtime metadata around policy-driven, proportional, evidence-based execution.

### v5.11.0

- Compared the harness with `Cjbuilds/Codex-Orchestration` and documented which thin-routing ideas are adopted and which high-overhead bridges and ceremony are explicitly excluded.
- Kept the active parent model as the only root orchestrator, made explicit `no subagents` instructions authoritative, and tightened truthful model-route states.
- Added `scripts/status.py --require-high-confidence` for CI or release gates while preserving the default compact human-readable status output.
- Reduced default alignment questioning to irreversible or acceptance-relevant decisions; ordinary ambiguity now uses a stated reversible assumption.

### v5.10.0

- Added GPT-5.6-aware Codex routing: Luna/low for simple sub-agents, Terra for moderate work, and Sol for critical review when explicit runtime controls are available.
- Added bounded worker budgets, shallow nesting, task-local context, compact reports, and model-override fallback rules.
- Made Superpowers-style methods risk-triggered and optional instead of a default ceremony bundle.
- Added model-routing guidance, regression cases, and runtime packaging coverage without adding GPT-5.6-specific API fields.

### v5.9.0

- Added a proportional Completion Confidence Loop to check final claims against fresh evidence before handoff.
- Expanded Verification and Evaluator guidance to expose missing checks, stale evidence, stubs, TODOs, mocks, and unverified critical paths.
- Enhanced `scripts/status.py` with task completion, acceptance rollup, evidence-gap detection, confidence bands, and next-verification guidance.
- Added lightweight confidence and evidence-gap prompts to the progress ledger and Lite plan templates.
- Preserved right-sized execution: Direct remains artifact-free, Lite remains compact, and Full remains the durable protocol for high-risk or resumable work.
- Added no new artifact type.

### v5.8.0

- Added `VERSION` plus `scripts/sync_version.py` so current-version references can be checked or updated from one source.
- Added runtime package checks with `scripts/package_skill.py --verify-source` and `--check <install-dir>`.
- Added Lite Orchestration artifacts through `templates/lite_plan.md`, `templates/lite_review.md`, and `init_run.py --mode lite`.
- Kept `progress.md` lightweight and added `scripts/status.py` for a generated single-screen summary from `run_state.json`.
- Added validator support for `lite_plan`, `lite_review`, and Lite `run_state.json`, plus runtime behavior tests.
- Kept automated mode-router evaluation out of this release; `references/eval_cases.md` remains the human-readable regression set.

### v5.7.0

- Added an explicit State and Memory boundary for Full Harness runs.
- Clarified that `task_spec.md` is the local human-readable plan/spec, while `run_state.json` is the machine-readable live state.
- Added `state_layers` for Working State, Session State, Execution Log, and Memory Boundary.
- Added `references/state-memory-boundary.md` and included it in runtime packaging.
- Updated validation to require the core `state_layers` structure in `run_state.json`.

### v5.6.0

- Renamed the public project and runtime skill from Multi-Agent Dispatcher to Agent Dispatch Harness.
- Updated repository URLs, install paths, runtime metadata, and bilingual documentation for the new name.
- Renamed the TDD command wrapper to `scripts/harness_test_run.py` and updated trace `source` values.
- Added migration guidance for older `multi-agent-dispatcher` and `multi-agent-orchestrator` local installs.
- Preserved the Direct, Lite, and Full mode model, with Full Harness remaining the durable advanced execution protocol.

### v5.5.0

- Added wrapper-generated TDD trace support for verification commands, now exposed as `scripts/harness_test_run.py`.
- Extended `scripts/tdd_gate_check.py` with optional `--source-path` mtime checks for strict TDD cycles.
- Added `tdd_current_cycle_context` to run-state templates and initialization output.
- Clarified that normal workers should prefer wrapper-generated trace evidence over hand-written TDD traces.
- Added retry, checkpoint, and rollback guidance to Bugfix and Feature-Spec lanes without allowing automatic `git reset --hard` in the main worktree.

### v5.4.0

- Added Bugfix Lane and Feature-Spec Lane references for task-type-specific development flow.
- Added `templates/tdd_trace.jsonl` and `scripts/tdd_gate_check.py` for runtime-neutral TDD chronology validation.
- Updated run initialization and runtime packaging so TDD trace artifacts and checker scripts are included.
- Tightened sub-agent and evaluator templates to require trace path, chronology summary, first production edit, and unverified critical path fields.
- Expanded evaluation cases for code-before-RED, passing-test-as-RED, shell-bypass, UI-only-unit-test, self-report-only, and missing no-test-reason failures.
- Added `.gitignore` protection for generated workspaces, worktrees, and Python cache files.

### v5.3.0

- Added a two-level testing model: `Test-First Evidence Gate` and `Strict TDD Gate`.
- Added `references/tdd-gates.md` for RED/GREEN, substitute verification, and manager acceptance rules.
- Added required `Test-First Or Substitute Verification` fields to sub-agent reports.
- Extended protocol JSON records with `verification_gate`.
- Updated validation so sub-agent reports and protocol records cannot omit the testing gate structure.

### v5.2.2

- Rewrote the English and Chinese README files in a formal public documentation style.
- Clarified the project positioning, execution modes, installation flow, runtime package boundary, and Superpowers acknowledgement.
- No runtime protocol changes.

### v5.2.1

- Added bilingual public documentation.
- Added an explicit acknowledgement of Superpowers-inspired engineering patterns.
- Added `scripts/package_skill.py` for clean runtime-only packaging.
- Consolidated Direct, Lite, and Full routing guidance in the public README.
- Expanded evaluation coverage for TDD evidence, review separation, Superpowers interaction, and clean sharing.

### v5.0.1

- Added a right-sizing gate before capability checks and DAG creation.
- Clarified that explicit multi-agent wording authorizes evaluation, not automatic dispatch.
- Added guidance to skip workers, worktrees, and artifacts for small tasks.

### v5.0.0

- Upgraded the project from protocol guidance into a manager-enforced harness protocol.
- Added capability snapshots, `run_state.json`, `acceptance_registry.json`, and `trace.jsonl`.
- Added evaluator validation and runtime adapters for Codex and Claude Code-style environments.

### v4.0.0

- Introduced the closed-loop multi-agent protocol.
- Added artifact initialization, report validation, role boundaries, stop conditions, and evaluator templates.

---

## License

No license file is currently included in this repository.
