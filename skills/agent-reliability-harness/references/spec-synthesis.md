# Spec Synthesis Protocol

Use this when the user goal is vague, incomplete, or outcome-shaped but not yet executable. This protocol turns fuzzy intent into a proportional harness **before** dispatching implementation workers.

This is a **manager capability**. Workers execute contracts; they do not invent the program of record.

## When To Run

Run Spec Synthesis when any of these are true:

- The user states a pain, wish, or direction without measurable acceptance.
- Success could be faked by proxy metrics (loading spinners, unit tests only, self-report).
- The work is multi-stage, resumable, improvement-shaped (latency, cost, accuracy), or high regression risk.
- Audited mode is selected and the goal still lacks measurable acceptance.

Skip when the Native or Portable plan already has measurable acceptance.

## Product Principle

```text
User owns intent and veto.
Manager owns compilation into an executable harness.
Workers own bounded execution inside contracts.
Evaluator/manager owns acceptance from external evidence.
```

## Mode Coupling

```text
Native   -> use the runtime plan; no synthesis artifacts
Portable -> compile the measurable outcome into the three-file contract
Audited  -> add task_spec / registry / tasks / run_state only when protected controls need them
```

Do not create Audited artifacts only to look thorough. A fuzzy goal needs planning; it does
not by itself require durable state or protected controls.

## Synthesis Pipeline

### 1. Intake rewrite

Capture:

- User's raw words (verbatim)
- Observed pain / desired direction
- Known environment facts (repo, device, constraints already stated)

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

Mine hard constraints and non-goals. If the user cannot articulate them, propose defaults and mark them `recommended_default` for veto.

### 5. Acceptance with pass algorithms

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

### 6. Risk-ordered phases (not ownership theater)

Prefer risk order for correctness/performance work:

1. Make success measurable / terminal semantics real
2. Establish baseline (improvement-shaped tasks)
3. Remove proven waste
4. Structural change
5. Integration / presentation
6. Final acceptance

Ownership slices (frontend/backend) are secondary and only after the risk order is clear.

### 7. Task contracts

Every ready implementation task needs:

| Field | Purpose |
|-------|---------|
| Goal | single responsibility |
| Dependencies | what must be PASS |
| Allowed scope | blast radius |
| Testing / verification gate | RED/GREEN or substitute |
| PASS | decidable |
| Stop | when to halt instead of thrashing |

### 8. Alignment packet for the user

Because the user may not know how to specify goals, present a short review packet instead of empty questionnaires:

```text
1) 我认为的成功定义（3 行内）
2) 这些不算成功
3) 默认约束 / 非目标（可删改）
4) 验收规则或测量计划
5) 阶段地图与第一个 ready task
6) 需要你拍板的问题（每个带推荐默认）
```

Prefer one decision question at a time when blocked; otherwise proceed on recommended
defaults and record them in the active plan or durable contract when one exists.

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

For an Audited run, the manager must not set implementation tasks to `running` until the
synthesis checklist passes or an explicit user override is recorded:

- [ ] Rewritten goal with user-facing + system completion
- [ ] ≥3 fake-success items when false-completion risk exists
- [ ] Non-goals + constraints present
- [ ] Acceptance items have `pass_algorithm` or explicit TBD+measurement plan
- [ ] Phases are risk-ordered with dependencies
- [ ] First ready task is narrow and measurable
- [ ] Stop conditions listed
- [ ] Alignment packet produced (or user already approved equivalent)

If checklist fails → status `needs_decision` or remain in `specified`, not `dispatched`.

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

- Empty template headings left blank after "init_run"
- Acceptance = "更好 / 更快 / 专业"
- Dispatching workers before terminal success is defined
- Inventing numeric SLOs with no measurement plan
- Audited ceremony for typo-sized work
- Treating reviewer essays as overriding task_spec
- Letting workers expand scope because the goal felt big

## Relationship To Other References

- `harness-protocol.md` — control loop and modes
- `tdd-gates.md` — behavior change verification chronology
