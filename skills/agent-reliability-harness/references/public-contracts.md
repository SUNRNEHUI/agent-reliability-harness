# Public Contracts

This reference defines the machine-readable and command-line boundaries that external
automation may consume. It is intentionally separate from the implementation modules.

## Versioned schemas

The `schemas/` directory is part of the canonical runtime package. The JSON Schema files use
Draft 2020-12 and have stable `$id` values:

| Artifact | Schema | Source of truth |
| --- | --- | --- |
| Portable Contract | `portable-contract-v2.schema.json` | `.harness/<slug>/contract.json` |
| Audited run state | `audited-run-state-v1.schema.json` | `run_state.json` |
| Acceptance registry | `acceptance-registry-v1.schema.json` | `acceptance_registry.json` |
| Worker result | `worker-result-v2.schema.json` | `templates/worker_result.json` |
| Status projection | `status-output-v1.schema.json` | `scripts/status.py --json` |

Schema validation covers JSON types, required fields, enum values, and relationships that can
be described inside one JSON document. It does not replace the standard-library runtime
validators. Runtime validation remains authoritative for artifact/project path binding,
cross-file digests, JSONL chronology, owner epochs, state transitions, evidence receipts,
workspace drift, and acceptance gates.

Provider and model identifiers are not part of the Portable Contract schema. Runtime-specific
dispatch records may contain those fields in Audited state, but a requested model is never
evidence that the runtime resolved that model.

## CLI compatibility

`harnessctl.py` keeps its existing subcommands and exit behavior. `--help` exits `0`; parser
usage errors and guarded operation failures exit `2`; validation and discovery reports return
`1` when an input is semantically invalid; a successful command exits `0`.

`status.py` keeps human output as the default. It exits `0` even when the summary reports
blocked work or integrity errors, preserving the historical reporting behavior. Add
`--require-high-confidence` to turn the confidence result into a gate: non-`high` exits `1`
and prints a gate message in human mode. Add `--json` for the versioned `arh-status-v1`
projection. JSON mode always emits one JSON object on stdout, including when the strict gate
returns `1`; the human gate message is not mixed into machine output.

## Integrity boundary

Evidence records contain SHA-256 digests so the harness can detect content changes after a
receipt was recorded. A digest is an integrity check, not a digital signature: it does not
authenticate the writer or establish trust across an untrusted process boundary. The runtime
owner/role checks are cooperative guards; they are not operating-system access control.
