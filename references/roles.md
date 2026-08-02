# Roles

Use these role boundaries when assigning multi-agent work.

## Manager

- Owns the delivery slice, ownership boundaries, merge, and final acceptance. Owns durable
  state only when the selected mode requires it.
- Does not outsource the immediate critical-path task if the next local step depends on it.
- Keeps at least one lane implementing or running the product.
- Applies the Progress Circuit Breaker and rejects repeated work without a new progress event.
- Reviews the underlying critical evidence without requiring duplicate Native reports.
- On session entry, resumes the unique active Full run before edits and adopts the returned
  actor/epoch fencing token.
- Checkpoints explicit next action and pending verification at durable boundaries; on clean
  exit, marks continuation ready for handoff.

## Explorer

- Answers specific codebase or system questions.
- Does not edit files.
- Returns concise findings, relevant paths, and confidence level.

Use for: unfamiliar code areas, dependency mapping, identifying test commands, locating ownership boundaries.

## Fresh Diagnoser

- Receives facts, assumptions, the current hypothesis, and the failed falsifying experiment.
- Receives no full transcript and no mandate to implement or explore exhaustively.
- Returns one changed diagnosis and one cheapest discriminating action, or a concrete blocker.
- Does not raise reasoning effort merely because the previous path stalled.

Use once after two no-progress cycles or repeated verification failures when genuinely new
diagnosis is possible.

## State Witness / Adversarial Reviewer

- Owns production-state fidelity, not implementation.
- Traces the reported user action through the real call sites that compute the decision.
- Names every gate input, producer, lifecycle, and state combination in `state_witness.md`.
- Reviews a concrete GREEN candidate and tries to find a real production combination missing
  from tests.
- Returns FAIL when a test uses a synthetic or semantically unreachable combination, even if
  the policy function passes.
- A blocking FAIL creates one focused repair and changed-surface re-review. Nonblocking
  findings stay queued.

Use for: blank/spinner/stuck UI, token/generation races, async queues, policy gates,
feature flags, lifecycle cleanup, and any bug described with multiple Boolean/enum states.

## Worker

- Implements a bounded slice.
- Has explicit file or responsibility ownership.
- Must not revert changes made by others.
- Returns changed files, decisive commands, risks, and unverified paths. Writes a report file
  only when handoff or audit requires durability.

Use for: frontend slice, backend slice, tests slice, migration slice, docs slice.

## Evaluator

- Verifies outputs against acceptance criteria.
- Does not explain away missing evidence.
- Must be allowed to return FAIL.
- Checks for stubs, TODOs, mocks, UI/browser gaps, and missing readback.

Use for: user-facing workflows, high-risk changes, release gates, broad UI changes.

Do not assign an Evaluator to a plan, report, or artifact that cannot yet run.

## Merger

- Reads reports and diffs.
- Resolves conflicts only within authorized ownership boundaries.
- Runs the smallest sufficient integration verification.

Use only when merge work is large enough to justify a separate role.
