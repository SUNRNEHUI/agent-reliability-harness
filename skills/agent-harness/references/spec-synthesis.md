# Spec Synthesis Protocol

Use this when the user goal is vague, incomplete, or outcome-shaped but not yet executable.
It turns intent into a proportional harness **before** Mode Gate or dispatching implementation
workers.

This is a **manager capability**. Workers execute contracts; they do not invent the program of
record.

## Explicit Harness Entry Gate

When the user explicitly says “写一个 harness”, “write a harness”, or an equivalent direct
request to build a harness, this reference is **必读/必跑**. The manager must read this
protocol and complete its synthesis pipeline before choosing Native/Portable/Audited or
dispatching any worker, even if an existing plan already appears measurable. “Run” means
produce the alignment packet and logical contract; it does not mean creating `.harness` files.

The required order is:

```text
raw intent and facts -> intent-to-contract/spec synthesis -> alignment packet
-> dispatch readiness gate -> Mode Gate -> route/dispatch (if any)
```

Show the packet before the first worker dispatch. If the request is analysis, planning, or
another non-implementation deliverable, return the packet and contract and stop; do not create
a worker just to satisfy the word “harness”.

## When To Run

Run Spec Synthesis when any of these are true:

- The user explicitly requests a harness, as described above.
- The user states a pain, wish, or direction without measurable acceptance.
- Success could be faked by proxy metrics (loading spinners, unit tests only, self-report).
- The work is multi-stage, resumable, improvement-shaped (latency, cost, accuracy), or high regression risk.
- Audited mode is selected and the goal still lacks measurable acceptance.

For a non-explicit request, skip only when the Native or Portable plan already has measurable
acceptance and no contract field below is missing. Never skip the protocol for an explicit
harness request.

## Product Principle

```text
User owns intent and veto.
Manager owns compilation into an executable harness.
Workers own bounded execution inside contracts.
Evaluator/manager owns acceptance from external evidence.
```

## Mode Coupling

Synthesis and persistence mode are orthogonal. An explicit harness request always produces a
logical contract; the Mode Gate only decides whether that contract stays in runtime state or is
materialized with stronger controls.

```text
Native   -> keep the contract in the runtime plan/response; no synthesis artifacts
Portable -> after synthesis, compile the measurable outcome into the three-file contract
Audited  -> add task_spec / registry / tasks / run_state only when protected controls need them
```

Do not create Audited artifacts only to look thorough. A fuzzy goal needs planning; it does
not by itself require durable state or protected controls. Likewise, the explicit trigger does
not force `.harness` files or Audited mode.

## Contract Minimum

The logical contract and alignment packet must cover the following fields. Keep each field
concrete and proportional; do not fill gaps with generic prose.

| Field | Required meaning |
| --- | --- |
| `raw_intent` and known facts | Preserve the user's words and separate observed environment facts from interpretation. |
| `outcome` and `done_when` | State the human-visible result, system terminal condition, and observable completion criteria. |
| `success_not` | Name false-success signals and what explicitly does not count. |
| `scope` / ownership and `non_goals` | Bound paths, modules, actors, outputs, compatibility, and excluded work. |
| `constraints` | Record hard technical, product, time, capability, and authorization constraints. |
| `edge_cases` / `failure_modes` | List only relevant boundaries, expected behavior, evidence, and when to stop. |
| `approval_boundaries` | Identify destructive, external, permission, production, paid, privacy/security, and irreversible actions that require a decision. |
| `evidence` and pass algorithm | Tie every required criterion to raw evidence and a decidable machine or human verification rule. |
| `recommended_defaults` / `open_decisions` | Record low-risk choices that may proceed and material choices that still need an owner decision, with impact. |

Use the four labels consistently:

- `fact`: directly observed or explicitly stated;
- `assumption`: an interpretation not yet confirmed;
- `recommended_default`: a low-risk, reversible choice recorded for veto;
- `open_decision`: a material choice that blocks dispatch until its owner decides.

Do not silently promote an assumption into a fact or a recommended default. A recommended
default is allowed only when changing it would not materially alter scope, risk, cost, public
contracts, approval needs, or acceptance.

## Synthesis Pipeline

### 1. Intake rewrite

Capture:

- User's raw words (verbatim)
- Observed pain / desired direction
- Known environment facts (repo, device, constraints already stated)

