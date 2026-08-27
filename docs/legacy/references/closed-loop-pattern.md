# Closed Loop Pattern

Long-running work fails through state drift, planning drift, shallow verification, ownership
conflicts, false completion, and reasoning that continues without new evidence. Keep the
loop small, executable, and evidence-driven.

## Five Control Layers

1. **State**
   Durable task state lives outside chat: goal, progress, changed files, decisions, verification, open risks, blockers, and next step.

2. **Planning**
   The plan is a job spec, not a motivational checklist. It defines stage boundaries, inputs, outputs, verification, budget, and stop conditions.

3. **Execution**
   Tool calls and sub-agent results must return to state. File edits, command results, browser findings, API calls, and decisions should be summarized in the ledger when they matter for continuation.

4. **Verification**
   Completion requires evidence. Tests, builds, screenshots, database readback, logs, CI, and evaluator reports are stronger than the executor saying the work is done.

5. **Supervision**
   The system must know when to stop: scope growth, budget pressure, repeated failures, destructive actions, release/publish steps, paid APIs, permissions, production data, or ownership conflicts.

## Practical Patterns

- **Delivery-first:** run the smallest end-to-end slice before expanding inventory, reports,
  or review surfaces.
- **Spec-first:** clarify goal, non-goals, constraints, acceptance criteria, and risk before large execution.
- **Plan gate:** review a consequential task split once; do not review the plan instead of
  building the candidate.
- **Progress breaker:** after two no-progress cycles, run one falsifying experiment, then
  stop or use one fresh bounded diagnosis.
- **Progress ledger:** update durable state after each meaningful stage.
- **Sub-agent results:** return concise evidence; write reports only for handoff or audit.
- **Independent evaluator:** review a concrete high-risk or user-facing candidate.
- **Browser-level verification:** web products must be clicked and inspected, not only checked by curl or unit tests.
- **Rollback path:** preserve a way back before high-impact operations.
- **Trace important steps:** keep enough evidence to answer why a decision was made and how completion was verified.

The loop is `build -> run -> compare -> diagnose -> fix -> verify`. Planning, reporting, and
review remain supporting actions unless risk requires a separate gate.
