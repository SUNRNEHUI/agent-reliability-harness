# Portable Contract v2

Use this reference only when work must survive a session, runtime, or model boundary.

## Contents

- [Purpose](#purpose)
- [Files](#files)
- [Materialize](#materialize)
- [Checkpoint](#checkpoint)
- [Handoff And Resume](#handoff-and-resume)
- [Close](#close)
- [Capsule Budget](#capsule-budget)
- [Capability Portability](#capability-portability)
- [Audited Escalation](#audited-escalation)
- [Legacy Compatibility](#legacy-compatibility)

## Purpose

`arh-portable-v2` stores the facts a replacement agent cannot safely or cheaply
reconstruct from the repository:

- the user-visible goal and observable completion criteria;
- hard constraints and non-goals;
- completed milestones, blockers, and one literal next action;
- material decisions with short rationale;
- repository fingerprint and changed paths;
- evidence paths and digests;
- required capabilities and tiered context reads.

It never stores chain-of-thought, full chat transcripts, provider reasoning items, secrets,
or in-flight external side effects.

## Files

```text
.harness/<slug>/
├── contract.json
├── events.jsonl
└── capsule.md
```

`contract.json` is the only mutable source of truth. `events.jsonl` is an append-only
index of material transitions and evidence. `capsule.md` is regenerated projection for a
receiving model; never edit it as state.

## Materialize

Use native planning first. Materialize only after the plan is actionable and a durability
trigger exists.

```bash
python3 <skill-dir>/scripts/harnessctl.py materialize <project-root> \
  --title "<title>" \
  --goal "<user-visible outcome>" \
  --done-when "<observable criterion>" \
  --constraint "<hard constraint>" \
  --next-action "<one literal action>"
```

Repeat `--done-when`, `--constraint`, `--non-goal`, `--required-capability`,
`--optional-capability`, `--must-read`, or `--read-if-needed` as needed. Keep each list
short. Do not materialize an empty plan skeleton.

## Checkpoint

Checkpoint after a verified milestone or before a likely interruption, not after every
tool call.

```bash
python3 <skill-dir>/scripts/harnessctl.py checkpoint <project-root> \
  --runtime <runtime> \
  --actor-id <actor> \
  --owner-epoch <epoch> \
  --completed "<observable result>" \
  --next-action "<literal next action>" \
  --pending-verification "<remaining check>" \
  --evidence-file <project-relative-path> \
  --reason "<why checkpoint now>"
```

The first checkpoint claims epoch 1 and therefore omits `--owner-epoch`. Later mutations
must provide the current epoch. `--decision` and `--decision-reason` must be supplied
together. After verification finishes, use `--clear-pending-verification`; remove a resolved
blocker by its exact text with `--resolve-blocker`.

Evidence files remain in the project. The contract stores only project-relative path,
SHA-256, and size; it does not duplicate output.

## Handoff And Resume

For a clean transfer:

```bash
python3 <skill-dir>/scripts/harnessctl.py handoff <project-root> \
  --actor-id <actor> --owner-epoch <epoch> \
  --next-action "<literal next action>" --reason "<why transfer>"
```

The replacement runtime runs:

```bash
python3 <skill-dir>/scripts/harnessctl.py resume <project-root> \
  --runtime <runtime> --actor-id <new-actor>
```

An abrupt takeover of an active owner requires `--takeover-reason`. Resume validates the
contract, checks repository drift, claims the next epoch, regenerates the capsule, and
returns:

- `capsule`: bounded model-facing context;
- `must_read`: files required before acting;
- `read_if_needed`: files loaded only for a concrete gap;
- `workspace_drift` and `changed_paths`;
- current and previous owners;
- the safe next action.

If drift exists, inspect it before following the recorded action. A capsule cannot prove
that an external side effect completed.

## Close

Close a terminal contract so it no longer participates in active-run selection:

```bash
python3 <skill-dir>/scripts/harnessctl.py close <project-root> \
  --status <accepted|failed|cancelled> \
  --actor-id <actor> --owner-epoch <epoch> \
  --reason "<terminal reason>"
```

`accepted` requires at least one evidence record and rejects unresolved blockers or pending
verification. Add `--evidence-file` when the final evidence was not checkpointed already.
Failed or cancelled closure still requires an acquired owner and a reason.

## Capsule Budget

The default capsule ceiling is 6,000 characters. This is a deterministic character limit,
not a claimed tokenizer-accurate token count. `pack --max-chars <N>` can enforce a different
budget. When a capsule exceeds the limit, reduce repeated state; do not truncate acceptance,
blockers, or evidence silently.

## Capability Portability

The contract uses capability names rather than model names. A receiving agent may continue
when it can read the workspace and satisfy all required capabilities. Missing optional
capabilities require a documented fallback. Missing required capabilities block execution.

Provider-specific model selection, persisted reasoning, prompt caching, native subagent
IDs, and UI state remain outside the portable core. Runtime adapters may use them while
active, but the next model must not need them to understand the capsule.

## Audited Escalation

Portable is not a weaker synonym for unsafe execution. Escalate to Audited extensions when
the task needs typed acceptance receipts, a Production State Witness, protected TDD
chronology, evaluator separation, or stronger rollback controls. Store each extension under
`contract.json.extensions`; absent extensions must not create empty fields.

## Legacy Compatibility

`handoff-v1` Full artifacts remain supported by existing `checkpoint`, `handoff`, `resume`,
and validation commands. Do not rewrite a valid legacy artifact merely to change its format.
Create new work as Portable v2 unless the task independently requires Audited controls.