Label each statement as `fact`, `assumption`, `recommended_default`, or `open_decision`.
Keep unknowns visible; the manager may resolve a local low-risk gap with a recorded default,
but may not silently rewrite a material choice.

### 2. Outcome rewrite (mandatory)

Write both:

1. **User-facing outcome** — what a human can perceive
2. **System completion condition** — what must be true in the system

And write an explicit contrast:

```text
Success is X.
Success is NOT Y / Z / W.
```

### 3. Fake-success blacklist (mandatory when false-completion risk is material)

List at least three items that look done but are not, appropriate to the domain. Examples of categories (not all required):

- Placeholder / proxy / cached stale UI
- Backend 200 without user-visible effect
- GPU/job complete without presentation
- Tests green for the wrong behavior
- Worker self-assessment
- Microbenchmark without product E2E
- Average improved while p95 worsened

### 4. Constraints and non-goals

Mine hard constraints, ownership boundaries, allowed paths/outputs, compatibility requirements,
and non-goals. If the user cannot articulate a low-risk detail, propose a default and mark it
`recommended_default` for veto. If the choice changes scope, risk, cost, a public contract, or
authorization, record it as an `open_decision` instead.

### 5. Edge cases, failure modes, and approvals

List the relevant boundary conditions before writing tasks. For each one, state the trigger,
expected behavior, evidence that distinguishes it, and whether it is a worker Stop condition.
Consider only applicable cases such as empty/invalid input, timeout or partial failure,
duplicate/retry/resume, concurrency or ownership conflict, unavailable capability, and
user-visible presentation. Do not manufacture a full matrix for a trivial task.

Record approval boundaries explicitly. Destructive or irreversible actions, publication or
deployment, permission changes, production data, paid services, external side effects, and
security/privacy-sensitive changes require an approval decision before dispatch or execution.

### 6. Acceptance with pass algorithms

Each acceptance item should include:

- `id`
- `description`
- `required_evidence`
- `pass_algorithm` (machine-checkable or explicitly human protocol)
- `linked_tasks`

If a number is unknown, do **not** invent a fake threshold. Write:

```text
TBD after Phase 0 measurement; compare against baseline with rule R
```

### 7. Risk-ordered phases (not ownership theater)

Prefer risk order for correctness/performance work:

1. Make success measurable / terminal semantics real
2. Establish baseline (improvement-shaped tasks)
3. Remove proven waste
4. Structural change
5. Integration / presentation
6. Final acceptance

Ownership slices (frontend/backend) are secondary and only after the risk order is clear.

### 8. Task contracts

Every ready implementation task needs:

| Field | Purpose |
|-------|---------|
| Goal | single responsibility |
| Dependencies | what must be PASS |
| Allowed scope | blast radius |
| Inputs / outputs | exact context consumed and artifacts/evidence returned |
| Execution guidance | relevant approach, commands, and existing patterns without irrelevant micro-steps |
| Testing / verification gate | RED/GREEN or substitute |
| PASS | decidable |
| Stop | when to halt instead of thrashing |

### 9. Alignment packet for the user

Because the user may not know how to specify goals, present a short review packet instead of empty questionnaires:

```text
1) 我认为的成功定义（用户结果 + 系统终态，3 行内）
2) 这些不算成功 / 相关假成功信号
3) 范围、所有权、约束、非目标和边界情况
4) 审批边界、验收规则、证据和测量计划
5) 阶段地图与第一个 ready task（单一职责）
6) 推荐默认与仍需拍板的问题（说明影响）
```

Prefer one decision question at a time when blocked; otherwise proceed on recommended
defaults and record them in the active plan or durable contract when one exists.

### 10. Dispatch readiness gate

Before dispatch, the manager must verify that the contract is executable:

- outcome, system completion, `done_when`, and `success_not` are concrete;
- scope, ownership, constraints, non-goals, relevant edge/failure handling, and approval
  boundaries are present;
- each required criterion has evidence and a pass algorithm, or an explicit Phase 0
  measurement rule (`TBD after Phase 0 measurement; compare against baseline with rule R`);
- every unknown is either a recorded low-risk `recommended_default` or an `open_decision`;
- no material `open_decision` remains unresolved;
- the first task has one responsibility, no ownership overlap, bounded inputs/outputs, an
  execution approach, verification gate, PASS, and Stop;
- the runtime has the required capability or a documented safe fallback.

