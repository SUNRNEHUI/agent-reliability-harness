#!/usr/bin/env python3
"""Print a compact human-readable status summary from run_state.json."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from harness_schema import ACCEPTANCE_STATUSES as VALID_ACCEPTANCE_STATUSES
from harness_schema import TERMINAL_RUN_STATUSES
from harness_schema import is_audited_mode
from harnessctl import (
    validate_active_tdd_gates,
    validate_canonical_state_digests,
    validate_cross_file_invariants,
    validate_evidence_receipts,
    validate_jsonl,
    validate_trace_transactions,
)
from validate_report import validate_acceptance_registry, validate_run_state


DONE_TASK_STATUSES = {"passed", "merged"}
BLOCKING_TASK_STATUSES = {"blocked", "verify_failed"}
ACCEPTANCE_STATUSES = tuple(sorted(VALID_ACCEPTANCE_STATUSES))
STATUS_SCHEMA = "arh-status-v1"
STATUS_SCHEMA_VERSION = 1


def load_state(path: Path) -> dict[str, object]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise SystemExit(f"invalid JSON: {path}: {exc}") from exc
    if not isinstance(data, dict):
        raise SystemExit(f"run state root must be an object: {path}")
    return data


def load_acceptance_registry(path: Path) -> tuple[str, dict[str, object] | None]:
    if not path.exists():
        return "missing", None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return "unreadable", None
    if not isinstance(data, dict):
        return "unreadable", None
    return "available", data


def task_blockers(tasks: list[object]) -> list[str]:
    blockers: list[str] = []
    for item in tasks:
        if not isinstance(item, dict):
            continue
        status = item.get("status")
        if status in BLOCKING_TASK_STATUSES:
            task_id = item.get("id", "?")
            name = item.get("name", "")
            reason = item.get("stop_reason") or "no stop reason recorded"
            blockers.append(f"{task_id} {name}: {reason}")
    return blockers


def resource_budget_blockers(items: list[object], scope: str = "task") -> list[str]:
    """Return blockers for an explicitly exhausted or unavailable token budget."""
    blockers: list[str] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        budget = item.get("resource_budget")
        if not isinstance(budget, dict) or not isinstance(budget.get("token_budget"), int):
            continue
        item_id = item.get("id", "?")
        name = item.get("name", "")
        label = f"{scope} {item_id} {name}".strip()
        if budget.get("usage_kind") == "unknown":
            blockers.append(f"{label}: token budget accounting unavailable")
            continue
        tokens_used = budget.get("tokens_used")
        tokens_remaining = budget.get("tokens_remaining")
        if (
            isinstance(tokens_used, int)
            and tokens_used >= budget["token_budget"]
        ) or (isinstance(tokens_remaining, int) and tokens_remaining <= 0):
            blockers.append(f"{label}: token budget exhausted")
    return blockers


def task_completion(tasks: list[object]) -> tuple[int, int]:
    total = 0
    done = 0
    for item in tasks:
        if not isinstance(item, dict):
            continue
        total += 1
        if item.get("status") in DONE_TASK_STATUSES:
            done += 1
    return done, total


def task_evidence_gaps(tasks: list[object]) -> list[str]:
    gaps: list[str] = []
    for item in tasks:
        if not isinstance(item, dict):
            continue
        status = item.get("status")
        if status not in DONE_TASK_STATUSES:
            continue
        evidence = item.get("evidence")
        if isinstance(evidence, list) and evidence:
            continue
        task_id = item.get("id", "?")
        gaps.append(f"task {task_id} {status} without evidence")
    return gaps


def acceptance_rollup(registry: dict[str, object] | None) -> tuple[dict[str, int], list[str], bool]:
    counts = {status: 0 for status in ACCEPTANCE_STATUSES}
    gaps: list[str] = []
    if registry is None:
        return counts, gaps, False

    criteria = registry.get("criteria")
    if not isinstance(criteria, list):
        return counts, ["acceptance registry missing criteria list"], True
    if not criteria:
        return counts, ["acceptance registry has no criteria"], True

    for index, item in enumerate(criteria, start=1):
        if not isinstance(item, dict):
            gaps.append(f"acceptance criteria[{index}] is not an object")
            continue
        status = item.get("status")
        if status in counts:
            counts[str(status)] += 1
        else:
            gaps.append(f"acceptance {item.get('id', index)} has unsupported status {status!r}")
        if status in {"pass", "scoped_out"}:
            evidence = item.get("evidence")
            if isinstance(evidence, list) and evidence:
                continue
            gaps.append(f"acceptance {item.get('id', index)} {status} without evidence")
    return counts, gaps, False


def accepted_state_conflicts(run_status: str, acceptance_counts: dict[str, int], registry_error: bool) -> list[str]:
    if run_status != "accepted":
        return []
    conflicts: list[str] = []
    if registry_error:
        conflicts.append("run_state accepted but acceptance registry is malformed")
    if acceptance_counts["pending"]:
        conflicts.append("run_state accepted but acceptance criteria are pending")
    if acceptance_counts["fail"] or acceptance_counts["blocked"]:
        conflicts.append("run_state accepted but acceptance criteria failed or blocked")
    return conflicts


def confidence_level(
    mode: str,
    registry_status: str,
    acceptance_counts: dict[str, int],
    blockers: list[str],
    conflicts: list[str],
    evidence_gaps: list[str],
    registry_error: bool,
    done: int,
    total: int,
    integrity_errors: list[str],
) -> str:
    if integrity_errors or blockers or conflicts or registry_error or acceptance_counts["fail"] or acceptance_counts["blocked"]:
        return "blocked"
    if is_audited_mode(mode) and registry_status != "available":
        return "unknown"
    if acceptance_counts["pending"]:
        return "medium" if done == total and total > 0 else "low"
    if evidence_gaps:
        return "medium" if done == total and total > 0 else "low"
    if total > 0 and done == total:
        return "high"
    return "unknown"


def next_verification(
    mode: str,
    registry_status: str,
    acceptance_counts: dict[str, int],
    blockers: list[str],
    conflicts: list[str],
    evidence_gaps: list[str],
    registry_error: bool,
    done: int,
    total: int,
    integrity_errors: list[str],
) -> str:
    if blockers:
        return "resolve blockers"
    if registry_error:
        return "repair acceptance_registry.json"
    if conflicts:
        return "repair accepted run state or acceptance registry"
    if integrity_errors:
        return "repair artifact integrity errors"
    if is_audited_mode(mode) and registry_status == "missing":
        return "create or locate acceptance_registry.json"
    if is_audited_mode(mode) and registry_status == "unreadable":
        return "repair acceptance_registry.json"
    if acceptance_counts["fail"] or acceptance_counts["blocked"]:
        return "repair failing or blocked acceptance criteria"
    if acceptance_counts["pending"]:
        return "resolve pending acceptance criteria"
    if evidence_gaps:
        return "record missing evidence"
    if total and done < total:
        return "finish remaining tasks"
    return "none"


def _status_evaluation(data: dict[str, object], state_path: Path | None = None) -> dict[str, object]:
    """Compute the shared status facts used by human, JSON, and strict output."""
    mode = str(data.get("mode") or "full")
    status = str(data.get("status") or "unknown")
    raw_tasks = data.get("tasks")
    tasks = raw_tasks if isinstance(raw_tasks, list) else []
    raw_stages = data.get("stages")
    stages = raw_stages if isinstance(raw_stages, list) else []

    registry_status = "not_applicable"
    registry: dict[str, object] | None = None
    registry_path: Path | None = None
    if state_path is not None and is_audited_mode(mode):
        registry_path = state_path.parent / "acceptance_registry.json"
        registry_status, registry = load_acceptance_registry(registry_path)
    acceptance_counts, acceptance_gaps, registry_error = acceptance_rollup(registry)
    blockers = [
        *task_blockers(tasks),
        *resource_budget_blockers(tasks),
        *resource_budget_blockers(stages, "stage"),
    ]
    conflicts = accepted_state_conflicts(status, acceptance_counts, registry_error)
    evidence_gaps = [*task_evidence_gaps(tasks), *acceptance_gaps]
    integrity_errors = validate_run_state(state_path) if state_path is not None else []
    if state_path is not None and is_audited_mode(mode):
        if registry_path is not None and registry_status == "available":
            integrity_errors.extend(validate_acceptance_registry(registry_path))
            integrity_errors.extend(validate_cross_file_invariants(state_path, registry_path))
            if registry is not None:
                integrity_errors.extend(validate_active_tdd_gates(state_path.parent, data, registry))
        trace_path = state_path.parent / "trace.jsonl"
        integrity_errors.extend(validate_jsonl(trace_path))
        integrity_errors.extend(validate_jsonl(state_path.parent / "tdd_trace.jsonl"))
        integrity_errors.extend(validate_trace_transactions(trace_path))
        integrity_errors.extend(validate_canonical_state_digests(state_path.parent))
        integrity_errors.extend(validate_evidence_receipts(state_path.parent))

    done, total = task_completion(tasks)
    confidence = confidence_level(
        mode,
        registry_status,
        acceptance_counts,
        blockers,
        conflicts,
        evidence_gaps,
        registry_error,
        done,
        total,
        integrity_errors,
    )
    stage_records = [item for item in stages if isinstance(item, dict)]
    stages_complete = bool(stage_records) and all(
        item.get("status") in {"passed", "merged"} for item in stage_records
    )
    terminal_run = status in {"accepted", "handed_off"}
    if confidence == "high" and (not terminal_run or not stages_complete):
        confidence = "medium"
    next_action = next_verification(
        mode,
        registry_status,
        acceptance_counts,
        blockers,
        conflicts,
        evidence_gaps,
        registry_error,
        done,
        total,
        integrity_errors,
    )
    if next_action == "none" and (not terminal_run or not stages_complete):
        next_action = "finalize run status and stage rollup through harnessctl.py run-set"
    return {
        "mode": mode,
        "status": status,
        "tasks": tasks,
        "stages": stages,
        "done": done,
        "total": total,
        "registry_status": registry_status,
        "registry_error": registry_error,
        "acceptance_counts": acceptance_counts,
        "acceptance_gaps": acceptance_gaps,
        "blockers": blockers,
        "conflicts": conflicts,
        "evidence_gaps": evidence_gaps,
        "integrity_errors": integrity_errors,
        "confidence": confidence,
        "next_action": next_action,
    }


def _safe_sequence(value: object) -> int:
    try:
        sequence = int(value or 0)
    except (TypeError, ValueError):
        return 0
    return sequence if sequence >= 0 else 0


def status_payload(data: dict[str, object], state_path: Path | None = None) -> dict[str, object]:
    """Return the stable machine-readable projection for ``status.py --json``.

    This intentionally exposes summary facts rather than the live run-state object.  The
    latter is an implementation artifact whose fields can grow independently of this
    versioned public status envelope.
    """
    evaluation = _status_evaluation(data, state_path)
    stages = evaluation["stages"]
    tasks = evaluation["tasks"]

    stage_payload = [
        {
            "id": str(item.get("id") or "?"),
            "name": str(item.get("name") or ""),
            "status": str(item.get("status") or "unknown"),
            "tasks": [str(task_id) for task_id in item.get("tasks", [])]
            if isinstance(item.get("tasks"), list)
            else [],
        }
        for item in stages
        if isinstance(item, dict)
    ]
    task_payload = [
        {
            "id": str(item.get("id") or "?"),
            "name": str(item.get("name") or ""),
            "status": str(item.get("status") or "unknown"),
            "stage": str(item.get("stage") or ""),
            "stop_reason": str(item.get("stop_reason") or ""),
            "evidence_count": len(item.get("evidence")) if isinstance(item.get("evidence"), list) else 0,
        }
        for item in tasks
        if isinstance(item, dict)
    ]

    continuation_payload: dict[str, object] | None = None
    continuation = data.get("continuation")
    if isinstance(continuation, dict):
        owner = continuation.get("owner")
        owner = owner if isinstance(owner, dict) else {}
        checkpoint = continuation.get("checkpoint")
        checkpoint = checkpoint if isinstance(checkpoint, dict) else {}
        continuation_status = str(continuation.get("status") or "unknown")
        terminal_run = evaluation["status"] in TERMINAL_RUN_STATUSES
        if terminal_run:
            readiness = "terminal"
        elif continuation_status == "ready":
            readiness = "ready"
        elif _safe_sequence(checkpoint.get("sequence")) > 0:
            readiness = "checkpointed"
        else:
            readiness = "not_checkpointed"
        continuation_payload = {
            "status": continuation_status,
            "owner": {
                "actor_id": str(owner.get("actor_id") or ""),
                "runtime": str(owner.get("runtime") or ""),
                "epoch": _safe_sequence(owner.get("epoch")),
            },
            "checkpoint": {
                "sequence": _safe_sequence(checkpoint.get("sequence")),
                "current_task": str(checkpoint.get("current_task") or ""),
                "next_action": str(checkpoint.get("next_action") or ""),
                "pending_verification": [str(item) for item in checkpoint.get("pending_verification", [])]
                if isinstance(checkpoint.get("pending_verification"), list)
                else [],
            },
            "readiness": readiness,
        }

    memory_candidates = 0
    state_layers = data.get("state_layers")
    if isinstance(state_layers, dict):
        memory_boundary = state_layers.get("memory_boundary")
        if isinstance(memory_boundary, dict) and isinstance(memory_boundary.get("memory_candidates"), list):
            memory_candidates = len(memory_boundary["memory_candidates"])

    integrity_errors = evaluation["integrity_errors"]
    return {
        "schema": STATUS_SCHEMA,
        "version": STATUS_SCHEMA_VERSION,
        "state_path": str(state_path) if state_path is not None else "",
        "title": str(data.get("title") or "untitled"),
        "mode": evaluation["mode"],
        "status": evaluation["status"],
        "current_stage": str(data.get("current_stage") or ""),
        "stages": stage_payload,
        "tasks": task_payload,
        "completion": {"done": evaluation["done"], "total": evaluation["total"]},
        "continuation": continuation_payload,
        "acceptance": {
            "registry_status": evaluation["registry_status"],
            "registry_error": evaluation["registry_error"],
            "counts": evaluation["acceptance_counts"],
            "gaps": evaluation["acceptance_gaps"],
        },
        "blockers": evaluation["blockers"],
        "state_conflicts": evaluation["conflicts"],
        "evidence_gaps": evaluation["evidence_gaps"],
        "integrity": {
            "status": "pass" if not integrity_errors else "fail",
            "errors": integrity_errors,
        },
        "integrity_errors": integrity_errors,
        "completion_confidence": evaluation["confidence"],
        "next_verification": evaluation["next_action"],
        "memory_candidates": memory_candidates,
        "generated_files": [str(item) for item in data.get("generated_files", [])]
        if isinstance(data.get("generated_files"), list)
        else [],
        "stop_reason": str(data.get("stop_reason") or ""),
    }


def status_confidence(data: dict[str, object], state_path: Path) -> str:
    """Return the confidence used by the historical strict status gate."""
    return str(_status_evaluation(data, state_path)["confidence"])


def format_status(data: dict[str, object], state_path: Path | None = None) -> str:
    title = str(data.get("title") or "untitled")
    mode = str(data.get("mode") or "full")
    status = str(data.get("status") or "unknown")
    lines = [f"Run: {title} | Mode: {mode} | Status: {status}"]

    current_stage = str(data.get("current_stage") or "")
    stages = data.get("stages")
    if isinstance(stages, list):
        for item in stages:
            if not isinstance(item, dict):
                continue
            stage_id = str(item.get("id") or "?")
            prefix = "Stage"
            if current_stage and stage_id == current_stage:
                prefix = "Stage"
            lines.append(f"{prefix} {stage_id}: {item.get('name', '')} [{item.get('status', 'unknown')}]")

    tasks = data.get("tasks")
    if isinstance(tasks, list):
        for item in tasks:
            if not isinstance(item, dict):
                continue
            lines.append(f"  {item.get('id', '?')} {item.get('name', '')} {item.get('status', 'unknown')}")
    else:
        tasks = []

    done, total = task_completion(tasks)
    lines.append(f"Completion: {done}/{total} tasks done")

    continuation = data.get("continuation")
    if isinstance(continuation, dict):
        continuation_status = str(continuation.get("status") or "unknown")
        owner = continuation.get("owner")
        owner = owner if isinstance(owner, dict) else {}
        lines.append(
            "Continuation: "
            f"{continuation_status} | "
            f"owner={owner.get('actor_id') or 'none'} | "
            f"runtime={owner.get('runtime') or 'none'} | "
            f"epoch={owner.get('epoch', 0)}"
        )
        checkpoint = continuation.get("checkpoint")
        checkpoint = checkpoint if isinstance(checkpoint, dict) else {}
        if status in TERMINAL_RUN_STATUSES:
            lines.append("Checkpoint: terminal run; no resume checkpoint required")
            lines.append("Handoff readiness: terminal")
        else:
            lines.append(
                "Checkpoint: "
                f"sequence={checkpoint.get('sequence', 0)} | "
                f"task={checkpoint.get('current_task') or 'none'} | "
                f"next={checkpoint.get('next_action') or 'none'}"
            )
            if continuation_status == "ready":
                readiness = "ready"
            elif int(checkpoint.get("sequence") or 0) > 0:
                readiness = "checkpointed"
            else:
                readiness = "not_checkpointed"
            lines.append(f"Handoff readiness: {readiness}")

    registry_status = "not_applicable"
    registry: dict[str, object] | None = None
    registry_path: Path | None = None
    if state_path is not None and is_audited_mode(mode):
        registry_path = state_path.parent / "acceptance_registry.json"
        registry_status, registry = load_acceptance_registry(registry_path)
    acceptance_counts, acceptance_gaps, registry_error = acceptance_rollup(registry)
    if is_audited_mode(mode):
        if registry_status == "available":
            lines.append(
                "Acceptance: "
                f"{acceptance_counts['pass']} pass, "
                f"{acceptance_counts['pending']} pending, "
                f"{acceptance_counts['fail']} fail, "
                f"{acceptance_counts['blocked']} blocked, "
                f"{acceptance_counts['scoped_out']} scoped_out"
            )
        else:
            lines.append(f"Acceptance: {registry_status}")

    stage_items = stages if isinstance(stages, list) else []
    blockers = [
        *task_blockers(tasks),
        *resource_budget_blockers(tasks),
        *resource_budget_blockers(stage_items, "stage"),
    ]
    lines.append("Blockers: " + ("; ".join(blockers) if blockers else "none"))

    conflicts = accepted_state_conflicts(status, acceptance_counts, registry_error)
    if conflicts:
        lines.append("State conflicts: " + "; ".join(conflicts))

    evidence_gaps = [*task_evidence_gaps(tasks), *acceptance_gaps]
    lines.append("Evidence gaps: " + ("; ".join(evidence_gaps) if evidence_gaps else "none"))

    integrity_errors = validate_run_state(state_path) if state_path is not None else []
    if state_path is not None and is_audited_mode(mode):
        if registry_path is not None and registry_status == "available":
            integrity_errors.extend(validate_acceptance_registry(registry_path))
            integrity_errors.extend(validate_cross_file_invariants(state_path, registry_path))
            if registry is not None:
                integrity_errors.extend(validate_active_tdd_gates(state_path.parent, data, registry))
        trace_path = state_path.parent / "trace.jsonl"
        integrity_errors.extend(validate_jsonl(trace_path))
        integrity_errors.extend(validate_jsonl(state_path.parent / "tdd_trace.jsonl"))
        integrity_errors.extend(validate_trace_transactions(trace_path))
        integrity_errors.extend(validate_canonical_state_digests(state_path.parent))
        integrity_errors.extend(validate_evidence_receipts(state_path.parent))
    lines.append("Integrity errors: " + ("; ".join(integrity_errors) if integrity_errors else "none"))

    confidence = confidence_level(
        mode,
        registry_status,
        acceptance_counts,
        blockers,
        conflicts,
        evidence_gaps,
        registry_error,
        done,
        total,
        integrity_errors,
    )
    stage_records = [item for item in stages if isinstance(item, dict)] if isinstance(stages, list) else []
    stages_complete = bool(stage_records) and all(item.get("status") in {"passed", "merged"} for item in stage_records)
    terminal_run = status in {"accepted", "handed_off"}
    if confidence == "high" and (not terminal_run or not stages_complete):
        confidence = "medium"
    lines.append(f"Completion confidence: {confidence}")
    next_action = next_verification(
        mode,
        registry_status,
        acceptance_counts,
        blockers,
        conflicts,
        evidence_gaps,
        registry_error,
        done,
        total,
        integrity_errors,
    )
    if next_action == "none" and (not terminal_run or not stages_complete):
        next_action = "finalize run status and stage rollup through harnessctl.py run-set"
    lines.append(
        "Next verification: "
        + next_action
    )

    state_layers = data.get("state_layers")
    if isinstance(state_layers, dict):
        memory_boundary = state_layers.get("memory_boundary")
        if isinstance(memory_boundary, dict):
            candidates = memory_boundary.get("memory_candidates")
            if isinstance(candidates, list):
                lines.append(f"Memory candidates: {len(candidates)}")

    generated_files = data.get("generated_files")
    if isinstance(generated_files, list):
        lines.append("Generated files: " + ", ".join(str(item) for item in generated_files))

    stop_reason = data.get("stop_reason")
    if stop_reason:
        lines.append(f"Stop reason: {stop_reason}")

    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description="Print a compact run status from run_state.json.")
    parser.add_argument("path", type=Path, help="Path to run_state.json")
    parser.add_argument(
        "--json",
        action="store_true",
        dest="as_json",
        help="Emit the versioned machine-readable status envelope.",
    )
    parser.add_argument(
        "--require-high-confidence",
        action="store_true",
        help="Exit nonzero unless the run reaches high completion confidence.",
    )
    args = parser.parse_args()

    path = args.path.expanduser().resolve()
    data = load_state(path)
    if args.as_json:
        print(json.dumps(status_payload(data, path), ensure_ascii=False, indent=2, sort_keys=True))
    else:
        print(format_status(data, path))
    if args.require_high_confidence and status_confidence(data, path) != "high":
        if not args.as_json:
            print("Status gate: requires high completion confidence")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
