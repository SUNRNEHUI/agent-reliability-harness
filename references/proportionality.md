# Proportionality And Progress Budget

Use this reference when coordination competes with implementation, mode selection is
unclear, or reasoning continues without observable progress.

## Decision Checklist

1. Can the active session implement and verify the next slice without expensive context
   reconstruction? Use **Native**.
2. Will work cross a session/model boundary, wait externally, or involve multiple writers
   whose decisions must survive context loss? Use **Portable**.
3. Is the next transition destructive, production-facing, permission-sensitive, disputed,
   or a protected acceptance claim? Add only the required **Audited** controls.

Task size alone is not a mode trigger. A large local implementation can remain Native; a
one-line production permission change may require an Audited control.

## Delivery Budget

Before the first executable or directly testable slice:

- Name the slice and its literal run command or user action.
- Spend at most one coordination pass on routing, reports, or review.
- Keep at least one lane implementing or running the slice.
- Do not start a reviewer until a candidate exists.
- Stop adding process artifacts when their creation takes longer than the next product step.

After the slice runs, spend evidence effort in response to observed mismatch or acceptance
risk. Do not pre-pay every future profile's proof cost.

## Progress Budget

A cycle advances only when it creates new evidence, an artifact change, a test result, or a
binding decision. Planning and prose that restate the same hypothesis do not reset the
budget.

After two no-progress cycles:

1. Mark the path `STALLED`.
2. Separate facts, assumptions, and the current hypothesis.
3. Run the cheapest reversible experiment that can falsify the hypothesis.
4. If it adds no evidence, stop that reasoning chain.
5. Use at most one fresh bounded diagnosis with the compact fact packet, or report the
   blocker.

Do not increase reasoning effort, broaden the inventory, or repeat the full verification
matrix merely because a path stalled.

## Artifact Matrix

| Artifact | Native | Portable | Audited |
| --- | --- | --- | --- |
| Chat plan | Optional, short | Short summary | Summary only |
| Durable contract/capsule | No | Yes | Yes |
| Full task spec/registry/state | No | No | Only when the audited protocol requires it |
| Worker report file | No by default | Only for handoff | Only when acceptance requires it |
| Command/test receipt | Decisive checks | Paths and digests | Typed for protected claims |
| Independent review | One real boundary | One real boundary | Risk-scoped |

Never create both a worker narrative and a manager narrative when one structured result plus
the underlying command receipt answers the acceptance question.

## Review Triage

Blocking findings invalidate the current slice or make continuation unsafe:

- wrong output, broken critical workflow, data loss, or destructive behavior;
- privacy or credential exposure;
- false or chronologically invalid tests/evidence;
- an expensive-to-reverse architecture decision.

Queue wording, report polish, duplicate provenance, future-profile generality, and unrelated
optimization unless the acceptance boundary explicitly requires them.

Review one concrete candidate. After a blocking repair, re-review only the changed surface
and its integration boundary.

## Vertical Slice Order

```text
one real input -> one real execution path -> runnable output -> decisive comparison
-> diagnose observed gap -> fix -> acceptance gate -> expand
```

An `EXPERIMENTAL`, `UNVERIFIED`, or `UNALIGNED` slice may drive the next comparison. It must
not be called exact, accepted, production-ready, or complete.

## Anti-Patterns

| Anti-pattern | Correction |
| --- | --- |
| Every worker gets a task file, report, trace, and reviewer | Use a concise Native result |
| All worker slots analyze or review | Keep an implementation/runtime lane active |
| A final risky claim makes every precursor Audited | Audit the risky transition |
| Full inventory blocks a representative slice | Run it later or in a separate lane |
| Every review comment restarts the loop | Repair only blocking findings |
| Stagnation increases effort or fan-out | Require new evidence or stop |