If only a low-risk gap is missing, add the recommended default, expose it in the packet, and
re-run the gate. If a material decision is missing, set `NEEDS_DECISION`/`specified` and ask a
focused question; do not dispatch. The gate is not a reason to invent a worker for a
non-implementation deliverable.

## Document Priority (canonical truth)

When artifacts conflict:

```text
task_spec.md
  > acceptance_registry.json
  > run_state.json
  > tasks/*.md
  > MODEL_RUNBOOK / measurement protocols
  > worker or reviewer prose
```

Review reports are evidence and advice, not a second constitution.

## Quality Gate Before Dispatch

For an explicit harness request or an Audited run, the manager must not dispatch or set
implementation tasks to `running` until the synthesis checklist passes or an explicit user
override is recorded:

- [ ] Raw intent, known facts, assumptions, recommended defaults, and open decisions separated
- [ ] Rewritten goal with user-facing + system completion
- [ ] ≥3 fake-success items when false-completion risk exists
- [ ] Scope/ownership, non-goals, constraints, and compatibility present
- [ ] Relevant edge cases/failure modes and approval boundaries present
- [ ] Acceptance items have `pass_algorithm` or explicit TBD+measurement plan
- [ ] Phases are risk-ordered with dependencies
- [ ] First ready task is narrow and measurable
- [ ] Worker packet has single responsibility, allowed scope, inputs/outputs, execution guidance,
      verification evidence, PASS, and Stop
- [ ] Stop conditions listed
- [ ] Alignment packet produced (or user already approved equivalent)
- [ ] No material open decision remains unresolved

If a low-risk item is missing, record a `recommended_default` and re-run the checklist. If a
material item fails → status `needs_decision` or remain in `specified`, not `dispatched`.

For a non-implementation request, the checklist validates the contract deliverable; it does
not require a dispatch.

## Worker Packet And Parent Acceptance

The manager compiles each ready task into a bounded packet. It must state the single
responsibility, dependencies, allowed read/write scope, inputs, outputs, relevant constraints
and edge cases, execution guidance, testing/verification gate, evidence path, PASS algorithm,
and Stop conditions. It may point to repository patterns and literal commands, but should not
micro-manage choices that do not affect acceptance. The worker must return actual changed paths,
verification output/exit status, unverified paths, assumptions, and blockers. It must stop on
scope/ownership conflict, unsafe approval boundary, missing critical evidence, or repeated
failure without a new diagnosis; it must not expand the contract or recursively delegate.

The parent remains the acceptance authority. It checks the actual diff and allowed boundary,
maps outputs and decisive evidence to `done_when`, verifies non-goals and integration behavior,
and records the acceptance result. A worker's `PASS`, report, or self-assessment is never enough
to claim completion.

## Improvement-Shaped Tasks

If the goal is faster / cheaper / more accurate / more reliable:

1. Force a measurement Phase 0 or a Native baseline note
2. Define terminal metric carefully
3. Require raw evidence retention, not averages only
4. Require real improvement on the user-relevant tail when applicable (e.g. p50 **and** p95), not warm-only or microbenchmark-only wins

## Scoring Hook

Use the bundled scorer only when Audited synthesis quality is itself a blocking question:

```bash
python3 <skill-dir>/scripts/score_harness.py --fixture <artifact-dir> --pretty
```

Interpretation guidance:

| Harness total | Meaning |
|---------------|---------|
| < 45 | empty/weak synthesis — do not treat as executable program of record |
| 45–74 | partial — fill fake-success, pass_algorithm, contracts |
| ≥ 75 | usable Audited instance |
| ≥ 85 | strong synthesis quality |

Scores measure **harness quality**, not product success.

## Anti-Patterns

- Choosing Native/Portable/Audited or dispatching before explicit intent-to-contract synthesis
- Treating “写一个 harness” as permission to create `.harness` or Audited artifacts automatically
- Empty template headings left blank after "init_run"
- Acceptance = "更好 / 更快 / 专业"
- Dispatching workers before terminal success is defined
- Inventing numeric SLOs with no measurement plan
- Audited ceremony for typo-sized work
- Asking a long questionnaire for a low-risk gap that has a safe recommended default
- Treating reviewer essays as overriding task_spec
- Letting a worker invent the contract, redefine acceptance, or self-accept its own output
- Letting workers expand scope because the goal felt big

## Relationship To Other References

- `harness-protocol.md` — control loop and modes
- `tdd-gates.md` — behavior change verification chronology
