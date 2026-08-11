#!/usr/bin/env python3
"""Validate and mutate Audited or legacy Full state through guarded commands."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
import subprocess
import sys
import tempfile
import uuid
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

from harness_schema import (
    ACCEPTANCE_STATUSES,
    ACCEPTANCE_TRANSITIONS,
    AGENT_PROFILES,
    CONTINUATION_PROTOCOL,
    DISPATCH_STATUSES,
    DISPATCH_TRANSITIONS,
    EVIDENCE_POLICY,
    QUALIFYING_EVIDENCE_TYPES,
    RUN_STATUSES,
    RUN_TRANSITIONS,
    TASK_STATUSES,
    TASK_TRANSITIONS,
    TERMINAL_RUN_STATUSES,
    VERIFICATION_TIERS,
    is_audited_mode,
)
from runtime_profiles import model_profiles_for
from runtime_state import append_jsonl, locked, mutate_json
from state_witness_check import validate as validate_state_witness
from validate_report import validate_acceptance_registry, validate_run_state
from tdd_gate_check import gate_mode_of, latest_gate_decision, load_events, validate_trace as validate_tdd_trace


DIGEST_ANCHOR_EVENTS = {"run_initialized", "state_sealed", "state_reseal_baseline"}
PORTABLE_PROTOCOL = "arh-portable-v2"
PORTABLE_SCHEMA_VERSION = 2
PORTABLE_TERMINAL_STATUSES = {"accepted", "failed", "cancelled"}
DEFAULT_CAPSULE_MAX_CHARS = 6000


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def serialized_json(value: dict[str, object]) -> bytes:
    return (json.dumps(value, ensure_ascii=False, indent=2) + "\n").encode("utf-8")


def sha256(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def load_object(path: Path) -> dict[str, object]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise ValueError(f"missing file: {path}") from exc
    except json.JSONDecodeError as exc:
        raise ValueError(f"invalid JSON: {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise ValueError(f"JSON root must be an object: {path}")
    return value


def portable_contract_errors(contract: dict[str, object], artifact_dir: Path) -> list[str]:
    errors: list[str] = []
    if contract.get("schema_version") != PORTABLE_SCHEMA_VERSION:
        errors.append(f"schema_version must be {PORTABLE_SCHEMA_VERSION}")
    if contract.get("protocol") != PORTABLE_PROTOCOL:
        errors.append(f"protocol must be {PORTABLE_PROTOCOL}")
    if contract.get("mode") != "portable":
        errors.append("mode must be portable")
    status = str(contract.get("status") or "")
    if status not in {"active", *PORTABLE_TERMINAL_STATUSES}:
        errors.append("status must be active, accepted, failed, or cancelled")

    recorded_dir = str(contract.get("artifact_dir") or "").strip()
    if not recorded_dir:
        errors.append("artifact_dir must be non-empty")
    elif Path(recorded_dir).expanduser().resolve() != artifact_dir.resolve():
        errors.append("artifact_dir does not match the opened contract directory")

    project_root = str(contract.get("project_root") or "").strip()
    if not project_root:
        errors.append("project_root must be non-empty")
    elif artifact_dir.parent.name != ".harness":
        errors.append("Portable Contract directory must be under <project>/.harness/<slug>")
    elif Path(project_root).expanduser().resolve() != artifact_dir.parent.parent.resolve():
        errors.append("project_root does not match the opened contract directory")

    objective = contract.get("objective")
    if not isinstance(objective, dict):
        errors.append("objective must be an object")
    else:
        if not str(objective.get("goal") or "").strip():
            errors.append("objective.goal must be non-empty")
        done_when = objective.get("done_when")
        if not isinstance(done_when, list) or not any(str(item).strip() for item in done_when):
            errors.append("objective.done_when must contain at least one criterion")

    execution = contract.get("execution")
    if not isinstance(execution, dict):
        errors.append("execution must be an object")
    elif status not in PORTABLE_TERMINAL_STATUSES and not str(execution.get("next_action") or "").strip():
        errors.append("execution.next_action must be non-empty")

    ownership = contract.get("ownership")
    if not isinstance(ownership, dict) or not isinstance(ownership.get("owner"), dict):
        errors.append("ownership.owner must be an object")

    for key in ("decisions", "evidence"):
        if not isinstance(contract.get(key), list):
            errors.append(f"{key} must be a list")
    if not isinstance(contract.get("workspace"), dict):
        errors.append("workspace must be an object")
    if not isinstance(contract.get("capabilities"), dict):
        errors.append("capabilities must be an object")
    if not isinstance(contract.get("context"), dict):
        errors.append("context must be an object")
    if not isinstance(contract.get("extensions"), dict):
        errors.append("extensions must be an object")
    return errors


def validate_portable_contract_path(path: Path) -> list[str]:
    try:
        contract = load_object(path)
    except ValueError as exc:
        return [str(exc)]
    return portable_contract_errors(contract, path.parent)


def validate_portable_artifact_path(path: Path) -> list[str]:
    errors = validate_portable_contract_path(path)
    errors.extend(validate_jsonl(path.parent / "events.jsonl"))
    return errors


def portable_candidates(path: Path, selector: str = "") -> tuple[list[Path], list[str]]:
    target = path.expanduser().resolve()
    if target.is_file() and target.name == "contract.json":
        paths = [target]
    elif (target / "contract.json").is_file():
        paths = [target / "contract.json"]
    else:
        root = target / ".harness"
        paths = sorted(root.glob("*/contract.json")) if root.is_dir() else []

    active: list[Path] = []
    corrupt: list[str] = []
    for contract_path in paths:
        if selector and contract_path.parent.name != selector:
            continue
        errors = validate_portable_artifact_path(contract_path)
        if errors:
            corrupt.append(f"{contract_path.parent}: {'; '.join(errors)}")
            continue
        contract = load_object(contract_path)
        if str(contract.get("status") or "active") not in PORTABLE_TERMINAL_STATUSES:
            active.append(contract_path.parent.resolve())
    return active, corrupt


def select_portable_artifact(path: Path, selector: str = "", *, required: bool = True) -> Path | None:
    active, corrupt = portable_candidates(path, selector)
    if corrupt:
        raise ValueError("corrupt Portable Contract found: " + " | ".join(corrupt))
    if not active:
        if required:
            raise ValueError("no active Portable Contract found")
        return None
    if len(active) != 1:
        raise ValueError("multiple active Portable Contracts found: " + ", ".join(path.name for path in active))
    return active[0]


def portable_project_root(contract: dict[str, object]) -> Path:
    root = str(contract.get("project_root") or "").strip()
    if not root:
        raise ValueError("Portable Contract project_root is empty")
    return Path(root).expanduser().resolve()


def portable_list(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item).strip() for item in value if str(item).strip()]


def portable_capsule(
    contract: dict[str, object],
    *,
    workspace_drift: bool = False,
    changed_paths: list[str] | None = None,
    max_chars: int = DEFAULT_CAPSULE_MAX_CHARS,
) -> str:
    objective = contract.get("objective")
    execution = contract.get("execution")
    context = contract.get("context")
    capabilities = contract.get("capabilities")
    objective = objective if isinstance(objective, dict) else {}
    execution = execution if isinstance(execution, dict) else {}
    context = context if isinstance(context, dict) else {}
    capabilities = capabilities if isinstance(capabilities, dict) else {}

    def section(title: str, values: list[str]) -> list[str]:
        if not values:
            return []
        return [f"## {title}", "", *(f"- {value}" for value in values), ""]

    decisions = []
    for item in contract.get("decisions") or []:
        if not isinstance(item, dict):
            continue
        decision = str(item.get("decision") or "").strip()
        reason = str(item.get("reason") or "").strip()
        if decision:
            decisions.append(f"{decision} ({reason})" if reason else decision)

    evidence = []
    for item in contract.get("evidence") or []:
        if not isinstance(item, dict):
            continue
        path = str(item.get("path") or "").strip()
        digest = str(item.get("sha256") or "").strip()
        if path:
            evidence.append(f"{path} sha256:{digest[:12]}" if digest else path)

    must_read = portable_list(context.get("must_read"))
    read_if_needed = portable_list(context.get("read_if_needed"))
    if "events.jsonl" not in read_if_needed:
        read_if_needed.append("events.jsonl")

    lines = [
        "# Resume Capsule",
        "",
        f"Protocol: {PORTABLE_PROTOCOL}",
        f"Title: {str(contract.get('title') or '').strip()}",
        f"Status: {str(contract.get('status') or '').strip()}",
        f"Goal: {str(objective.get('goal') or '').strip()}",
        f"Current milestone: {str(execution.get('current_milestone') or '').strip() or 'not set'}",
        f"Next action: {str(execution.get('next_action') or '').strip() or 'none (terminal)'}",
        f"Workspace drift: {'yes' if workspace_drift else 'no'}",
        "",
    ]
    lines.extend(section("Done When", portable_list(objective.get("done_when"))))
    lines.extend(section("Non-Goals", portable_list(objective.get("non_goals"))))
    lines.extend(section("Constraints", portable_list(objective.get("constraints"))))
    lines.extend(section("Completed", portable_list(execution.get("completed"))))
    lines.extend(section("Pending Verification", portable_list(execution.get("pending_verification"))))
    lines.extend(section("Blockers", portable_list(execution.get("blockers"))))
    terminal_reason = str(execution.get("terminal_reason") or "").strip()
    lines.extend(section("Terminal Reason", [terminal_reason] if terminal_reason else []))
    lines.extend(section("Decisions", decisions))
    lines.extend(section("Changed Paths", changed_paths or []))
    lines.extend(section("Evidence", evidence))
    lines.extend(section("Required Capabilities", portable_list(capabilities.get("required"))))
    lines.extend(section("Optional Capabilities", portable_list(capabilities.get("optional"))))
    lines.extend(section("Must Read", must_read))
    lines.extend(section("Read If Needed", read_if_needed))
    capsule = "\n".join(lines).rstrip() + "\n"
    if len(capsule) > max_chars:
        raise ValueError(
            f"resume capsule is {len(capsule)} characters; reduce contract state below {max_chars} characters"
        )
    return capsule


def write_portable_capsule(
    artifact_dir: Path,
    contract: dict[str, object],
    *,
    workspace_drift: bool = False,
    changed_paths: list[str] | None = None,
    max_chars: int = DEFAULT_CAPSULE_MAX_CHARS,
) -> str:
    capsule = portable_capsule(
        contract,
        workspace_drift=workspace_drift,
        changed_paths=changed_paths,
        max_chars=max_chars,
    )
    (artifact_dir / "capsule.md").write_text(capsule, encoding="utf-8")
    return capsule


def write_portable_contract(artifact_dir: Path, expected: dict[str, object], value: dict[str, object]) -> None:
    errors = portable_contract_errors(value, artifact_dir)
    if errors:
        raise ValueError("invalid Portable Contract: " + "; ".join(errors))

    def update(current: dict[str, object]) -> dict[str, object]:
        if current != expected:
            raise ValueError("concurrent update detected: contract.json")
        return value

    mutate_json(artifact_dir / "contract.json", update, writer_role="manager", scope="global")


def portable_evidence(project_root: Path, value: str) -> dict[str, object]:
    candidate = Path(value).expanduser()
    resolved = candidate.resolve() if candidate.is_absolute() else (project_root / candidate).resolve()
    try:
        relative = resolved.relative_to(project_root).as_posix()
    except ValueError as exc:
        raise ValueError("portable evidence must remain inside the project root") from exc
    if not resolved.is_file() or resolved.stat().st_size <= 0:
        raise ValueError(f"portable evidence must be a non-empty regular file: {relative}")
    return {
        "path": relative,
        "sha256": sha256(resolved.read_bytes()),
        "size_bytes": resolved.stat().st_size,
    }


def validate_candidate(
    artifact_dir: Path,
    filename: str,
    value: dict[str, object],
    validator: Callable[[Path], list[str]],
) -> None:
    fd, name = tempfile.mkstemp(prefix=f".{filename}.", suffix=".json", dir=str(artifact_dir))
    path = Path(name)
    try:
        with open(fd, "w", encoding="utf-8", closefd=True) as handle:
            json.dump(value, handle, ensure_ascii=False, indent=2)
            handle.write("\n")
        errors = validator(path)
    finally:
        path.unlink(missing_ok=True)
    if errors:
        raise ValueError("; ".join(errors))


def append_unique(values: object, additions: list[str]) -> list[str]:
    result = [str(value).strip() for value in values if str(value).strip()] if isinstance(values, list) else []
    for addition in additions:
        normalized = addition.strip()
        if normalized and normalized not in result:
            result.append(normalized)
    return result


def append_unique_values(values: object, additions: list[object]) -> list[object]:
    result = list(values) if isinstance(values, list) else []
    fingerprints = {json.dumps(value, ensure_ascii=False, sort_keys=True) for value in result}
    for addition in additions:
        fingerprint = json.dumps(addition, ensure_ascii=False, sort_keys=True)
        if fingerprint not in fingerprints:
            result.append(addition)
            fingerprints.add(fingerprint)
    return result


def artifact_evidence_path(artifact_dir: Path, value: str) -> tuple[Path, str]:
    candidate = Path(value).expanduser()
    resolved = candidate.resolve() if candidate.is_absolute() else (artifact_dir / candidate).resolve()
    try:
        normalized = resolved.relative_to(artifact_dir).as_posix()
    except ValueError as exc:
        raise ValueError("evidence file must remain inside artifact directory") from exc
    if not resolved.exists() or not resolved.is_file() or resolved.stat().st_size <= 0:
        raise ValueError(f"evidence file must be a non-empty regular file: {normalized}")
    return resolved, normalized


def lesson_ledger_path(artifact_dir: Path) -> Path:
    return artifact_dir / "lessons.jsonl"


def validate_lesson_ledger(artifact_dir: Path) -> tuple[list[dict[str, object]], list[str]]:
    """Validate evidence-backed, append-only lesson records for a Full run."""
    path = lesson_ledger_path(artifact_dir)
    if not path.exists():
        state_path = artifact_dir / "run_state.json"
        if state_path.is_file():
            try:
                state = load_object(state_path)
            except ValueError:
                return [], []
            layers = state.get("state_layers")
            session = layers.get("session_state") if isinstance(layers, dict) else None
            paths = session.get("artifact_paths") if isinstance(session, dict) else None
            if isinstance(paths, dict) and paths.get("lessons") == "lessons.jsonl":
                return [], ["missing lessons.jsonl declared by run_state.json"]
        return [], []

    errors: list[str] = []
    content = path.read_text(encoding="utf-8")
    if content and not content.endswith("\n"):
        errors.append("lessons.jsonl: missing final newline")
    records: list[dict[str, object]] = []
    ids: set[str] = set()
    for line_number, line in enumerate(content.splitlines(), start=1):
        if not line.strip():
            continue
        try:
            record = json.loads(line)
        except json.JSONDecodeError as exc:
            errors.append(f"lessons.jsonl:{line_number}: invalid JSON: {exc}")
            continue
        if not isinstance(record, dict):
            errors.append(f"lessons.jsonl:{line_number}: record must be an object")
            continue
        prefix = f"lessons.jsonl:{line_number}"
        if record.get("schema_version") != 1:
            errors.append(f"{prefix}: schema_version must be 1")
        for key in ("id", "recorded_at", "source_case", "category", "symptom", "root_cause", "fix", "verification", "reusable_rule", "verified_by"):
            if not isinstance(record.get(key), str) or not str(record.get(key)).strip():
                errors.append(f"{prefix}: {key} must be a non-empty string")
        record_id = str(record.get("id") or "")
        if record_id in ids:
            errors.append(f"{prefix}: duplicate lesson id {record_id}")
        ids.add(record_id)
        if record.get("status") != "verified":
            errors.append(f"{prefix}: status must be verified")
        if record.get("verification_tier") not in VERIFICATION_TIERS:
            errors.append(f"{prefix}: verification_tier must be one of {', '.join(VERIFICATION_TIERS)}")
        evidence = record.get("evidence")
        if not isinstance(evidence, list) or not evidence:
            errors.append(f"{prefix}: evidence must be a non-empty array")
        else:
            for evidence_index, item in enumerate(evidence):
                if not isinstance(item, dict):
                    errors.append(f"{prefix}.evidence[{evidence_index}] must be an object")
                    continue
                try:
                    evidence_path, _ = artifact_evidence_path(artifact_dir, str(item.get("path") or ""))
                except ValueError as exc:
                    errors.append(f"{prefix}.evidence[{evidence_index}]: {exc}")
                    continue
                if item.get("sha256") != sha256(evidence_path.read_bytes()):
                    errors.append(f"{prefix}.evidence[{evidence_index}]: sha256 does not match evidence bytes")
        records.append(record)
    return records, errors


def validate_lesson_trace(artifact_dir: Path, records: list[dict[str, object]]) -> list[str]:
    trace_path = artifact_dir / "trace.jsonl"
    if not trace_path.exists() or not records:
        return []
    by_id = {str(record.get("id")): record for record in records}
    seen: set[str] = set()
    errors: list[str] = []
    for line_number, line in enumerate(trace_path.read_text(encoding="utf-8").splitlines(), start=1):
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            continue
        if not isinstance(event, dict) or event.get("event") != "lesson_recorded":
            continue
        lesson_id = str(event.get("lesson_id") or "")
        record = by_id.get(lesson_id)
        if record is None:
            errors.append(f"trace.jsonl:{line_number}: lesson_recorded references unknown lesson {lesson_id}")
            continue
        seen.add(lesson_id)
        line_bytes = (json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n").encode("utf-8")
        if event.get("lesson_sha256") != sha256(line_bytes):
            errors.append(f"trace.jsonl:{line_number}: lesson digest does not match lessons.jsonl")
    missing_events = sorted(set(by_id) - seen)
    if missing_events:
        errors.append("lessons.jsonl records missing lesson_recorded trace events: " + ", ".join(missing_events))
    return errors


def build_evidence_additions(
    artifact_dir: Path,
    *,
    subject: str,
    freeform: list[str],
    files: list[str],
    transaction_id: str,
    policy: object,
    verification_tier: str = "policy",
) -> list[object]:
    additions: list[object] = []
    for text in freeform:
        normalized = text.strip()
        if not normalized:
            continue
        if policy == EVIDENCE_POLICY:
            additions.append(
                {
                    "id": f"EV-{uuid.uuid4()}",
                    "type": "legacy_text",
                    "source_role": "manager",
                    "subject": subject,
                    "result": "info",
                    "payload": {"text": normalized},
                    "verification": {
                        "status": "unverified",
                        "method": "legacy_cli_text",
                        "verified_by": "",
                        "verified_at": "",
                        "transaction_id": transaction_id,
                    },
                }
            )
        else:
            additions.append(normalized)
    for value in files:
        path, normalized = artifact_evidence_path(artifact_dir, value)
        additions.append(
            {
                "id": f"EV-{uuid.uuid4()}",
                "type": "artifact_digest",
                "source_role": "manager",
                "subject": subject,
                "result": "pass",
                "verification_tier": verification_tier,
                "payload": {
                    "path": normalized,
                    "sha256": sha256(path.read_bytes()),
                    "size_bytes": path.stat().st_size,
                },
                "verification": {
                    "status": "verified",
                    "method": "hashed_by_harnessctl",
                    "verified_by": "harnessctl",
                    "verified_at": utc_now(),
                    "transaction_id": transaction_id,
                },
            }
        )
    return additions


def qualifying_evidence(
    values: list[object], subject: str, minimum_tier: str = "policy"
) -> list[dict[str, object]]:
    if minimum_tier not in VERIFICATION_TIERS:
        return []
    return [
        value for value in values
        if isinstance(value, dict)
        and value.get("type") in QUALIFYING_EVIDENCE_TYPES
        and value.get("subject") == subject
        and value.get("result") == "pass"
        and isinstance(value.get("verification"), dict)
        and value["verification"].get("status") == "verified"
        and value.get("verification_tier", "policy") in VERIFICATION_TIERS
        and VERIFICATION_TIERS.index(value.get("verification_tier", "policy"))
        >= VERIFICATION_TIERS.index(minimum_tier)
    ]


def reject_self_report(values: list[str]) -> None:
    pattern = re.compile(r"self[- ]?report|worker\s+says|worker.*done|自报|自称完成", re.IGNORECASE)
    if any(pattern.search(value) for value in values):
        raise ValueError("worker self-report cannot satisfy protected evidence")


def find_unique(items: object, item_id: str, label: str, *, key: str = "id") -> dict[str, object]:
    if not isinstance(items, list):
        raise ValueError(f"{label} list is missing")
    matches = [item for item in items if isinstance(item, dict) and item.get(key) == item_id]
    if len(matches) != 1:
        raise ValueError(f"{label} id not found or ambiguous: {item_id}")
    return matches[0]


def resolve_artifact_path(artifact_dir: Path, value: str, label: str, *, must_exist: bool) -> tuple[Path, str]:
    relative = Path(value)
    if relative.is_absolute() or ".." in relative.parts:
        raise ValueError(f"{label} must be a safe artifact-relative path")
    resolved = (artifact_dir / relative).resolve()
    try:
        normalized = resolved.relative_to(artifact_dir).as_posix()
    except ValueError as exc:
        raise ValueError(f"{label} escapes artifact directory") from exc
    if must_exist and (not resolved.exists() or not resolved.is_file()):
        raise ValueError(f"{label} must reference an existing file: {normalized}")
    return resolved, normalized


def state_witness_gate(
    artifact_dir: Path,
    state: dict[str, object],
    *,
    require_review: bool,
) -> list[str]:
    record = state.get("state_witness")
    if not isinstance(record, dict) or not record.get("required"):
        return []

    path_value = str(record.get("path") or "")
    try:
        witness_path, _ = resolve_artifact_path(artifact_dir, path_value, "state witness path", must_exist=True)
    except ValueError as exc:
        return [str(exc)]
    errors = validate_state_witness(witness_path, True)
    sealed_digest = str(record.get("sealed_digest") or "")
    if sealed_digest and sha256(witness_path.read_bytes()) != sealed_digest:
        errors.append("state witness changed after seal")
    if not require_review:
        return errors

    if record.get("review_status") != "pass":
        errors.append("state witness adversarial review must be pass")
    if not str(record.get("reviewer_id") or "").strip():
        errors.append("state witness reviewer_id must be recorded")
    required_tier = str(record.get("required_tier") or "policy")
    observed_tier = str(record.get("observed_tier") or "")
    if required_tier not in VERIFICATION_TIERS or observed_tier not in VERIFICATION_TIERS:
        errors.append("state witness observed_tier must reach a valid required_tier")
    elif VERIFICATION_TIERS.index(observed_tier) < VERIFICATION_TIERS.index(required_tier):
        errors.append(f"state witness tier {observed_tier} is below required {required_tier}")
    if not sealed_digest:
        errors.append("state witness must be sealed before protected acceptance")
    review_evidence = record.get("review_evidence")
    if not qualifying_evidence(
        review_evidence if isinstance(review_evidence, list) else [],
        "state_witness",
        required_tier,
    ):
        errors.append("state witness review requires qualifying evidence at the required tier")
    return errors


def has_state_seal(artifact_dir: Path) -> bool:
    trace_path = artifact_dir / "trace.jsonl"
    if not trace_path.is_file():
        return False
    for line in trace_path.read_text(encoding="utf-8").splitlines():
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(event, dict) and event.get("event") == "state_sealed":
            return True
    return False


def commit_transition(
    artifact_dir: Path,
    state_path: Path,
    expected: dict[str, object],
    value: dict[str, object],
    event: dict[str, object],
    *,
    transaction_id: str | None = None,
) -> None:
    trace_path = artifact_dir / "trace.jsonl"
    transaction_id = transaction_id or str(uuid.uuid4())
    journal = {
        **event,
        "transaction_id": transaction_id,
        "state_file": state_path.name,
        "before_sha256": sha256(state_path.read_bytes()),
        "after_sha256": sha256(serialized_json(value)),
    }
    started = {**journal, "event": f"{event['event']}_started", "ts": utc_now()}
    committed = {**journal, "ts": utc_now()}
    def guarded_update(current: dict[str, object]) -> dict[str, object]:
        if current != expected:
            raise ValueError(f"concurrent update detected: {state_path.name}")
        append_jsonl(trace_path, started, writer_role="manager", scope="global")
        return value

    mutate_json(state_path, guarded_update, writer_role="manager", scope="global")
    append_jsonl(trace_path, committed, writer_role="manager", scope="global")


def project_root_for_artifact(artifact_dir: Path) -> Path:
    resolved = artifact_dir.expanduser().resolve()
    if resolved.parent.name == "workspace":
        return resolved.parent.parent
    state_path = resolved / "run_state.json"
    if state_path.is_file():
        state = load_object(state_path)
        continuation = state.get("continuation")
        if isinstance(continuation, dict):
            checkpoint = continuation.get("checkpoint")
            repository = checkpoint.get("repository") if isinstance(checkpoint, dict) else None
            root = repository.get("root") if isinstance(repository, dict) else None
            if isinstance(root, str) and root.strip():
                return Path(root).expanduser().resolve()
    raise ValueError("artifact directory must be under <project>/workspace/<run>")


def validate_artifact_dir_binding(artifact_dir: Path) -> list[str]:
    """Ensure run_state points at the artifact directory the controller opened."""
    state_path = artifact_dir / "run_state.json"
    if not state_path.is_file():
        return ["missing canonical state file: run_state.json"]
    try:
        state = load_object(state_path)
    except ValueError as exc:
        return [str(exc)]
    recorded = state.get("artifact_dir")
    if not isinstance(recorded, str) or not recorded.strip():
        return ["run_state.json: artifact_dir must be a non-empty path"]
    recorded_path = Path(recorded).expanduser()
    if not recorded_path.is_absolute():
        try:
            recorded_path = project_root_for_artifact(artifact_dir) / recorded_path
        except ValueError as exc:
            return [f"run_state.json: cannot resolve relative artifact_dir: {exc}"]
    expected = artifact_dir.expanduser().resolve()
    observed = recorded_path.resolve()
    if observed != expected:
        return [
            "run_state.json: artifact_dir does not match opened artifact directory "
            f"(recorded {observed}; opened {expected})"
        ]
    return []


def repository_snapshot(project_root: Path) -> dict[str, object]:
    root = project_root.expanduser().resolve()

    def git(*args: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            ["git", "-C", str(root), *args],
            text=True,
            capture_output=True,
            check=False,
        )

    top = git("rev-parse", "--show-toplevel")
    if top.returncode != 0:
        return {
            "root": str(root),
            "cwd": str(root),
            "branch": "",
            "head": "",
            "dirty_paths": [],
            "dirty_entries": {},
            "worktree_digest": "",
        }
    repository_root = Path(top.stdout.strip()).resolve()
    branch = git("branch", "--show-current")
    head = git("rev-parse", "HEAD")
    status = git(
        "status",
        "--porcelain=v1",
        "--untracked-files=all",
        "--",
        ".",
        ":(exclude)workspace/**",
        ":(exclude).harness/**",
    )
    tracked = git(
        "diff",
        "--name-only",
        "--no-renames",
        "-z",
        "HEAD",
        "--",
        ".",
        ":(exclude)workspace/**",
        ":(exclude).harness/**",
    )
    diff = git(
        "diff",
        "--binary",
        "--no-ext-diff",
        "HEAD",
        "--",
        ".",
        ":(exclude)workspace/**",
        ":(exclude).harness/**",
    )
    fingerprint = hashlib.sha256()
    fingerprint.update(status.stdout.encode("utf-8", errors="surrogateescape"))
    fingerprint.update(diff.stdout.encode("utf-8", errors="surrogateescape"))
    untracked = git(
        "ls-files",
        "--others",
        "--exclude-standard",
        "-z",
        "--",
        ".",
        ":(exclude)workspace/**",
        ":(exclude).harness/**",
    )
    tracked_paths = {
        value for value in tracked.stdout.split("\0") if value
    } if tracked.returncode == 0 else set()
    untracked_paths = {
        value for value in untracked.stdout.split("\0") if value
    } if untracked.returncode == 0 else set()
    dirty_paths = sorted(tracked_paths | untracked_paths)
    dirty_entries: dict[str, str] = {}
    for value in dirty_paths:
        entry = hashlib.sha256()
        entry.update(value.encode("utf-8", errors="surrogateescape"))
        entry_diff = git(
            "diff",
            "--binary",
            "--no-ext-diff",
            "--no-renames",
            "HEAD",
            "--",
            value,
        )
        entry.update(entry_diff.stdout.encode("utf-8", errors="surrogateescape"))
        if value in untracked_paths:
            path = repository_root / value
            if path.is_symlink():
                entry.update(str(path.readlink()).encode("utf-8", errors="surrogateescape"))
            elif path.is_file():
                entry.update(path.read_bytes())
        dirty_entries[value] = entry.hexdigest()
    if untracked.returncode == 0:
        for value in sorted(untracked_paths):
            path = repository_root / value
            fingerprint.update(value.encode("utf-8", errors="surrogateescape"))
            if path.is_symlink():
                fingerprint.update(str(path.readlink()).encode("utf-8", errors="surrogateescape"))
            elif path.is_file():
                fingerprint.update(path.read_bytes())
    return {
        "root": str(repository_root),
        "cwd": str(root),
        "branch": branch.stdout.strip() if branch.returncode == 0 else "",
        "head": head.stdout.strip() if head.returncode == 0 else "",
        "dirty_paths": dirty_paths,
        "dirty_entries": dirty_entries,
        "worktree_digest": fingerprint.hexdigest(),
    }


def derive_next_task(state: dict[str, object]) -> tuple[str, str]:
    layers = state.get("state_layers")
    working = layers.get("working_state") if isinstance(layers, dict) else None
    current_task = str(working.get("current_task") or "") if isinstance(working, dict) else ""
    tasks = state.get("tasks")
    task_items = [item for item in tasks if isinstance(item, dict)] if isinstance(tasks, list) else []
    task = next((item for item in task_items if str(item.get("id")) == current_task), None)
    if task is None:
        task = next(
            (
                item
                for item in task_items
                if item.get("status") not in {"passed", "merged", "cancelled"}
            ),
            None,
        )
    if task is None:
        return "", "Inspect task_spec.md and define the next ready task"
    task_id = str(task.get("id") or "")
    task_path = str(task.get("task_path") or "task_spec.md")
    task_name = str(task.get("name") or "unnamed task")
    return task_id, f"Read {task_path} and continue task {task_id}: {task_name}"


def legacy_continuation(state: dict[str, object], project_root: Path) -> dict[str, object]:
    current_task, next_action = derive_next_task(state)
    return {
        "protocol": CONTINUATION_PROTOCOL,
        "status": "unclaimed",
        "owner": {"actor_id": "", "runtime": "", "epoch": 0, "claimed_at": ""},
        "previous_owner": {},
        "takeover_count": 0,
        "checkpoint": {
            "id": "",
            "sequence": 0,
            "checkpointed_at": str(state.get("updated_at") or state.get("created_at") or ""),
            "actor_id": "",
            "runtime": "",
            "reason": "legacy artifact upgraded during resume",
            "current_task": current_task,
            "next_action": next_action,
            "pending_verification": [],
            "repository": {
                "root": str(project_root),
                "cwd": str(project_root),
                "branch": "",
                "head": "",
                "dirty_paths": [],
                "dirty_entries": {},
                "worktree_digest": "",
            },
        },
        "last_resume": {
            "resumed_at": "",
            "actor_id": "",
            "runtime": "",
            "takeover_reason": "",
            "forced": False,
        },
    }


def continuation_record(
    state: dict[str, object], project_root: Path
) -> tuple[dict[str, object], bool]:
    value = state.get("continuation")
    if isinstance(value, dict):
        return value, False
    value = legacy_continuation(state, project_root)
    state["continuation"] = value
    return value, True


def validate_actor(value: str, label: str) -> str:
    normalized = value.strip()
    if not normalized or any(ord(character) < 32 for character in normalized):
        raise ValueError(f"{label} must be a non-empty string without control characters")
    return normalized


def require_current_owner(
    state: dict[str, object], actor_id: str, owner_epoch: int | None
) -> None:
    continuation = state.get("continuation")
    owner = continuation.get("owner") if isinstance(continuation, dict) else None
    current = str(owner.get("actor_id") or "") if isinstance(owner, dict) else ""
    if not current:
        return
    actor = actor_id.strip()
    if actor != current:
        raise PermissionError(
            f"current owner is {current!r}; --actor-id must match before mutating this run"
        )
    current_epoch = int(owner.get("epoch") or 0)
    if owner_epoch != current_epoch:
        raise PermissionError(
            f"current owner epoch is {current_epoch}; --owner-epoch must match before mutating this run"
        )


def discover_active_runs(path: Path, selector: str = "") -> dict[str, object]:
    target = path.expanduser().resolve()
    if target.is_file() and target.name == "run_state.json":
        state_paths = [target]
    elif (target / "run_state.json").is_file():
        state_paths = [target / "run_state.json"]
    else:
        workspace = target / "workspace"
        state_paths = sorted(workspace.glob("*/run_state.json")) if workspace.is_dir() else []

    active: list[dict[str, object]] = []
    terminal: list[dict[str, object]] = []
    corrupt: list[dict[str, str]] = []
    for state_path in state_paths:
        if selector and state_path.parent.name != selector:
            continue
        try:
            state = load_object(state_path)
        except ValueError as exc:
            corrupt.append({"artifact_dir": str(state_path.parent.resolve()), "error": str(exc)})
            continue
        if not is_audited_mode(state.get("mode") or "full"):
            continue
        item = {
            "artifact_dir": str(state_path.parent.resolve()),
            "slug": state_path.parent.name,
            "title": str(state.get("title") or ""),
            "status": str(state.get("status") or ""),
            "updated_at": str(state.get("updated_at") or ""),
        }
        if item["status"] in TERMINAL_RUN_STATUSES:
            terminal.append(item)
        else:
            active.append(item)
    return {
        "project_or_artifact": str(target),
        "active_count": len(active),
        "runs": active,
        "terminal_count": len(terminal),
        "terminal_runs": terminal,
        "corrupt": corrupt,
    }


def select_unique_active_run(path: Path, selector: str = "") -> Path:
    discovered = discover_active_runs(path, selector)
    corrupt = discovered["corrupt"]
    if corrupt:
        locations = ", ".join(str(item["artifact_dir"]) for item in corrupt)
        raise ValueError(f"corrupt Audited/legacy Full run state found: {locations}")
    runs = discovered["runs"]
    if not isinstance(runs, list) or not runs:
        raise ValueError("no active Audited or legacy Full run found")
    if len(runs) != 1:
        names = ", ".join(str(item.get("slug")) for item in runs if isinstance(item, dict))
        raise ValueError(f"multiple active Audited/legacy Full runs found: {names}")
    return Path(str(runs[0]["artifact_dir"])).resolve()


def select_active_protocol_artifact(path: Path, selector: str = "") -> tuple[str, Path]:
    portable, portable_corrupt = portable_candidates(path, selector)
    discovered = discover_active_runs(path, selector)
    audited_corrupt = discovered["corrupt"]
    if portable_corrupt or audited_corrupt:
        details = list(portable_corrupt)
        details.extend(
            f"{item['artifact_dir']}: {item['error']}"
            for item in audited_corrupt
            if isinstance(item, dict)
        )
        raise ValueError("corrupt harness state found: " + " | ".join(details))

    audited = discovered["runs"]
    audited = audited if isinstance(audited, list) else []
    if len(portable) > 1:
        names = ", ".join(item.name for item in portable)
        raise ValueError(f"multiple active Portable Contracts found: {names}")
    if len(audited) > 1:
        names = ", ".join(
            str(item.get("slug")) for item in audited if isinstance(item, dict)
        )
        raise ValueError(f"multiple active Audited/legacy Full runs found: {names}")
    if portable and audited:
        audited_path = str(audited[0].get("artifact_dir")) if isinstance(audited[0], dict) else "unknown"
        raise ValueError(
            "ambiguous active harness protocols: Portable "
            f"{portable[0]} and Audited/legacy Full {audited_path}; pass an explicit artifact path"
        )
    if portable:
        return "portable", portable[0]
    if audited and isinstance(audited[0], dict):
        return "audited", Path(str(audited[0]["artifact_dir"])).resolve()
    raise ValueError("no active Portable or Audited Harness run found")


def changed_repository_paths(
    before: dict[str, object], after: dict[str, object]
) -> tuple[bool, list[str]]:
    before_paths = {str(item) for item in before.get("dirty_paths", [])} if isinstance(before.get("dirty_paths"), list) else set()
    after_paths = {str(item) for item in after.get("dirty_paths", [])} if isinstance(after.get("dirty_paths"), list) else set()
    before_digest = str(before.get("worktree_digest") or "")
    after_digest = str(after.get("worktree_digest") or "")
    before_entries = before.get("dirty_entries")
    after_entries = after.get("dirty_entries")
    if isinstance(before_entries, dict) and isinstance(after_entries, dict):
        changed = sorted(
            path
            for path in set(before_entries) | set(after_entries)
            if before_entries.get(path) != after_entries.get(path)
        )
        worktree_drift = bool(changed)
    elif before_digest and after_digest:
        worktree_drift = before_digest != after_digest
        changed = sorted(before_paths | after_paths) if worktree_drift else []
    else:
        worktree_drift = before_paths != after_paths
        changed = sorted(before_paths | after_paths) if worktree_drift else []
    metadata_drift = any(before.get(key) != after.get(key) for key in ("root", "branch", "head"))
    drift = worktree_drift or metadata_drift
    return drift, changed


def portable_slug(value: str) -> str:
    slug = re.sub(r"[^a-z0-9\u4e00-\u9fff]+", "-", value.strip().casefold()).strip("-")
    return slug or "portable-task"


def materialize_portable(args: argparse.Namespace) -> int:
    project_root = args.project_root.expanduser().resolve()
    if not project_root.is_dir():
        raise ValueError(f"project root is not a directory: {project_root}")
    slug = portable_slug(args.slug or args.title)
    artifact_dir = project_root / ".harness" / slug
    if artifact_dir.exists():
        raise ValueError(f"portable artifact already exists: {artifact_dir}")

    now = utc_now()
    artifact_dir.mkdir(parents=True)
    contract: dict[str, object] = {
        "schema_version": PORTABLE_SCHEMA_VERSION,
        "protocol": PORTABLE_PROTOCOL,
        "mode": "portable",
        "id": str(uuid.uuid4()),
        "title": args.title.strip(),
        "artifact_dir": str(artifact_dir),
        "project_root": str(project_root),
        "created_at": now,
        "updated_at": now,
        "status": "active",
        "objective": {
            "goal": args.goal.strip(),
            "done_when": list(dict.fromkeys(item.strip() for item in args.done_when if item.strip())),
            "non_goals": list(dict.fromkeys(item.strip() for item in args.non_goal if item.strip())),
            "constraints": list(dict.fromkeys(item.strip() for item in args.constraint if item.strip())),
        },
        "execution": {
            "current_milestone": args.current_milestone.strip(),
            "completed": [],
            "next_action": args.next_action.strip(),
            "pending_verification": [],
            "blockers": [],
        },
        "decisions": [],
        "workspace": {
            "checkpoint": repository_snapshot(project_root),
        },
        "ownership": {
            "status": "unclaimed",
            "owner": {"actor_id": "", "runtime": "", "epoch": 0, "claimed_at": ""},
            "previous_owner": {},
            "takeover_count": 0,
        },
        "evidence": [],
        "capabilities": {
            "required": list(dict.fromkeys(args.required_capability or ["filesystem"])),
            "optional": list(dict.fromkeys(args.optional_capability)),
        },
        "context": {
            "must_read": list(dict.fromkeys(args.must_read)),
            "read_if_needed": list(dict.fromkeys(args.read_if_needed or ["events.jsonl"])),
        },
        "extensions": {},
    }
    errors = portable_contract_errors(contract, artifact_dir)
    if errors:
        shutil.rmtree(artifact_dir)
        raise ValueError("invalid Portable Contract: " + "; ".join(errors))
    (artifact_dir / "contract.json").write_text(
        json.dumps(contract, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    append_jsonl(
        artifact_dir / "events.jsonl",
        {
            "event": "portable_materialized",
            "protocol": PORTABLE_PROTOCOL,
            "ts": now,
            "contract_sha256": sha256(serialized_json(contract)),
        },
        writer_role="manager",
        scope="global",
    )
    write_portable_capsule(artifact_dir, contract, max_chars=args.max_chars)
    print(
        json.dumps(
            {
                "artifact_dir": str(artifact_dir),
                "capsule_path": str(artifact_dir / "capsule.md"),
                "contract_path": str(artifact_dir / "contract.json"),
                "mode": "portable",
                "protocol": PORTABLE_PROTOCOL,
            },
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        )
    )
    return 0


def portable_owner(contract: dict[str, object]) -> tuple[dict[str, object], dict[str, object]]:
    ownership = contract.get("ownership")
    if not isinstance(ownership, dict):
        raise ValueError("Portable Contract ownership is invalid")
    owner = ownership.get("owner")
    if not isinstance(owner, dict):
        raise ValueError("Portable Contract owner is invalid")
    return ownership, owner


def require_portable_owner(owner: dict[str, object], actor_id: str, owner_epoch: int | None) -> None:
    if str(owner.get("actor_id") or "") != actor_id:
        raise ValueError("current Portable Contract owner does not match --actor-id")
    epoch = int(owner.get("epoch") or 0)
    if owner_epoch is None or owner_epoch != epoch:
        raise ValueError(f"stale Portable Contract owner epoch; expected {epoch}")


def portable_checkpoint(args: argparse.Namespace, artifact_dir: Path) -> int:
    with locked(artifact_dir / ".portable"):
        contract = load_object(artifact_dir / "contract.json")
        errors = portable_contract_errors(contract, artifact_dir)
        if errors:
            raise ValueError("invalid Portable Contract: " + "; ".join(errors))
        original = deepcopy(contract)
        project_root = portable_project_root(contract)
        actor_id = validate_actor(args.actor_id, "actor id")
        runtime = validate_actor(args.runtime.casefold(), "runtime")
        ownership, owner = portable_owner(contract)
        if str(owner.get("actor_id") or ""):
            require_portable_owner(owner, actor_id, args.owner_epoch)
            if str(owner.get("runtime") or "") != runtime:
                raise ValueError("checkpoint runtime must match the current Portable Contract owner runtime")
        else:
            owner.update(
                {
                    "actor_id": actor_id,
                    "runtime": runtime,
                    "epoch": 1,
                    "claimed_at": utc_now(),
                }
            )

        execution = contract.get("execution")
        if not isinstance(execution, dict):
            raise ValueError("Portable Contract execution is invalid")
        next_action = args.next_action.strip()
        reason = args.reason.strip()
        if not next_action or not reason:
            raise ValueError("checkpoint requires non-empty --next-action and --reason")
        execution["next_action"] = next_action
        if args.current_task.strip():
            execution["current_milestone"] = args.current_task.strip()
        execution["completed"] = append_unique(execution.get("completed"), args.completed)
        blockers = portable_list(execution.get("blockers"))
        for resolved in args.resolve_blocker:
            normalized = resolved.strip()
            if normalized not in blockers:
                raise ValueError(f"cannot resolve unknown blocker: {normalized}")
            blockers.remove(normalized)
        execution["blockers"] = append_unique(blockers, args.blocker)
        if args.clear_pending_verification and args.pending_verification:
            raise ValueError("cannot combine --clear-pending-verification with --pending-verification")
        if args.clear_pending_verification:
            execution["pending_verification"] = []
        elif args.pending_verification:
            execution["pending_verification"] = list(dict.fromkeys(args.pending_verification))

        if args.decision or args.decision_reason:
            if not args.decision.strip() or not args.decision_reason.strip():
                raise ValueError("--decision and --decision-reason must be provided together")
            contract["decisions"] = append_unique_values(
                contract.get("decisions"),
                [
                    {
                        "decision": args.decision.strip(),
                        "reason": args.decision_reason.strip(),
                        "recorded_at": utc_now(),
                    }
                ],
            )

        additions = [portable_evidence(project_root, value) for value in args.evidence_file]
        contract["evidence"] = append_unique_values(contract.get("evidence"), additions)
        contract["workspace"] = {"checkpoint": repository_snapshot(project_root)}
        ownership["status"] = "active"
        contract["status"] = "active"
        contract["updated_at"] = utc_now()
        write_portable_contract(artifact_dir, original, contract)
        append_jsonl(
            artifact_dir / "events.jsonl",
            {
                "event": "portable_checkpoint",
                "ts": contract["updated_at"],
                "actor_id": actor_id,
                "runtime": runtime,
                "next_action": next_action,
                "reason": reason,
                "evidence_paths": [item["path"] for item in additions],
            },
            writer_role="manager",
            scope="global",
        )
        write_portable_capsule(artifact_dir, contract, max_chars=args.max_chars)
        print(
            json.dumps(
                {
                    "artifact_dir": str(artifact_dir),
                    "mode": "portable",
                    "owner": owner,
                    "next_action": next_action,
                },
                ensure_ascii=False,
                indent=2,
                sort_keys=True,
            )
        )
    return 0


def portable_handoff(args: argparse.Namespace, artifact_dir: Path) -> int:
    with locked(artifact_dir / ".portable"):
        contract = load_object(artifact_dir / "contract.json")
        errors = portable_contract_errors(contract, artifact_dir)
        if errors:
            raise ValueError("invalid Portable Contract: " + "; ".join(errors))
        original = deepcopy(contract)
        ownership, owner = portable_owner(contract)
        actor_id = validate_actor(args.actor_id, "actor id")
        require_portable_owner(owner, actor_id, args.owner_epoch)
        next_action = args.next_action.strip()
        reason = args.reason.strip()
        if not next_action or not reason:
            raise ValueError("handoff requires non-empty --next-action and --reason")
        execution = contract.get("execution")
        if not isinstance(execution, dict):
            raise ValueError("Portable Contract execution is invalid")
        execution["next_action"] = next_action
        if args.pending_verification:
            execution["pending_verification"] = list(dict.fromkeys(args.pending_verification))
        contract["workspace"] = {"checkpoint": repository_snapshot(portable_project_root(contract))}
        ownership["status"] = "ready"
        contract["updated_at"] = utc_now()
        write_portable_contract(artifact_dir, original, contract)
        append_jsonl(
            artifact_dir / "events.jsonl",
            {
                "event": "portable_handoff",
                "ts": contract["updated_at"],
                "actor_id": actor_id,
                "runtime": owner.get("runtime"),
                "next_action": next_action,
                "reason": reason,
            },
            writer_role="manager",
            scope="global",
        )
        write_portable_capsule(artifact_dir, contract)
        print(
            json.dumps(
                {
                    "artifact_dir": str(artifact_dir),
                    "mode": "portable",
                    "owner": owner,
                    "status": "ready",
                    "next_action": next_action,
                },
                ensure_ascii=False,
                indent=2,
                sort_keys=True,
            )
        )
    return 0


def close_portable(args: argparse.Namespace) -> int:
    artifact_dir = select_portable_artifact(args.path, args.run)
    assert artifact_dir is not None
    with locked(artifact_dir / ".portable"):
        contract = load_object(artifact_dir / "contract.json")
        errors = validate_portable_artifact_path(artifact_dir / "contract.json")
        if errors:
            raise ValueError("invalid Portable Contract: " + "; ".join(errors))
        original = deepcopy(contract)
        ownership, owner = portable_owner(contract)
        actor_id = validate_actor(args.actor_id, "actor id")
        require_portable_owner(owner, actor_id, args.owner_epoch)
        reason = args.reason.strip()
        if not reason:
            raise ValueError("close requires a non-empty --reason")

        project_root = portable_project_root(contract)
        additions = [portable_evidence(project_root, value) for value in args.evidence_file]
        contract["evidence"] = append_unique_values(contract.get("evidence"), additions)
        execution = contract.get("execution")
        if not isinstance(execution, dict):
            raise ValueError("Portable Contract execution is invalid")
        if args.status == "accepted":
            blockers = portable_list(execution.get("blockers"))
            pending = portable_list(execution.get("pending_verification"))
            if blockers:
                raise ValueError("accepted Portable Contract cannot have blockers")
            if pending:
                raise ValueError("accepted Portable Contract cannot have pending verification")
            if not contract["evidence"]:
                raise ValueError("accepted Portable Contract requires evidence")

        now = utc_now()
        contract["status"] = args.status
        contract["updated_at"] = now
        contract["workspace"] = {"checkpoint": repository_snapshot(project_root)}
        execution["next_action"] = ""
        execution["terminal_reason"] = reason
        ownership["status"] = "closed"
        write_portable_contract(artifact_dir, original, contract)
        append_jsonl(
            artifact_dir / "events.jsonl",
            {
                "event": "portable_closed",
                "ts": now,
                "actor_id": actor_id,
                "runtime": owner.get("runtime"),
                "status": args.status,
                "reason": reason,
                "evidence_paths": [item["path"] for item in additions],
                "contract_sha256": sha256(serialized_json(contract)),
            },
            writer_role="manager",
            scope="global",
        )
        write_portable_capsule(artifact_dir, contract)
        print(
            json.dumps(
                {
                    "artifact_dir": str(artifact_dir),
                    "mode": "portable",
                    "status": args.status,
                    "reason": reason,
                },
                ensure_ascii=False,
                indent=2,
                sort_keys=True,
            )
        )
    return 0


def portable_resume(args: argparse.Namespace, artifact_dir: Path) -> int:
    project_root = portable_project_root(load_object(artifact_dir / "contract.json"))
    with locked(project_root / ".harness" / ".resume"):
        with locked(artifact_dir / ".portable"):
            contract = load_object(artifact_dir / "contract.json")
            errors = portable_contract_errors(contract, artifact_dir)
            if errors:
                raise ValueError("invalid Portable Contract: " + "; ".join(errors))
            original = deepcopy(contract)
            ownership, owner = portable_owner(contract)
            actor_id = validate_actor(args.actor_id, "actor id")
            runtime = validate_actor(args.runtime.casefold(), "runtime")
            previous_owner = deepcopy(owner) if str(owner.get("actor_id") or "") else {}
            same_owner = (
                str(owner.get("actor_id") or "") == actor_id
                and str(owner.get("runtime") or "") == runtime
            )
            if same_owner:
                require_portable_owner(owner, actor_id, args.owner_epoch)
            forced = ownership.get("status") == "active" and bool(previous_owner) and not same_owner
            takeover_reason = args.takeover_reason.strip()
            if forced and not takeover_reason:
                raise ValueError("active owner takeover requires a non-empty takeover reason (--takeover-reason)")
            if not same_owner:
                old_epoch = int(owner.get("epoch") or 0)
                ownership["previous_owner"] = previous_owner
                ownership["owner"] = {
                    "actor_id": actor_id,
                    "runtime": runtime,
                    "epoch": old_epoch + 1,
                    "claimed_at": utc_now(),
                }
                owner = ownership["owner"]
                if previous_owner:
                    ownership["takeover_count"] = int(ownership.get("takeover_count") or 0) + 1
            ownership["status"] = "active"
            contract["updated_at"] = utc_now()

            checkpoint = contract.get("workspace")
            checkpoint = checkpoint.get("checkpoint") if isinstance(checkpoint, dict) else {}
            checkpoint = checkpoint if isinstance(checkpoint, dict) else {}
            current_repository = repository_snapshot(project_root)
            workspace_drift, changed_paths = changed_repository_paths(checkpoint, current_repository)
            execution = contract.get("execution")
            next_action = str(execution.get("next_action") or "") if isinstance(execution, dict) else ""
            projected_next_action = (
                f"Reconcile workspace drift before continuing: {next_action}"
                if workspace_drift
                else next_action
            )
            write_portable_contract(artifact_dir, original, contract)
            append_jsonl(
                artifact_dir / "events.jsonl",
                {
                    "event": "portable_resume",
                    "ts": contract["updated_at"],
                    "previous_owner": previous_owner,
                    "owner": owner,
                    "forced": forced,
                    "takeover_reason": takeover_reason,
                    "workspace_drift": workspace_drift,
                },
                writer_role="manager",
                scope="global",
            )
            capsule = write_portable_capsule(
                artifact_dir,
                contract,
                workspace_drift=workspace_drift,
                changed_paths=changed_paths,
            )
            context = contract.get("context")
            context = context if isinstance(context, dict) else {}
            capabilities = contract.get("capabilities")
            capabilities = capabilities if isinstance(capabilities, dict) else {}
            must_read = ["capsule.md", *portable_list(context.get("must_read"))]
            read_if_needed = portable_list(context.get("read_if_needed"))
            if "events.jsonl" not in read_if_needed:
                read_if_needed.append("events.jsonl")
            packet = {
                "protocol": PORTABLE_PROTOCOL,
                "artifact_dir": str(artifact_dir),
                "project_root": str(project_root),
                "capsule_path": str(artifact_dir / "capsule.md"),
                "capsule": capsule,
                "next_action": projected_next_action,
                "must_read": list(dict.fromkeys(must_read)),
                "read_if_needed": list(dict.fromkeys(read_if_needed)),
                "required_capabilities": portable_list(capabilities.get("required")),
                "optional_capabilities": portable_list(capabilities.get("optional")),
                "owner": owner,
                "previous_owner": previous_owner,
                "forced_takeover": forced,
                "workspace_drift": workspace_drift,
                "changed_paths": changed_paths,
                "integrity": "pass",
            }
            print(json.dumps(packet, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


def pack_portable(args: argparse.Namespace) -> int:
    artifact_dir = select_portable_artifact(args.path, args.run)
    assert artifact_dir is not None
    contract = load_object(artifact_dir / "contract.json")
    errors = portable_contract_errors(contract, artifact_dir)
    if errors:
        raise ValueError("invalid Portable Contract: " + "; ".join(errors))
    capsule = write_portable_capsule(artifact_dir, contract, max_chars=args.max_chars)
    print(
        json.dumps(
            {
                "artifact_dir": str(artifact_dir),
                "capsule_path": str(artifact_dir / "capsule.md"),
                "capsule_chars": len(capsule),
                "max_chars": args.max_chars,
            },
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        )
    )
    return 0


def build_resume_packet(
    artifact_dir: Path,
    state: dict[str, object],
    *,
    current_repository: dict[str, object],
    legacy_upgrade: bool,
    forced_takeover: bool,
) -> dict[str, object]:
    continuation = state["continuation"]
    checkpoint = continuation["checkpoint"]
    checkpoint_repository = checkpoint.get("repository")
    if not isinstance(checkpoint_repository, dict):
        checkpoint_repository = {}
    workspace_drift = False
    changed_paths: list[str] = []
    if int(checkpoint.get("sequence") or 0) > 0:
        workspace_drift, changed_paths = changed_repository_paths(
            checkpoint_repository,
            current_repository,
        )

    tasks = state.get("tasks")
    task_items = [item for item in tasks if isinstance(item, dict)] if isinstance(tasks, list) else []
    active_tasks = [
        {
            "id": str(item.get("id") or ""),
            "name": str(item.get("name") or ""),
            "status": str(item.get("status") or ""),
            "task_path": str(item.get("task_path") or ""),
            "report_path": str(item.get("report_path") or ""),
        }
        for item in task_items
        if item.get("status") not in {"passed", "merged", "cancelled"}
    ]
    blockers = [
        f"{item.get('id')}: {item.get('stop_reason') or item.get('status')}"
        for item in task_items
        if item.get("status") in {"blocked", "verify_failed"}
    ]
    layers = state.get("state_layers")
    working = layers.get("working_state") if isinstance(layers, dict) else None
    if isinstance(working, dict) and isinstance(working.get("active_blockers"), list):
        blockers.extend(str(item) for item in working["active_blockers"] if str(item).strip())
    session = layers.get("session_state") if isinstance(layers, dict) else None
    artifact_paths = session.get("artifact_paths") if isinstance(session, dict) else None
    required_reads = []
    if isinstance(artifact_paths, dict):
        required_reads.extend(str(value) for value in artifact_paths.values() if str(value).strip())
    current_task = str(checkpoint.get("current_task") or "")
    current = next((item for item in active_tasks if item["id"] == current_task), None)
    if current:
        required_reads.extend(
            value for value in (current["task_path"], current["report_path"]) if value
        )
    candidate_reads = list(dict.fromkeys(required_reads))
    required_reads = [
        value for value in candidate_reads if (artifact_dir / value).is_file()
    ]
    missing_required_reads = [
        value for value in candidate_reads if not (artifact_dir / value).is_file()
    ]
    next_action = str(checkpoint.get("next_action") or "").strip()
    next_verification = next_action
    if workspace_drift:
        next_verification = (
            "Inspect and reconcile post-checkpoint workspace drift before continuing: "
            + next_action
        )
    return {
        "protocol": CONTINUATION_PROTOCOL,
        "artifact_dir": str(artifact_dir),
        "project_root": str(project_root_for_artifact(artifact_dir)),
        "run_status": str(state.get("status") or ""),
        "current_stage": str(state.get("current_stage") or ""),
        "current_task": current_task,
        "recorded_next_action": next_action,
        "next_verification": next_verification,
        "pending_verification": list(checkpoint.get("pending_verification") or []),
        "active_tasks": active_tasks,
        "blockers": blockers,
        "required_reads": required_reads,
        "missing_required_reads": missing_required_reads,
        "owner": deepcopy(continuation["owner"]),
        "previous_owner": deepcopy(continuation.get("previous_owner") or {}),
        "forced_takeover": forced_takeover,
        "legacy_upgrade": legacy_upgrade,
        "workspace_drift": workspace_drift,
        "changed_paths": changed_paths,
        "checkpoint_repository": checkpoint_repository,
        "current_repository": current_repository,
        "integrity": "pass",
    }


def discover_runs(args: argparse.Namespace) -> int:
    payload = discover_active_runs(args.path, args.run)
    print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))
    return 1 if payload["corrupt"] else 0


def checkpoint_run(args: argparse.Namespace) -> int:
    protocol, artifact_dir = select_active_protocol_artifact(args.path, args.run)
    if protocol == "portable":
        return portable_checkpoint(args, artifact_dir)
    with locked(artifact_dir / ".harnessctl"):
        ensure_trace_integrity(artifact_dir)
        state_path = artifact_dir / "run_state.json"
        state = load_object(state_path)
        original_state = deepcopy(state)
        current_errors = validate_run_state(state_path)
        if current_errors:
            raise ValueError("current run_state is invalid: " + "; ".join(current_errors))
        project_root = project_root_for_artifact(artifact_dir)
        continuation, legacy_upgrade = continuation_record(state, project_root)
        actor_id = validate_actor(args.actor_id, "actor id")
        runtime = validate_actor(args.runtime.casefold(), "runtime")
        owner = continuation.get("owner")
        if not isinstance(owner, dict):
            raise ValueError("continuation owner is invalid")
        if str(owner.get("actor_id") or ""):
            require_current_owner(state, actor_id, args.owner_epoch)
            if str(owner.get("runtime") or "") != runtime:
                raise ValueError("checkpoint runtime must match the current owner runtime")
        else:
            owner.update(
                {
                    "actor_id": actor_id,
                    "runtime": runtime,
                    "epoch": 1,
                    "claimed_at": utc_now(),
                }
            )

        checkpoint = continuation.get("checkpoint")
        if not isinstance(checkpoint, dict):
            raise ValueError("continuation checkpoint is invalid")
        next_action = args.next_action.strip()
        reason = args.reason.strip()
        if not next_action or not reason:
            raise ValueError("checkpoint requires non-empty --next-action and --reason")
        current_task = args.current_task.strip() or str(checkpoint.get("current_task") or "")
        now = utc_now()
        pending_verification = (
            list(dict.fromkeys(args.pending_verification))
            if args.pending_verification
            else list(checkpoint.get("pending_verification") or [])
        )
        checkpoint.update(
            {
                "id": str(uuid.uuid4()),
                "sequence": int(checkpoint.get("sequence") or 0) + 1,
                "checkpointed_at": now,
                "actor_id": actor_id,
                "runtime": runtime,
                "reason": reason,
                "current_task": current_task,
                "next_action": next_action,
                "pending_verification": pending_verification,
                "repository": repository_snapshot(project_root),
            }
        )
        continuation["status"] = "active"
        layers = state.get("state_layers")
        working = layers.get("working_state") if isinstance(layers, dict) else None
        if isinstance(working, dict):
            working["current_task"] = current_task
            working["updated_at"] = now
        state["updated_at"] = now
        validate_candidate(artifact_dir, "run_state.json", state, validate_run_state)
        commit_transition(
            artifact_dir,
            state_path,
            original_state,
            state,
            {
                "event": "continuation_checkpoint",
                "actor_id": actor_id,
                "runtime": runtime,
                "checkpoint_id": checkpoint["id"],
                "sequence": checkpoint["sequence"],
                "current_task": current_task,
                "next_action": next_action,
                "reason": reason,
                "legacy_upgrade": legacy_upgrade,
            },
        )
        print(
            json.dumps(
                {
                    "artifact_dir": str(artifact_dir),
                    "checkpoint_id": checkpoint["id"],
                    "sequence": checkpoint["sequence"],
                    "owner": owner,
                    "next_action": next_action,
                },
                ensure_ascii=False,
                indent=2,
                sort_keys=True,
            )
        )
    return 0


def handoff_run(args: argparse.Namespace) -> int:
    protocol, artifact_dir = select_active_protocol_artifact(args.path, args.run)
    if protocol == "portable":
        return portable_handoff(args, artifact_dir)
    with locked(artifact_dir / ".harnessctl"):
        ensure_trace_integrity(artifact_dir)
        state_path = artifact_dir / "run_state.json"
        state = load_object(state_path)
        original_state = deepcopy(state)
        project_root = project_root_for_artifact(artifact_dir)
        continuation, _ = continuation_record(state, project_root)
        actor_id = validate_actor(args.actor_id, "actor id")
        require_current_owner(state, actor_id, args.owner_epoch)
        owner = continuation.get("owner")
        if not isinstance(owner, dict) or not str(owner.get("actor_id") or ""):
            raise ValueError("handoff requires an acquired continuation owner; checkpoint first")
        checkpoint = continuation.get("checkpoint")
        if not isinstance(checkpoint, dict):
            raise ValueError("continuation checkpoint is invalid")
        reason = args.reason.strip()
        next_action = args.next_action.strip()
        if not reason or not next_action:
            raise ValueError("handoff requires non-empty --reason and --next-action")
        now = utc_now()
        pending_verification = (
            list(dict.fromkeys(args.pending_verification))
            if args.pending_verification
            else list(checkpoint.get("pending_verification") or [])
        )
        checkpoint.update(
            {
                "id": str(uuid.uuid4()),
                "sequence": int(checkpoint.get("sequence") or 0) + 1,
                "checkpointed_at": now,
                "actor_id": actor_id,
                "runtime": str(owner.get("runtime") or ""),
                "reason": reason,
                "next_action": next_action,
                "pending_verification": pending_verification,
                "repository": repository_snapshot(project_root),
            }
        )
        continuation["status"] = "ready"
        state["updated_at"] = now
        validate_candidate(artifact_dir, "run_state.json", state, validate_run_state)
        commit_transition(
            artifact_dir,
            state_path,
            original_state,
            state,
            {
                "event": "continuation_handoff",
                "actor_id": actor_id,
                "runtime": owner.get("runtime"),
                "checkpoint_id": checkpoint["id"],
                "sequence": checkpoint["sequence"],
                "next_action": next_action,
                "reason": reason,
            },
        )
        print(
            json.dumps(
                {
                    "artifact_dir": str(artifact_dir),
                    "status": "ready",
                    "owner": owner,
                    "checkpoint_id": checkpoint["id"],
                    "next_action": next_action,
                },
                ensure_ascii=False,
                indent=2,
                sort_keys=True,
            )
        )
    return 0


def resume_run(args: argparse.Namespace) -> int:
    protocol, artifact_dir = select_active_protocol_artifact(args.path, args.run)
    if protocol == "portable":
        return portable_resume(args, artifact_dir)
    target = args.path.expanduser().resolve()
    if target.is_file() and target.name == "run_state.json":
        coordination_root = project_root_for_artifact(target.parent)
    elif (target / "run_state.json").is_file():
        coordination_root = project_root_for_artifact(target)
    else:
        coordination_root = target

    with locked(coordination_root / "workspace" / ".resume"):
        with locked(artifact_dir / ".harnessctl"):
            recovery_plan = plan_artifact_recovery(artifact_dir)
            errors = artifact_validation_errors_with_recovery(artifact_dir, recovery_plan)
            if errors:
                raise ValueError("artifact validation failed before resume: " + "; ".join(errors))

            state_path = artifact_dir / "run_state.json"
            state = load_object(state_path)
            original_state = deepcopy(state)
            project_root = project_root_for_artifact(artifact_dir)
            continuation, legacy_upgrade = continuation_record(state, project_root)
            actor_id = validate_actor(args.actor_id, "actor id")
            runtime = validate_actor(args.runtime.casefold(), "runtime")
            owner = continuation.get("owner")
            if not isinstance(owner, dict):
                raise ValueError("continuation owner is invalid")
            previous_owner = deepcopy(owner) if str(owner.get("actor_id") or "") else {}
            same_owner = (
                str(owner.get("actor_id") or "") == actor_id
                and str(owner.get("runtime") or "") == runtime
            )
            if same_owner:
                require_current_owner(state, actor_id, args.owner_epoch)
            forced = (
                continuation.get("status") == "active"
                and bool(previous_owner)
                and not same_owner
            )
            takeover_reason = args.takeover_reason.strip()
            if forced and not takeover_reason:
                raise ValueError("active owner takeover requires a non-empty takeover reason (--takeover-reason)")

            if not same_owner:
                old_epoch = int(owner.get("epoch") or 0)
                continuation["previous_owner"] = previous_owner
                continuation["owner"] = {
                    "actor_id": actor_id,
                    "runtime": runtime,
                    "epoch": old_epoch + 1,
                    "claimed_at": utc_now(),
                }
                if previous_owner:
                    continuation["takeover_count"] = int(continuation.get("takeover_count") or 0) + 1
            continuation["status"] = "active"
            continuation["last_resume"] = {
                "resumed_at": utc_now(),
                "actor_id": actor_id,
                "runtime": runtime,
                "takeover_reason": takeover_reason,
                "forced": forced,
            }
            state["updated_at"] = utc_now()
            current_repository = repository_snapshot(project_root)

            if state != original_state:
                validate_candidate(artifact_dir, "run_state.json", state, validate_run_state)
            packet = build_resume_packet(
                artifact_dir,
                state,
                current_repository=current_repository,
                legacy_upgrade=legacy_upgrade,
                forced_takeover=forced,
            )

            apply_recovery_plan(artifact_dir, recovery_plan, emit=False)
            if state != original_state:
                commit_transition(
                    artifact_dir,
                    state_path,
                    original_state,
                    state,
                    {
                        "event": "continuation_resume",
                        "previous_owner": previous_owner,
                        "owner": continuation["owner"],
                        "forced": forced,
                        "takeover_reason": takeover_reason,
                        "legacy_upgrade": legacy_upgrade,
                    },
                )
            print(json.dumps(packet, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


def task_set_unlocked(args: argparse.Namespace) -> int:
    artifact_dir = args.artifact_dir.expanduser().resolve()
    state_path = artifact_dir / "run_state.json"
    state = load_object(state_path)
    original_state = deepcopy(state)
    current_errors = validate_run_state(state_path)
    if current_errors:
        raise ValueError("current run_state is invalid: " + "; ".join(current_errors))
    require_current_owner(state, args.actor_id, args.owner_epoch)
    task = find_unique(state.get("tasks"), args.task_id, "task")
    old_status = str(task.get("status") or "")
    allowed = TASK_TRANSITIONS.get(old_status, set())
    if args.status not in allowed:
        raise ValueError(f"invalid task transition: {old_status} -> {args.status}")

    transaction_id = str(uuid.uuid4())
    subject = f"task:{args.task_id}"
    policy = state.get("evidence_policy")
    additions = build_evidence_additions(
        artifact_dir,
        subject=subject,
        freeform=args.evidence,
        files=getattr(args, "evidence_file", []),
        transaction_id=transaction_id,
        policy=policy,
    )
    evidence = append_unique_values(task.get("evidence"), additions)
    if args.status in {"passed", "merged"}:
        reject_self_report(args.evidence)
        if policy == EVIDENCE_POLICY and not qualifying_evidence(evidence, subject):
            raise ValueError(f"task status {args.status} requires qualifying evidence; use --evidence-file")
        if policy != EVIDENCE_POLICY and not evidence:
            raise ValueError(f"task status {args.status} requires evidence")
    if args.status in {"blocked", "verify_failed"} and not args.stop_reason:
        raise ValueError(f"task status {args.status} requires --stop-reason")
    if args.status == "running":
        tasks = state.get("tasks")
        task_map = {
            str(item.get("id")): item
            for item in tasks
            if isinstance(tasks, list) and isinstance(item, dict)
        }
        missing_dependencies = [
            str(dependency)
            for dependency in task.get("dependencies", [])
            if task_map.get(str(dependency), {}).get("status") not in {"passed", "merged"}
        ]
        if missing_dependencies:
            raise ValueError("task dependencies are not complete: " + ", ".join(missing_dependencies))

    task["status"] = args.status
    task["evidence"] = evidence
    task["stop_reason"] = args.stop_reason or ""
    if args.no_test_reason:
        task["verification_gate"]["no_test_reason"] = args.no_test_reason.strip()
    state["updated_at"] = utc_now()
    validate_candidate(artifact_dir, "run_state.json", state, validate_run_state)
    commit_transition(
        artifact_dir,
        state_path,
        original_state,
        state,
        {
            "event": "task_transition",
            "task_id": args.task_id,
            "from_status": old_status,
            "to_status": args.status,
            "evidence": additions,
            "stop_reason": args.stop_reason,
        },
        transaction_id=transaction_id,
    )
    print(f"task_transition=committed {args.task_id} {old_status}->{args.status}")
    return 0


def task_set(args: argparse.Namespace) -> int:
    artifact_dir = args.artifact_dir.expanduser().resolve()
    with locked(artifact_dir / ".harnessctl"):
        ensure_trace_integrity(artifact_dir)
        return task_set_unlocked(args)


def task_refresh_unlocked(args: argparse.Namespace) -> int:
    artifact_dir = args.artifact_dir.expanduser().resolve()
    state_path = artifact_dir / "run_state.json"
    state = load_object(state_path)
    original_state = deepcopy(state)
    current_errors = validate_run_state(state_path)
    if current_errors:
        raise ValueError("current run state is invalid: " + "; ".join(current_errors))
    require_current_owner(state, args.actor_id, args.owner_epoch)

    task = find_unique(state.get("tasks"), args.task_id, "task")
    if task.get("status") not in {"ready", "running", "verify_failed", "passed", "merged"}:
        raise ValueError("task evidence refresh requires an active or completed task")
    if not args.evidence_file:
        raise ValueError("task evidence refresh requires --evidence-file")

    transaction_id = str(uuid.uuid4())
    subject = f"task:{args.task_id}"
    additions = build_evidence_additions(
        artifact_dir,
        subject=subject,
        freeform=[],
        files=args.evidence_file,
        transaction_id=transaction_id,
        policy=state.get("evidence_policy"),
        verification_tier=args.verification_tier,
    )
    replacement_paths = {
        str(item.get("payload", {}).get("path"))
        for item in additions
        if isinstance(item, dict) and isinstance(item.get("payload"), dict)
    }
    existing = task.get("evidence") if isinstance(task.get("evidence"), list) else []
    retained = [
        item for item in existing
        if not (
            isinstance(item, dict)
            and isinstance(item.get("payload"), dict)
            and str(item["payload"].get("path")) in replacement_paths
        )
    ]
    task["evidence"] = append_unique_values(retained, additions)
    state["updated_at"] = utc_now()
    validate_candidate(artifact_dir, "run_state.json", state, validate_run_state)
    commit_transition(
        artifact_dir,
        state_path,
        original_state,
        state,
        {
            "event": "task_evidence_refresh",
            "task_id": args.task_id,
            "status": task.get("status"),
            "evidence": additions,
            "replaced_paths": sorted(replacement_paths),
        },
        transaction_id=transaction_id,
    )
    print(f"task_refresh=committed {args.task_id} paths={len(replacement_paths)}")
    return 0


def task_refresh(args: argparse.Namespace) -> int:
    artifact_dir = args.artifact_dir.expanduser().resolve()
    with locked(artifact_dir / ".harnessctl"):
        ensure_trace_structure_integrity(artifact_dir)
        return task_refresh_unlocked(args)


ACCEPTANCE_GATE_ARG_FIELDS = (
    ("gate_tdd_trace_path", "tdd_trace_path"),
    ("gate_red_command", "red_command"),
    ("gate_red_result", "red_result"),
    ("gate_red_failure_reason", "red_failure_reason"),
    ("gate_green_command", "green_command"),
    ("gate_green_result", "green_result"),
    ("gate_refactor_check", "refactor_check"),
    ("gate_substitute_check", "substitute_check"),
)


def acceptance_gate_updates_from_args(args: argparse.Namespace) -> dict[str, str]:
    updates: dict[str, str] = {}
    for arg_name, field_name in ACCEPTANCE_GATE_ARG_FIELDS:
        value = str(getattr(args, arg_name, "") or "").strip()
        if value:
            updates[field_name] = value
    no_test_reason = str(getattr(args, "no_test_reason", "") or "").strip()
    if no_test_reason:
        updates["no_test_reason"] = no_test_reason
    return updates


def acceptance_set_unlocked(args: argparse.Namespace) -> int:
    artifact_dir = args.artifact_dir.expanduser().resolve()
    registry_path = artifact_dir / "acceptance_registry.json"
    registry = load_object(registry_path)
    original_registry = deepcopy(registry)
    current_errors = validate_acceptance_registry(registry_path)
    if current_errors:
        raise ValueError("current acceptance registry is invalid: " + "; ".join(current_errors))
    require_current_owner(
        load_object(artifact_dir / "run_state.json"), args.actor_id, args.owner_epoch
    )

    criterion = find_unique(registry.get("criteria"), args.criterion_id, "acceptance criterion")
    old_status = str(criterion.get("status") or "")
    allowed = ACCEPTANCE_TRANSITIONS.get(old_status, set())
    if args.status not in allowed:
        raise ValueError(f"invalid acceptance transition: {old_status} -> {args.status}")

    transaction_id = str(uuid.uuid4())
    subject = f"acceptance:{args.criterion_id}"
    policy = registry.get("evidence_policy")
    verification_tier = args.verification_tier
    additions = build_evidence_additions(
        artifact_dir,
        subject=subject,
        freeform=args.evidence,
        files=getattr(args, "evidence_file", []),
        transaction_id=transaction_id,
        policy=policy,
        verification_tier=verification_tier,
    )
    evidence = append_unique_values(criterion.get("evidence"), additions)
    pass_algorithm = args.pass_algorithm.strip() or str(criterion.get("pass_algorithm") or "").strip()
    blocking_issues = append_unique(criterion.get("blocking_issues"), args.blocking_issue)
    if args.status in {"pass", "scoped_out"} and not evidence:
        raise ValueError(f"acceptance status {args.status} requires evidence")
    if args.status == "pass":
        reject_self_report(args.evidence)
        required_tier = str(criterion.get("required_verification_tier") or "policy")
        if policy == EVIDENCE_POLICY and not qualifying_evidence(evidence, subject, required_tier):
            raise ValueError("acceptance status pass requires qualifying evidence; use --evidence-file")
        state = load_object(artifact_dir / "run_state.json")
        witness_errors = state_witness_gate(artifact_dir, state, require_review=True)
        if witness_errors:
            raise ValueError("state witness gate failed: " + "; ".join(witness_errors))
    if args.status == "pass" and not pass_algorithm:
        raise ValueError("acceptance status pass requires pass_algorithm")
    if args.status in {"fail", "blocked"} and not blocking_issues:
        raise ValueError(f"acceptance status {args.status} requires --blocking-issue")

    criterion["status"] = args.status
    criterion["evidence"] = evidence
    criterion["pass_algorithm"] = pass_algorithm
    criterion["blocking_issues"] = blocking_issues if args.status in {"fail", "blocked"} else []
    gate_updates = acceptance_gate_updates_from_args(args)
    if gate_updates:
        if not isinstance(criterion.get("verification_gate"), dict):
            criterion["verification_gate"] = {}
        criterion["verification_gate"].update(gate_updates)
    registry["updated_at"] = utc_now()
    validate_candidate(artifact_dir, "acceptance_registry.json", registry, validate_acceptance_registry)
    commit_transition(
        artifact_dir,
        registry_path,
        original_registry,
        registry,
        {
            "event": "acceptance_transition",
            "criterion_id": args.criterion_id,
            "from_status": old_status,
            "to_status": args.status,
            "evidence": additions,
            "blocking_issues": args.blocking_issue,
            "verification_gate_updates": sorted(gate_updates),
        },
        transaction_id=transaction_id,
    )
    print(f"acceptance_transition=committed {args.criterion_id} {old_status}->{args.status}")
    return 0


def acceptance_set(args: argparse.Namespace) -> int:
    artifact_dir = args.artifact_dir.expanduser().resolve()
    with locked(artifact_dir / ".harnessctl"):
        ensure_trace_integrity(artifact_dir)
        return acceptance_set_unlocked(args)


def acceptance_refresh_unlocked(args: argparse.Namespace) -> int:
    artifact_dir = args.artifact_dir.expanduser().resolve()
    state = load_object(artifact_dir / "run_state.json")
    require_current_owner(state, args.actor_id, args.owner_epoch)
    registry_path = artifact_dir / "acceptance_registry.json"
    registry = load_object(registry_path)
    original_registry = deepcopy(registry)
    current_errors = validate_acceptance_registry(registry_path)
    if current_errors:
        raise ValueError("current acceptance registry is invalid: " + "; ".join(current_errors))

    criterion = find_unique(registry.get("criteria"), args.criterion_id, "acceptance criterion")
    criterion_status = str(criterion.get("status") or "")
    if criterion_status not in {"pass", "blocked", "fail", "scoped_out"}:
        raise ValueError(
            "acceptance evidence refresh requires a terminal or decisioned criterion status"
        )
    if not args.evidence_file:
        raise ValueError("acceptance evidence refresh requires --evidence-file")

    transaction_id = str(uuid.uuid4())
    subject = f"acceptance:{args.criterion_id}"
    additions = build_evidence_additions(
        artifact_dir,
        subject=subject,
        freeform=[],
        files=args.evidence_file,
        transaction_id=transaction_id,
        policy=registry.get("evidence_policy"),
        verification_tier=args.verification_tier,
    )
    replacement_paths = {
        str(item.get("payload", {}).get("path"))
        for item in additions
        if isinstance(item, dict) and isinstance(item.get("payload"), dict)
    }
    existing = criterion.get("evidence") if isinstance(criterion.get("evidence"), list) else []
    retained = [
        item for item in existing
        if not (
            isinstance(item, dict)
            and isinstance(item.get("payload"), dict)
            and str(item["payload"].get("path")) in replacement_paths
        )
    ]
    criterion["evidence"] = append_unique_values(retained, additions)
    registry["updated_at"] = utc_now()
    validate_candidate(artifact_dir, "acceptance_registry.json", registry, validate_acceptance_registry)
    commit_transition(
        artifact_dir,
        registry_path,
        original_registry,
        registry,
        {
            "event": "acceptance_evidence_refresh",
            "criterion_id": args.criterion_id,
            "status": criterion_status,
            "evidence": additions,
            "replaced_paths": sorted(replacement_paths),
        },
        transaction_id=transaction_id,
    )
    print(f"acceptance_refresh=committed {args.criterion_id} paths={len(replacement_paths)}")
    return 0


def acceptance_refresh(args: argparse.Namespace) -> int:
    artifact_dir = args.artifact_dir.expanduser().resolve()
    with locked(artifact_dir / ".harnessctl"):
        ensure_trace_structure_integrity(artifact_dir)
        return acceptance_refresh_unlocked(args)


def run_set_unlocked(args: argparse.Namespace) -> int:
    artifact_dir = args.artifact_dir.expanduser().resolve()
    state_path = artifact_dir / "run_state.json"
    registry_path = artifact_dir / "acceptance_registry.json"
    state = load_object(state_path)
    original_state = deepcopy(state)
    current_errors = validate_run_state(state_path)
    if current_errors:
        raise ValueError("current run_state is invalid: " + "; ".join(current_errors))
    require_current_owner(state, args.actor_id, args.owner_epoch)

    old_status = str(state.get("status") or "")
    if args.status not in RUN_TRANSITIONS.get(old_status, set()):
        raise ValueError(f"invalid run transition: {old_status} -> {args.status}")
    if args.status == "dispatched" and not has_state_seal(artifact_dir):
        raise ValueError("run dispatch requires a sealed baseline; run harnessctl seal first")
    transaction_id = str(uuid.uuid4())
    subject = "run"
    policy = state.get("evidence_policy")
    evidence = build_evidence_additions(
        artifact_dir,
        subject=subject,
        freeform=args.evidence,
        files=getattr(args, "evidence_file", []),
        transaction_id=transaction_id,
        policy=policy,
        verification_tier=args.verification_tier,
    )

    if args.status in {"accepted", "handed_off"}:
        if not evidence:
            raise ValueError(f"run status {args.status} requires evidence")
        reject_self_report(args.evidence)
        existing_run_evidence = append_unique_values(state.get("run_evidence"), evidence)
        if policy == EVIDENCE_POLICY and not qualifying_evidence(existing_run_evidence, subject):
            raise ValueError(f"run status {args.status} requires qualifying evidence; use --evidence-file")
        tasks = state.get("tasks")
        if not isinstance(tasks, list):
            raise ValueError("run_state tasks must be a list")
        incomplete_tasks = [
            str(item.get("id") or "?")
            for item in tasks if isinstance(item, dict)
            if item.get("status") not in {"passed", "merged"}
        ]
        if incomplete_tasks:
            raise ValueError("run has incomplete tasks: " + ", ".join(incomplete_tasks))
        registry = load_object(registry_path)
        registry_errors = validate_acceptance_registry(registry_path)
        if registry_errors:
            raise ValueError("current acceptance registry is invalid: " + "; ".join(registry_errors))
        criteria = registry.get("criteria")
        if not isinstance(criteria, list):
            raise ValueError("acceptance criteria must be a list")
        unresolved = [
            str(item.get("id") or "?")
            for item in criteria if isinstance(item, dict)
            if item.get("status") not in {"pass", "scoped_out"}
        ]
        if unresolved:
            raise ValueError("run has unresolved acceptance: " + ", ".join(unresolved))
        tdd_errors = validate_active_tdd_gates(artifact_dir, state, registry)
        if tdd_errors:
            raise ValueError("active TDD gate failed: " + "; ".join(tdd_errors))
        witness_errors = state_witness_gate(artifact_dir, state, require_review=True)
        if witness_errors:
            raise ValueError("state witness gate failed: " + "; ".join(witness_errors))
        task_statuses = {
            str(item.get("id")): item.get("status")
            for item in tasks if isinstance(item, dict)
        }
        for stage in state.get("stages", []):
            if not isinstance(stage, dict):
                continue
            linked = stage.get("tasks")
            if isinstance(linked, list) and all(task_statuses.get(str(task_id)) in {"passed", "merged"} for task_id in linked):
                stage["status"] = "passed"
                stage["evidence"] = append_unique_values(stage.get("evidence"), evidence)
        state["status"] = args.status
        dispatch_errors = validate_dispatch_coverage(state)
        if dispatch_errors:
            raise ValueError("durable dispatch gate failed: " + "; ".join(dispatch_errors))

    state["status"] = args.status
    state["run_evidence"] = append_unique_values(state.get("run_evidence"), evidence)
    state["stop_reason"] = args.stop_reason.strip()
    state["updated_at"] = utc_now()
    validate_candidate(artifact_dir, "run_state.json", state, validate_run_state)
    commit_transition(
        artifact_dir,
        state_path,
        original_state,
        state,
        {
            "event": "run_transition",
            "from_status": old_status,
            "to_status": args.status,
            "evidence": evidence,
            "stop_reason": args.stop_reason.strip(),
        },
        transaction_id=transaction_id,
    )
    print(f"run_transition=committed {old_status}->{args.status}")
    return 0


def run_set(args: argparse.Namespace) -> int:
    artifact_dir = args.artifact_dir.expanduser().resolve()
    with locked(artifact_dir / ".harnessctl"):
        ensure_trace_integrity(artifact_dir)
        return run_set_unlocked(args)


def dispatch_create_unlocked(args: argparse.Namespace) -> int:
    artifact_dir = args.artifact_dir.expanduser().resolve()
    state_path = artifact_dir / "run_state.json"
    state = load_object(state_path)
    original_state = deepcopy(state)
    current_errors = validate_run_state(state_path)
    if current_errors:
        raise ValueError("current run_state is invalid: " + "; ".join(current_errors))
    require_current_owner(state, args.actor_id, args.owner_epoch)
    witness_errors = state_witness_gate(artifact_dir, state, require_review=False)
    if witness_errors:
        raise ValueError("state witness gate failed before dispatch: " + "; ".join(witness_errors))
    if state.get("status") not in {"specified", "dispatched"}:
        raise ValueError("worker dispatch requires run status specified or dispatched")
    if not has_state_seal(artifact_dir):
        raise ValueError("worker dispatch requires a sealed baseline; run harnessctl seal first")

    task = find_unique(state.get("tasks"), args.task_id, "task")
    if args.contract_path != task.get("task_path"):
        raise ValueError("contract path must exactly match task_path")
    if args.report_path != task.get("report_path"):
        raise ValueError("report path must exactly match task report_path")
    resolve_artifact_path(artifact_dir, args.contract_path, "contract path", must_exist=True)
    resolve_artifact_path(artifact_dir, args.report_path, "report path", must_exist=False)
    worker_id = args.worker_id.strip()
    if not worker_id or any(ord(character) < 32 for character in worker_id):
        raise ValueError("worker id must be a non-empty opaque string without control characters")
    runtime = args.runtime.strip().casefold()
    requested_model = args.requested_model.strip()
    reasoning_effort = args.reasoning_effort.strip()
    resolved_model = args.resolved_model.strip()
    route_reason = args.route_reason.strip() or f"selected {args.profile} profile"
    if not runtime or any(ord(character) < 32 for character in runtime):
        raise ValueError("runtime must be a non-empty string without control characters")
    if any(ord(character) < 32 for value in (requested_model, reasoning_effort, resolved_model, route_reason) for character in value):
        raise ValueError("model routing values must not contain control characters")
    if args.escalation_count < 0:
        raise ValueError("escalation count must be non-negative")
    sealed_profiles = model_profiles_for(runtime, state.get("routing_policy"))
    if sealed_profiles is not None:
        configured = sealed_profiles[args.profile]
        requested_model = requested_model or configured["model"]
        reasoning_effort = reasoning_effort or configured["reasoning_effort"]
        if requested_model != configured["model"] or reasoning_effort != configured["reasoning_effort"]:
            raise ValueError(
                f"{runtime} profile {args.profile} must use "
                f"{configured['model']} {configured['reasoning_effort']}"
            )
        if runtime == "codex" and "terra" in resolved_model.casefold():
            raise ValueError("Codex resolved model must not use disabled Terra models")

    session_state = state.get("state_layers", {}).get("session_state", {})
    dispatches = session_state.get("delegation_state") if isinstance(session_state, dict) else None
    if not isinstance(dispatches, list):
        raise ValueError("delegation_state list is missing")
    if any(
        isinstance(item, dict)
        and item.get("task_id") == args.task_id
        and item.get("status") in {"dispatched", "running"}
        for item in dispatches
    ):
        raise ValueError(f"task already has an active dispatch: {args.task_id}")

    now = utc_now()
    record = {
        "dispatch_id": str(uuid.uuid4()),
        "worker_id": worker_id,
        "task_id": args.task_id,
        "contract_path": args.contract_path,
        "report_path": args.report_path,
        "status": "dispatched",
        "runtime": runtime,
        "profile": args.profile,
        "requested_model": requested_model,
        "resolved_model": resolved_model,
        "reasoning_effort": reasoning_effort,
        "route_reason": route_reason,
        "escalation_count": args.escalation_count,
        "created_at": now,
        "updated_at": now,
        "stop_reason": "",
    }
    dispatches.append(record)
    state["updated_at"] = now
    validate_candidate(artifact_dir, "run_state.json", state, validate_run_state)
    commit_transition(
        artifact_dir,
        state_path,
        original_state,
        state,
        {"event": "dispatch_create", **record},
    )
    print(
        "dispatch_create=committed "
        f"dispatch_id={record['dispatch_id']} task_id={args.task_id} worker_id={worker_id} status=dispatched"
    )
    return 0


def dispatch_create(args: argparse.Namespace) -> int:
    artifact_dir = args.artifact_dir.expanduser().resolve()
    with locked(artifact_dir / ".harnessctl"):
        ensure_trace_integrity(artifact_dir)
        return dispatch_create_unlocked(args)


def dispatch_update_unlocked(args: argparse.Namespace) -> int:
    artifact_dir = args.artifact_dir.expanduser().resolve()
    state_path = artifact_dir / "run_state.json"
    state = load_object(state_path)
    original_state = deepcopy(state)
    current_errors = validate_run_state(state_path)
    if current_errors:
        raise ValueError("current run_state is invalid: " + "; ".join(current_errors))
    require_current_owner(state, args.actor_id, args.owner_epoch)
    session_state = state.get("state_layers", {}).get("session_state", {})
    dispatches = session_state.get("delegation_state") if isinstance(session_state, dict) else None
    record = find_unique(dispatches, args.dispatch_id, "dispatch", key="dispatch_id")
    old_status = str(record.get("status") or "")
    if args.status not in DISPATCH_TRANSITIONS.get(old_status, set()):
        raise ValueError(f"invalid dispatch transition: {old_status} -> {args.status}")
    if args.status == "reported":
        resolve_artifact_path(artifact_dir, str(record.get("report_path") or ""), "report path", must_exist=True)
    if args.status in {"failed", "cancelled"} and not args.stop_reason.strip():
        raise ValueError(f"dispatch status {args.status} requires --stop-reason")

    record["status"] = args.status
    record["updated_at"] = utc_now()
    record["stop_reason"] = args.stop_reason.strip() if args.status in {"failed", "cancelled"} else ""
    state["updated_at"] = utc_now()
    validate_candidate(artifact_dir, "run_state.json", state, validate_run_state)
    commit_transition(
        artifact_dir,
        state_path,
        original_state,
        state,
        {
            "event": "dispatch_update",
            "dispatch_id": args.dispatch_id,
            "task_id": record.get("task_id"),
            "from_status": old_status,
            "to_status": args.status,
            "stop_reason": record["stop_reason"],
        },
    )
    print(f"dispatch_update=committed dispatch_id={args.dispatch_id} {old_status}->{args.status}")
    return 0


def dispatch_update(args: argparse.Namespace) -> int:
    artifact_dir = args.artifact_dir.expanduser().resolve()
    with locked(artifact_dir / ".harnessctl"):
        ensure_trace_integrity(artifact_dir)
        return dispatch_update_unlocked(args)


def plan_artifact_recovery(
    artifact_dir: Path,
) -> list[tuple[dict[str, object], str]]:
    trace_path = artifact_dir / "trace.jsonl"
    jsonl_errors = validate_jsonl(trace_path)
    if jsonl_errors:
        raise ValueError("artifact trace integrity failed: " + "; ".join(jsonl_errors))
    events = [json.loads(line) for line in trace_path.read_text(encoding="utf-8").splitlines() if line.strip()]
    starts = {
        str(event["transaction_id"]): event
        for event in events
        if isinstance(event, dict)
        and str(event.get("event", "")).endswith("_started")
        and event.get("transaction_id")
    }
    terminals = {
        str(event["transaction_id"])
        for event in events
        if isinstance(event, dict)
        and not str(event.get("event", "")).endswith("_started")
        and event.get("transaction_id")
    }
    pending = [event for transaction_id, event in starts.items() if transaction_id not in terminals]
    plan: list[tuple[dict[str, object], str]] = []
    for started in pending:
        transaction_id = str(started["transaction_id"])
        state_file = str(started.get("state_file") or "")
        if not state_file or Path(state_file).name != state_file:
            raise ValueError(f"transaction {transaction_id} has unsafe or missing state_file")
        before_digest = str(started.get("before_sha256") or "")
        after_digest = str(started.get("after_sha256") or "")
        if not before_digest or not after_digest:
            raise ValueError(f"transaction {transaction_id} lacks recovery digests")
        state_path = artifact_dir / state_file
        actual_digest = sha256(state_path.read_bytes())
        base_event = str(started["event"])[: -len("_started")]
        if actual_digest == after_digest:
            terminal_event = base_event
            result = "committed"
        elif actual_digest == before_digest:
            terminal_event = f"{base_event}_aborted"
            result = "aborted"
        else:
            raise ValueError(f"transaction {transaction_id} state digest matches neither before nor after")
        terminal = {**started, "event": terminal_event, "ts": utc_now()}
        plan.append((terminal, result))
    return plan


def apply_recovery_plan(
    artifact_dir: Path,
    plan: list[tuple[dict[str, object], str]],
    *,
    emit: bool,
) -> list[str]:
    trace_path = artifact_dir / "trace.jsonl"
    results: list[str] = []
    for terminal, result in plan:
        transaction_id = str(terminal["transaction_id"])
        append_jsonl(trace_path, terminal, writer_role="manager", scope="global")
        results.append(f"{result} {transaction_id}")
        if emit:
            print(f"recovery={result} {transaction_id}")
    if emit and not plan:
        print("recovery=no incomplete transactions")
    return results


def recover_artifact_unlocked(artifact_dir: Path, *, emit: bool) -> list[str]:
    plan = plan_artifact_recovery(artifact_dir)
    results = apply_recovery_plan(artifact_dir, plan, emit=emit)
    ensure_trace_integrity(artifact_dir)
    return results


def artifact_validation_errors_with_recovery(
    artifact_dir: Path,
    plan: list[tuple[dict[str, object], str]],
) -> list[str]:
    if not plan:
        return artifact_validation_errors(artifact_dir)
    fd, name = tempfile.mkstemp(prefix=".trace.recovery.", suffix=".jsonl", dir=str(artifact_dir))
    path = Path(name)
    try:
        with open(fd, "w", encoding="utf-8", closefd=True) as handle:
            handle.write((artifact_dir / "trace.jsonl").read_text(encoding="utf-8"))
            for terminal, _ in plan:
                handle.write(json.dumps(terminal, ensure_ascii=False, sort_keys=True) + "\n")
        return artifact_validation_errors(artifact_dir, trace_path=path)
    finally:
        path.unlink(missing_ok=True)


def recover_artifact(args: argparse.Namespace) -> int:
    artifact_dir = args.artifact_dir.expanduser().resolve()
    with locked(artifact_dir / ".harnessctl"):
        state = load_object(artifact_dir / "run_state.json")
        require_current_owner(state, args.actor_id, args.owner_epoch)
        recover_artifact_unlocked(artifact_dir, emit=True)
    return 0


def validate_jsonl(path: Path) -> list[str]:
    if not path.exists():
        return [f"missing file: {path.name}"]
    errors: list[str] = []
    content = path.read_text(encoding="utf-8")
    if content and not content.endswith("\n"):
        errors.append(f"{path.name}: missing final newline")
    for line_number, line in enumerate(content.splitlines(), start=1):
        if not line.strip():
            continue
        try:
            event = json.loads(line)
        except json.JSONDecodeError as exc:
            errors.append(f"{path.name}: line {line_number} invalid JSON: {exc.msg}")
            continue
        if not isinstance(event, dict):
            errors.append(f"{path.name}: line {line_number} must be an object")
    return errors


def transaction_payload(event: dict[str, object]) -> str:
    value = {key: item for key, item in event.items() if key not in {"event", "ts"}}
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def validate_trace_transactions(path: Path) -> list[str]:
    if not path.exists():
        return []
    started: dict[str, tuple[str, str]] = {}
    committed: dict[str, tuple[str, str]] = {}
    errors: list[str] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            continue
        if not isinstance(event, dict) or not event.get("transaction_id"):
            continue
        transaction_id = str(event["transaction_id"])
        event_name = str(event.get("event", ""))
        if event_name.endswith("_started"):
            base = event_name[: -len("_started")]
            if transaction_id in started:
                errors.append(f"trace.jsonl: duplicate transaction start: {transaction_id}")
            started[transaction_id] = (base, transaction_payload(event))
        else:
            if transaction_id in committed:
                errors.append(f"trace.jsonl: duplicate transaction commit: {transaction_id}")
            committed[transaction_id] = (event_name, transaction_payload(event))
    for transaction_id, (base, payload) in started.items():
        if transaction_id not in committed or committed[transaction_id][0] not in {base, f"{base}_aborted"}:
            errors.append(f"trace.jsonl: incomplete transaction: {transaction_id}")
        elif committed[transaction_id][1] != payload:
            errors.append(f"trace.jsonl: transaction payload mismatch: {transaction_id}")
    for transaction_id in sorted(set(committed) - set(started)):
        errors.append(f"trace.jsonl: commit without start: {transaction_id}")
    return errors


def validate_transaction_digest_chain(path: Path) -> list[str]:
    if not path.exists():
        return []
    expected: dict[str, str] = {}
    pending: dict[str, tuple[str, str, str]] = {}
    errors: list[str] = []
    initialized = 0
    previous_was_start: str | None = None
    digest_pattern = re.compile(r"^[0-9a-f]{64}$")
    parsed_events: list[dict[str, object]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(event, dict):
            parsed_events.append(event)
    has_sealed_anchor = any(
        event.get("event") in {"state_sealed", "state_reseal_baseline"}
        for event in parsed_events
    )
    for event in parsed_events:
        state_digests = event.get("state_digests")
        if event.get("event") in DIGEST_ANCHOR_EVENTS and isinstance(state_digests, dict):
            if event.get("event") == "run_initialized":
                initialized += 1
                if initialized > 1:
                    errors.append("trace.jsonl: duplicate run_initialized anchor")
            for filename, digest in state_digests.items():
                if isinstance(filename, str) and isinstance(digest, str):
                    if not digest_pattern.fullmatch(digest):
                        errors.append(f"trace.jsonl: invalid canonical digest for {filename}")
                    if event.get("event") != "run_initialized" or not has_sealed_anchor:
                        expected[filename] = digest
            continue
        event_name = str(event.get("event") or "")
        state_file = event.get("state_file")
        transaction_id = str(event.get("transaction_id") or "")
        if event_name.endswith("_started") and isinstance(state_file, str):
            if previous_was_start is not None:
                errors.append(f"trace.jsonl: transaction {previous_was_start} start is not adjacent to its terminal")
            before_digest = str(event.get("before_sha256") or "")
            after_digest = str(event.get("after_sha256") or "")
            if not digest_pattern.fullmatch(before_digest) or not digest_pattern.fullmatch(after_digest):
                errors.append(f"trace.jsonl: transaction {transaction_id} has invalid state digest")
            previous_digest = expected.get(state_file)
            if previous_digest is not None and before_digest != previous_digest:
                errors.append(f"trace.jsonl: {state_file} transaction digest chain is broken")
            pending[transaction_id] = (state_file, before_digest, after_digest)
            previous_was_start = transaction_id
        elif transaction_id in pending:
            if previous_was_start != transaction_id:
                errors.append(f"trace.jsonl: transaction {transaction_id} terminal is not adjacent to its start")
            pending_state_file, before_digest, after_digest = pending[transaction_id]
            expected[pending_state_file] = before_digest if event_name.endswith("_aborted") else after_digest
            previous_was_start = None
        elif previous_was_start is not None:
            errors.append(f"trace.jsonl: transaction {previous_was_start} start is not adjacent to its terminal")
            previous_was_start = None
    return errors


def ensure_trace_structure_integrity(artifact_dir: Path) -> None:
    errors = [
        *validate_jsonl(artifact_dir / "trace.jsonl"),
        *validate_jsonl(artifact_dir / "tdd_trace.jsonl"),
        *validate_trace_transactions(artifact_dir / "trace.jsonl"),
        *validate_transaction_digest_chain(artifact_dir / "trace.jsonl"),
        *validate_canonical_state_digests(artifact_dir),
    ]
    if errors:
        raise ValueError("artifact trace integrity failed: " + "; ".join(errors))


def ensure_trace_integrity(artifact_dir: Path) -> None:
    ensure_trace_structure_integrity(artifact_dir)
    errors = validate_evidence_receipts(artifact_dir)
    if errors:
        raise ValueError("artifact trace integrity failed: " + "; ".join(errors))


def validate_canonical_state_digests(
    artifact_dir: Path, trace_path: Path | None = None
) -> list[str]:
    trace_path = trace_path or artifact_dir / "trace.jsonl"
    if not trace_path.exists():
        return []
    expected: dict[str, str] = {}
    for line in trace_path.read_text(encoding="utf-8").splitlines():
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            continue
        if not isinstance(event, dict):
            continue
        if event.get("event") in DIGEST_ANCHOR_EVENTS and isinstance(event.get("state_digests"), dict):
            for filename, digest in event["state_digests"].items():
                if isinstance(filename, str) and isinstance(digest, str):
                    expected[filename] = digest
        event_name = str(event.get("event") or "")
        state_file = event.get("state_file")
        if not isinstance(state_file, str) or not state_file or event_name.endswith("_started"):
            continue
        digest_key = "before_sha256" if event_name.endswith("_aborted") else "after_sha256"
        digest = event.get(digest_key)
        if isinstance(digest, str) and digest:
            expected[state_file] = digest

    errors: list[str] = []
    for filename, digest in expected.items():
        if Path(filename).name != filename:
            errors.append(f"trace.jsonl: unsafe canonical state file: {filename}")
            continue
        path = artifact_dir / filename
        if not path.exists():
            errors.append(f"missing canonical state file: {filename}")
        elif sha256(path.read_bytes()) != digest:
            errors.append(f"{filename}: digest does not match latest committed state")
    return errors


def seal_artifact(args: argparse.Namespace) -> int:
    artifact_dir = args.artifact_dir.expanduser().resolve()
    with locked(artifact_dir / ".harnessctl"):
        structural_errors = [
            *validate_jsonl(artifact_dir / "trace.jsonl"),
            *validate_jsonl(artifact_dir / "tdd_trace.jsonl"),
            *validate_trace_transactions(artifact_dir / "trace.jsonl"),
            *validate_run_state(artifact_dir / "run_state.json"),
            *validate_acceptance_registry(artifact_dir / "acceptance_registry.json"),
        ]
        if structural_errors:
            raise ValueError("cannot seal invalid artifact: " + "; ".join(structural_errors))
        state = load_object(artifact_dir / "run_state.json")
        original_state = deepcopy(state)
        require_current_owner(state, args.actor_id, args.owner_epoch)
        witness_errors = state_witness_gate(artifact_dir, state, require_review=False)
        if witness_errors:
            raise ValueError("cannot seal invalid state witness: " + "; ".join(witness_errors))
        if state.get("status") not in {"intake", "gated", "specified"}:
            raise ValueError("seal is only allowed before dispatch")
        if any(
            isinstance(task, dict) and task.get("status") in {"running", "passed", "merged"}
            for task in state.get("tasks", []) if isinstance(state.get("tasks"), list)
        ):
            raise ValueError("seal requires all tasks to remain pre-execution")
        session_state = state.get("state_layers", {}).get("session_state", {})
        dispatches = session_state.get("delegation_state", []) if isinstance(session_state, dict) else []
        if isinstance(dispatches, list) and dispatches:
            raise ValueError("seal is only allowed before dispatch")
        trace_events = [
            json.loads(line)
            for line in (artifact_dir / "trace.jsonl").read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]
        if any(isinstance(event, dict) and event.get("event") == "dispatch_create" for event in trace_events):
            raise ValueError("seal is only allowed before dispatch")
        reason = args.reason.strip()
        if not reason:
            raise ValueError("seal requires --reason")
        if has_state_seal(artifact_dir):
            baseline_digests = {
                "run_state.json": sha256((artifact_dir / "run_state.json").read_bytes()),
                "acceptance_registry.json": sha256(
                    (artifact_dir / "acceptance_registry.json").read_bytes()
                ),
            }
            state_witness = state.get("state_witness")
            if isinstance(state_witness, dict) and state_witness.get("required"):
                baseline_digests[str(state_witness["path"])] = sha256(
                    (artifact_dir / str(state_witness["path"])).read_bytes()
                )
            append_jsonl(
                artifact_dir / "trace.jsonl",
                {
                    "event": "state_reseal_baseline",
                    "ts": utc_now(),
                    "reason": reason,
                    "state_digests": baseline_digests,
                },
                writer_role="manager",
                scope="global",
            )
        state_witness = state.get("state_witness")
        if isinstance(state_witness, dict) and state_witness.get("required"):
            witness_path = artifact_dir / str(state_witness["path"])
            state_witness["sealed_digest"] = sha256(witness_path.read_bytes())
            state["updated_at"] = utc_now()
            validate_candidate(artifact_dir, "run_state.json", state, validate_run_state)
            commit_transition(
                artifact_dir,
                artifact_dir / "run_state.json",
                original_state,
                state,
                {"event": "state_witness_sealed", "reason": reason},
            )
        state_digests = {
            "run_state.json": sha256((artifact_dir / "run_state.json").read_bytes()),
            "acceptance_registry.json": sha256((artifact_dir / "acceptance_registry.json").read_bytes()),
        }
        state_witness = state.get("state_witness")
        if isinstance(state_witness, dict) and state_witness.get("required"):
            state_digests[str(state_witness["path"])] = sha256(
                (artifact_dir / str(state_witness["path"])).read_bytes()
            )
        event = {
            "event": "state_sealed",
            "ts": utc_now(),
            "reason": reason,
            "state_digests": state_digests,
        }
        append_jsonl(artifact_dir / "trace.jsonl", event, writer_role="manager", scope="global")
        print("state_sealed=committed")
        return 0


def witness_set(args: argparse.Namespace) -> int:
    artifact_dir = args.artifact_dir.expanduser().resolve()
    with locked(artifact_dir / ".harnessctl"):
        ensure_trace_integrity(artifact_dir)
        state_path = artifact_dir / "run_state.json"
        state = load_object(state_path)
        original_state = deepcopy(state)
        current_errors = validate_run_state(state_path)
        if current_errors:
            raise ValueError("current run_state is invalid: " + "; ".join(current_errors))
        require_current_owner(state, args.actor_id, args.owner_epoch)
        record = state.get("state_witness")
        if not isinstance(record, dict) or not record.get("required"):
            raise ValueError("state witness is not required for this run")
        if args.status == "pass":
            gate_errors = state_witness_gate(artifact_dir, state, require_review=False)
            if gate_errors:
                raise ValueError("state witness validation failed: " + "; ".join(gate_errors))
            if not args.reviewer_id.strip():
                raise ValueError("witness pass requires --reviewer-id")
            required_tier = str(record.get("required_tier") or "policy")
            if required_tier not in VERIFICATION_TIERS or VERIFICATION_TIERS.index(args.verification_tier) < VERIFICATION_TIERS.index(required_tier):
                raise ValueError(
                    f"witness verification tier {args.verification_tier} is below required {required_tier}"
                )
            transaction_id = str(uuid.uuid4())
            additions = build_evidence_additions(
                artifact_dir,
                subject="state_witness",
                freeform=[],
                files=args.evidence_file,
                transaction_id=transaction_id,
                policy=EVIDENCE_POLICY,
                verification_tier=args.verification_tier,
            )
            if not qualifying_evidence(additions, "state_witness", args.verification_tier):
                raise ValueError("witness pass requires a qualifying --evidence-file")
            record["review_status"] = "pass"
            record["reviewer_id"] = args.reviewer_id.strip()
            record["observed_tier"] = args.verification_tier
            record["review_evidence"] = additions
            record["reviewed_at"] = utc_now()
        else:
            transaction_id = str(uuid.uuid4())
            if not args.reason.strip():
                raise ValueError(f"witness status {args.status} requires --reason")
            record["review_status"] = args.status
            record["reviewer_id"] = args.reviewer_id.strip()
            record["reviewed_at"] = utc_now()
        state["updated_at"] = utc_now()
        validate_candidate(artifact_dir, "run_state.json", state, validate_run_state)
        commit_transition(
            artifact_dir,
            state_path,
            original_state,
            state,
            {
                "event": "state_witness_review",
                "status": args.status,
                "reviewer_id": args.reviewer_id.strip(),
                "reason": args.reason.strip(),
            },
            transaction_id=transaction_id,
        )
        print(f"state_witness=committed status={args.status}")
        return 0


def validate_evidence_receipts(
    artifact_dir: Path, trace_path: Path | None = None
) -> list[str]:
    trace_path = trace_path or artifact_dir / "trace.jsonl"
    if not trace_path.exists():
        return []
    terminals: dict[str, dict[str, object]] = {}
    for line in trace_path.read_text(encoding="utf-8").splitlines():
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            continue
        if not isinstance(event, dict):
            continue
        event_name = str(event.get("event") or "")
        transaction_id = event.get("transaction_id")
        if isinstance(transaction_id, str) and not event_name.endswith("_started") and not event_name.endswith("_aborted"):
            terminals[transaction_id] = event

    records: list[tuple[str, object]] = []
    for filename in ("run_state.json", "acceptance_registry.json"):
        path = artifact_dir / filename
        if not path.exists():
            continue
        try:
            data = load_object(path)
        except ValueError:
            continue
        if filename == "run_state.json":
            tasks = data.get("tasks")
            for task in tasks if isinstance(tasks, list) else []:
                if isinstance(task, dict):
                    for record in task.get("evidence", []) if isinstance(task.get("evidence"), list) else []:
                        records.append((f"task:{task.get('id')}", record))
            for record in data.get("run_evidence", []) if isinstance(data.get("run_evidence"), list) else []:
                records.append(("run", record))
        else:
            criteria = data.get("criteria")
            for criterion in criteria if isinstance(criteria, list) else []:
                if isinstance(criterion, dict):
                    for record in criterion.get("evidence", []) if isinstance(criterion.get("evidence"), list) else []:
                        records.append((f"acceptance:{criterion.get('id')}", record))

    errors: list[str] = []
    seen_ids: set[str] = set()
    for subject, record in records:
        if not isinstance(record, dict):
            continue
        evidence_id = str(record.get("id") or "")
        if evidence_id:
            if evidence_id in seen_ids:
                errors.append(f"duplicate evidence id: {evidence_id}")
            seen_ids.add(evidence_id)
        if record.get("type") not in QUALIFYING_EVIDENCE_TYPES:
            continue
        verification = record.get("verification")
        transaction_id = str(verification.get("transaction_id") or "") if isinstance(verification, dict) else ""
        terminal = terminals.get(transaction_id)
        if terminal is None or record not in terminal.get("evidence", []):
            errors.append(f"{evidence_id or subject}: missing committed evidence receipt")
            continue
        payload = record.get("payload")
        if record.get("type") == "artifact_digest" and isinstance(payload, dict):
            value = str(payload.get("path") or "")
            try:
                path, normalized = artifact_evidence_path(artifact_dir, value)
            except ValueError as exc:
                errors.append(f"{evidence_id or subject}: {exc}")
                continue
            actual = sha256(path.read_bytes())
            if actual != payload.get("sha256"):
                errors.append(f"{evidence_id or subject}: artifact digest mismatch: {normalized}")
            if path.stat().st_size != payload.get("size_bytes"):
                errors.append(f"{evidence_id or subject}: artifact size mismatch: {normalized}")
    return errors


def validate_dispatch_coverage(state: dict[str, object]) -> list[str]:
    if state.get("status") not in {"dispatched", "reported", "evaluating", "accepted", "handed_off"}:
        return []
    tasks = state.get("tasks")
    if not isinstance(tasks, list):
        return []
    session_state = state.get("state_layers", {}).get("session_state", {})
    dispatches = session_state.get("delegation_state", []) if isinstance(session_state, dict) else []
    errors: list[str] = []
    for task in tasks:
        if not isinstance(task, dict) or task.get("owner") in {"manager", "main-agent"}:
            continue
        task_id = str(task.get("id") or "?")
        related = [
            item for item in dispatches
            if isinstance(item, dict) and str(item.get("task_id")) == task_id
        ] if isinstance(dispatches, list) else []
        active = [item for item in related if item.get("status") in {"dispatched", "running"}]
        reported = [item for item in related if item.get("status") == "reported"]
        if task.get("status") == "running" and len(active) != 1:
            errors.append(f"running task lacks active durable dispatch: {task_id}")
        if task.get("status") in {"verify_failed", "passed", "merged"} and (not reported or active):
            errors.append(f"completed task lacks reported durable dispatch: {task_id}")
    return errors


def validate_cross_file_invariants(state_path: Path, registry_path: Path) -> list[str]:
    try:
        state = load_object(state_path)
        registry = load_object(registry_path)
    except ValueError:
        return []
    errors: list[str] = []
    tasks = state.get("tasks")
    if not isinstance(tasks, list):
        tasks = []
    task_statuses = {
        str(item.get("id")): item.get("status")
        for item in tasks if isinstance(item, dict)
    }
    stages = state.get("stages")
    if not isinstance(stages, list):
        stages = []
    for stage in stages:
        if not isinstance(stage, dict) or stage.get("status") not in {"passed", "merged"}:
            continue
        linked = stage.get("tasks")
        incomplete = [
            str(task_id) for task_id in linked if task_statuses.get(str(task_id)) not in {"passed", "merged"}
        ] if isinstance(linked, list) else []
        if incomplete:
            errors.append(
                f"passed stage has incomplete tasks: {stage.get('id', '?')}: " + ", ".join(incomplete)
            )

    errors.extend(validate_dispatch_coverage(state))

    if state.get("status") not in {"accepted", "handed_off"}:
        return errors
    errors.extend(state_witness_gate(state_path.parent, state, require_review=True))
    criteria = registry.get("criteria")
    if not isinstance(criteria, list):
        return errors
    unresolved = [
        str(item.get("id") or "?")
        for item in criteria if isinstance(item, dict)
        if item.get("status") not in {"pass", "scoped_out"}
    ]
    if unresolved:
        errors.append("accepted run has unresolved acceptance: " + ", ".join(unresolved))
    incomplete_tasks = [
        str(item.get("id") or "?")
        for item in tasks if isinstance(item, dict)
        if item.get("status") not in {"passed", "merged"}
    ]
    if incomplete_tasks:
        errors.append("accepted run has incomplete tasks: " + ", ".join(incomplete_tasks))
    incomplete_stages = [
        str(item.get("id") or "?")
        for item in stages if isinstance(item, dict)
        if item.get("status") not in {"passed", "merged"}
    ]
    if incomplete_stages:
        errors.append("accepted run has incomplete stages: " + ", ".join(incomplete_stages))
    return errors


def validate_active_tdd_gates(
    artifact_dir: Path,
    state: dict[str, object],
    registry: dict[str, object],
) -> list[str]:
    def gate_satisfies(required_mode: str, actual_mode: str) -> bool:
        if actual_mode == required_mode:
            return True
        return required_mode == "test_first_evidence" and actual_mode == "strict_tdd"

    required_modes: dict[str, str] = {}
    tasks = state.get("tasks")
    for item in tasks if isinstance(tasks, list) else []:
        if isinstance(item, dict) and item.get("status") in {"passed", "merged"}:
            gate = item.get("verification_gate")
            task_id = str(item.get("id") or "").strip()
            mode = str(gate.get("mode") or "") if isinstance(gate, dict) else ""
            if task_id and mode in {"strict_tdd", "test_first_evidence"}:
                required_modes[task_id] = mode
    criteria = registry.get("criteria")
    for item in criteria if isinstance(criteria, list) else []:
        if isinstance(item, dict) and item.get("status") == "pass":
            gate = item.get("verification_gate")
            mode = str(gate.get("mode") or "") if isinstance(gate, dict) else ""
            if mode not in {"strict_tdd", "test_first_evidence"}:
                continue
            linked_tasks = item.get("linked_tasks")
            if isinstance(linked_tasks, list) and linked_tasks:
                for task_id in linked_tasks:
                    existing_mode = required_modes.get(str(task_id))
                    if existing_mode and not gate_satisfies(mode, existing_mode):
                        return [f"tdd_trace.jsonl: conflicting gate mode for task {task_id}"]
                    if not existing_mode:
                        required_modes[str(task_id)] = mode
    if not required_modes:
        return []
    trace_path = artifact_dir / "tdd_trace.jsonl"
    errors: list[str] = []
    for task_id, required_mode in sorted(required_modes.items()):
        scoped_events, parse_errors = load_events(trace_path)
        if parse_errors:
            errors.extend(f"tdd_trace.jsonl: {error}" for error in parse_errors)
            continue
        scoped_events = [
            event for event in scoped_events if str(event.data.get("task_id") or "").strip() == task_id
        ]
        gate = latest_gate_decision(scoped_events)
        actual_mode = gate_mode_of(gate) if gate is not None else ""
        if not gate_satisfies(required_mode, actual_mode):
            errors.append(
                f"tdd_trace.jsonl: task {task_id} gate mode must be {required_mode}; got {actual_mode or 'missing'}"
            )
            continue
        errors.extend(
            f"tdd_trace.jsonl task {task_id}: {error}"
            for error in validate_tdd_trace(
                trace_path,
                source_paths=[],
                tolerance_seconds=1.0,
                require_wrapper=True,
                task_id=task_id,
            )
        )
    return errors


def artifact_validation_errors(
    artifact_dir: Path, *, trace_path: Path | None = None
) -> list[str]:
    trace_path = trace_path or artifact_dir / "trace.jsonl"
    errors: list[str] = validate_artifact_dir_binding(artifact_dir)
    validators = (
        (artifact_dir / "run_state.json", validate_run_state),
        (artifact_dir / "acceptance_registry.json", validate_acceptance_registry),
    )
    for path, validator in validators:
        if not path.exists():
            errors.append(f"missing file: {path.name}")
        else:
            errors.extend(validator(path))
    errors.extend(validate_jsonl(trace_path))
    errors.extend(validate_jsonl(artifact_dir / "tdd_trace.jsonl"))
    errors.extend(validate_trace_transactions(trace_path))
    errors.extend(validate_transaction_digest_chain(trace_path))
    errors.extend(validate_canonical_state_digests(artifact_dir, trace_path))
    lesson_records, lesson_errors = validate_lesson_ledger(artifact_dir)
    errors.extend(lesson_errors)
    errors.extend(validate_lesson_trace(artifact_dir, lesson_records))
    errors.extend(validate_evidence_receipts(artifact_dir, trace_path))
    errors.extend(validate_cross_file_invariants(artifact_dir / "run_state.json", artifact_dir / "acceptance_registry.json"))
    if not errors:
        state = load_object(artifact_dir / "run_state.json")
        registry = load_object(artifact_dir / "acceptance_registry.json")
        errors.extend(validate_active_tdd_gates(artifact_dir, state, registry))
    return errors


def record_lesson(args: argparse.Namespace) -> int:
    artifact_dir = args.artifact_dir.expanduser().resolve()
    with locked(artifact_dir / ".harnessctl"):
        ensure_trace_integrity(artifact_dir)
        state = load_object(artifact_dir / "run_state.json")
        require_current_owner(state, args.actor_id, args.owner_epoch)
        existing, errors = validate_lesson_ledger(artifact_dir)
        if errors:
            raise ValueError("lesson ledger is invalid: " + "; ".join(errors))
        lesson_id = validate_actor(args.lesson_id or str(uuid.uuid4()), "lesson id")
        if any(str(item.get("id")) == lesson_id for item in existing):
            raise ValueError(f"lesson id already exists: {lesson_id}")
        evidence: list[dict[str, object]] = []
        for value in args.evidence_file:
            path, normalized = artifact_evidence_path(artifact_dir, value)
            evidence.append(
                {
                    "path": normalized,
                    "sha256": sha256(path.read_bytes()),
                    "size_bytes": path.stat().st_size,
                }
            )
        record = {
            "schema_version": 1,
            "id": lesson_id,
            "recorded_at": utc_now(),
            "status": "verified",
            "verification_tier": args.verification_tier,
            "source_case": args.source_case.strip(),
            "category": args.category.strip(),
            "symptom": args.symptom.strip(),
            "root_cause": args.root_cause.strip(),
            "fix": args.fix.strip(),
            "verification": args.verification.strip(),
            "reusable_rule": args.reusable_rule.strip(),
            "verified_by": args.actor_id.strip(),
            "evidence": evidence,
        }
        if not all(record[key] for key in ("source_case", "category", "symptom", "root_cause", "fix", "verification", "reusable_rule")):
            raise ValueError("lesson fields must not be empty")
        line_bytes = (json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n").encode("utf-8")
        append_jsonl(lesson_ledger_path(artifact_dir), record, writer_role="manager", scope="global")
        append_jsonl(
            artifact_dir / "trace.jsonl",
            {
                "event": "lesson_recorded",
                "lesson_id": lesson_id,
                "lesson_sha256": sha256(line_bytes),
                "source_case": args.source_case.strip(),
                "verification_tier": args.verification_tier,
            },
            writer_role="manager",
            scope="global",
        )
        print(f"lesson_recorded={lesson_id}")
    return 0


def validate_artifact(args: argparse.Namespace) -> int:
    artifact_dir = args.artifact_dir.expanduser().resolve()
    contract_path = artifact_dir if artifact_dir.is_file() else artifact_dir / "contract.json"
    if contract_path.is_file() and contract_path.name == "contract.json":
        errors = validate_portable_artifact_path(contract_path)
        if errors:
            print(f"FAIL {contract_path.parent}")
            for error in errors:
                print(f"- {error}")
            return 1
        print(f"PASS {contract_path.parent}")
        return 0
    errors = artifact_validation_errors(artifact_dir)
    if errors:
        print(f"FAIL {artifact_dir}")
        for error in errors:
            print(f"- {error}")
        return 1
    print(f"PASS {artifact_dir}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Guarded Portable and Audited Harness state control.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    materialize_parser = subparsers.add_parser(
        "materialize", help="Compile an approved native plan into a minimal Portable Contract."
    )
    materialize_parser.add_argument("project_root", type=Path)
    materialize_parser.add_argument("--title", required=True)
    materialize_parser.add_argument("--slug", default="")
    materialize_parser.add_argument("--goal", required=True)
    materialize_parser.add_argument("--done-when", action="append", required=True)
    materialize_parser.add_argument("--non-goal", action="append", default=[])
    materialize_parser.add_argument("--constraint", action="append", default=[])
    materialize_parser.add_argument("--current-milestone", default="")
    materialize_parser.add_argument("--next-action", required=True)
    materialize_parser.add_argument("--required-capability", action="append", default=[])
    materialize_parser.add_argument("--optional-capability", action="append", default=[])
    materialize_parser.add_argument("--must-read", action="append", default=[])
    materialize_parser.add_argument("--read-if-needed", action="append", default=[])
    materialize_parser.add_argument("--max-chars", type=int, default=DEFAULT_CAPSULE_MAX_CHARS)
    materialize_parser.set_defaults(handler=materialize_portable)

    pack_parser = subparsers.add_parser("pack", help="Regenerate a bounded Portable resume capsule.")
    pack_parser.add_argument("path", type=Path)
    pack_parser.add_argument("--run", default="")
    pack_parser.add_argument("--max-chars", type=int, default=DEFAULT_CAPSULE_MAX_CHARS)
    pack_parser.set_defaults(handler=pack_portable)

    close_parser = subparsers.add_parser("close", help="Close a Portable Contract with a terminal status.")
    close_parser.add_argument("path", type=Path)
    close_parser.add_argument("--run", default="")
    close_parser.add_argument("--status", choices=sorted(PORTABLE_TERMINAL_STATUSES), required=True)
    close_parser.add_argument("--actor-id", required=True)
    close_parser.add_argument("--owner-epoch", type=int, required=True)
    close_parser.add_argument("--reason", required=True)
    close_parser.add_argument("--evidence-file", action="append", default=[])
    close_parser.set_defaults(handler=close_portable)

    validate_parser = subparsers.add_parser("validate", help="Validate protocol JSON and JSONL files.")
    validate_parser.add_argument("artifact_dir", type=Path)
    validate_parser.set_defaults(handler=validate_artifact)

    lesson_parser = subparsers.add_parser(
        "lesson-add", help="Record an evidence-backed, reusable lesson in the current Full run."
    )
    lesson_parser.add_argument("artifact_dir", type=Path)
    lesson_parser.add_argument("--lesson-id", default="")
    lesson_parser.add_argument("--source-case", required=True)
    lesson_parser.add_argument("--category", required=True)
    lesson_parser.add_argument("--symptom", required=True)
    lesson_parser.add_argument("--root-cause", required=True)
    lesson_parser.add_argument("--fix", required=True)
    lesson_parser.add_argument("--verification", required=True)
    lesson_parser.add_argument("--reusable-rule", required=True)
    lesson_parser.add_argument("--verification-tier", choices=VERIFICATION_TIERS, default="flow")
    lesson_parser.add_argument("--evidence-file", action="append", required=True)
    lesson_parser.add_argument("--actor-id", required=True)
    lesson_parser.add_argument("--owner-epoch", type=int)
    lesson_parser.set_defaults(handler=record_lesson)

    discover_parser = subparsers.add_parser(
        "discover", help="Discover active Audited or legacy Full runs."
    )
    discover_parser.add_argument("path", type=Path)
    discover_parser.add_argument("--run", default="")
    discover_parser.set_defaults(handler=discover_runs)

    checkpoint_parser = subparsers.add_parser("checkpoint", help="Persist a resumable continuation checkpoint.")
    checkpoint_parser.add_argument("path", type=Path)
    checkpoint_parser.add_argument("--run", default="")
    checkpoint_parser.add_argument("--runtime", required=True)
    checkpoint_parser.add_argument("--actor-id", required=True)
    checkpoint_parser.add_argument("--owner-epoch", type=int)
    checkpoint_parser.add_argument("--current-task", default="")
    checkpoint_parser.add_argument("--next-action", required=True)
    checkpoint_parser.add_argument("--pending-verification", action="append", default=[])
    checkpoint_parser.add_argument("--clear-pending-verification", action="store_true")
    checkpoint_parser.add_argument("--completed", action="append", default=[])
    checkpoint_parser.add_argument("--blocker", action="append", default=[])
    checkpoint_parser.add_argument("--resolve-blocker", action="append", default=[])
    checkpoint_parser.add_argument("--decision", default="")
    checkpoint_parser.add_argument("--decision-reason", default="")
    checkpoint_parser.add_argument("--evidence-file", action="append", default=[])
    checkpoint_parser.add_argument("--max-chars", type=int, default=DEFAULT_CAPSULE_MAX_CHARS)
    checkpoint_parser.add_argument("--reason", required=True)
    checkpoint_parser.set_defaults(handler=checkpoint_run)

    handoff_parser = subparsers.add_parser("handoff", help="Mark a checkpoint ready for another runtime.")
    handoff_parser.add_argument("path", type=Path)
    handoff_parser.add_argument("--run", default="")
    handoff_parser.add_argument("--actor-id", required=True)
    handoff_parser.add_argument("--owner-epoch", type=int)
    handoff_parser.add_argument("--next-action", required=True)
    handoff_parser.add_argument("--pending-verification", action="append", default=[])
    handoff_parser.add_argument("--reason", required=True)
    handoff_parser.set_defaults(handler=handoff_run)

    resume_parser = subparsers.add_parser("resume", help="Validate, recover, claim, and emit a resume packet.")
    resume_parser.add_argument("path", type=Path)
    resume_parser.add_argument("--run", default="")
    resume_parser.add_argument("--runtime", required=True)
    resume_parser.add_argument("--actor-id", required=True)
    resume_parser.add_argument("--owner-epoch", type=int)
    resume_parser.add_argument("--takeover-reason", default="")
    resume_parser.set_defaults(handler=resume_run)

    seal_parser = subparsers.add_parser("seal", help="Authorize and bind pre-dispatch human-authored state.")
    seal_parser.add_argument("artifact_dir", type=Path)
    seal_parser.add_argument("--reason", required=True)
    seal_parser.add_argument("--actor-id", default="")
    seal_parser.add_argument("--owner-epoch", type=int)
    seal_parser.set_defaults(handler=seal_artifact)

    task_parser = subparsers.add_parser("task-set", help="Apply a guarded task status transition.")
    task_parser.add_argument("artifact_dir", type=Path)
    task_parser.add_argument("--task-id", required=True)
    task_parser.add_argument("--status", required=True, choices=sorted(TASK_STATUSES))
    task_parser.add_argument("--evidence", action="append", default=[])
    task_parser.add_argument("--evidence-file", action="append", default=[])
    task_parser.add_argument("--stop-reason", default="")
    task_parser.add_argument("--no-test-reason", default="")
    task_parser.add_argument("--actor-id", default="")
    task_parser.add_argument("--owner-epoch", type=int)
    task_parser.set_defaults(handler=task_set)

    task_refresh_parser = subparsers.add_parser(
        "task-refresh", help="Replace receipts for files backing a completed task."
    )
    task_refresh_parser.add_argument("artifact_dir", type=Path)
    task_refresh_parser.add_argument("--task-id", required=True)
    task_refresh_parser.add_argument("--evidence-file", action="append", default=[])
    task_refresh_parser.add_argument("--verification-tier", choices=VERIFICATION_TIERS, default="policy")
    task_refresh_parser.add_argument("--actor-id", default="")
    task_refresh_parser.add_argument("--owner-epoch", type=int)
    task_refresh_parser.set_defaults(handler=task_refresh)

    acceptance_parser = subparsers.add_parser("acceptance-set", help="Apply a guarded acceptance status transition.")
    acceptance_parser.add_argument("artifact_dir", type=Path)
    acceptance_parser.add_argument("--criterion-id", required=True)
    acceptance_parser.add_argument("--status", required=True, choices=sorted(ACCEPTANCE_STATUSES))
    acceptance_parser.add_argument("--evidence", action="append", default=[])
    acceptance_parser.add_argument("--evidence-file", action="append", default=[])
    acceptance_parser.add_argument("--verification-tier", choices=VERIFICATION_TIERS, default="policy")
    acceptance_parser.add_argument("--pass-algorithm", default="")
    acceptance_parser.add_argument("--blocking-issue", action="append", default=[])
    acceptance_parser.add_argument("--no-test-reason", default="")
    acceptance_parser.add_argument("--gate-tdd-trace-path", default="")
    acceptance_parser.add_argument("--gate-red-command", default="")
    acceptance_parser.add_argument("--gate-red-result", default="")
    acceptance_parser.add_argument("--gate-red-failure-reason", default="")
    acceptance_parser.add_argument("--gate-green-command", default="")
    acceptance_parser.add_argument("--gate-green-result", default="")
    acceptance_parser.add_argument("--gate-refactor-check", default="")
    acceptance_parser.add_argument("--gate-substitute-check", default="")
    acceptance_parser.add_argument("--actor-id", default="")
    acceptance_parser.add_argument("--owner-epoch", type=int)
    acceptance_parser.set_defaults(handler=acceptance_set)

    refresh_parser = subparsers.add_parser(
        "acceptance-refresh", help="Replace receipts for files backing an accepted or decisioned criterion."
    )
    refresh_parser.add_argument("artifact_dir", type=Path)
    refresh_parser.add_argument("--criterion-id", required=True)
    refresh_parser.add_argument("--evidence-file", action="append", default=[])
    refresh_parser.add_argument("--verification-tier", choices=VERIFICATION_TIERS, default="policy")
    refresh_parser.add_argument("--actor-id", default="")
    refresh_parser.add_argument("--owner-epoch", type=int)
    refresh_parser.set_defaults(handler=acceptance_refresh)

    run_parser = subparsers.add_parser("run-set", help="Apply a guarded top-level run transition.")
    run_parser.add_argument("artifact_dir", type=Path)
    run_parser.add_argument("--status", required=True, choices=sorted(RUN_STATUSES))
    run_parser.add_argument("--evidence", action="append", default=[])
    run_parser.add_argument("--evidence-file", action="append", default=[])
    run_parser.add_argument("--verification-tier", choices=VERIFICATION_TIERS, default="policy")
    run_parser.add_argument("--stop-reason", default="")
    run_parser.add_argument("--actor-id", default="")
    run_parser.add_argument("--owner-epoch", type=int)
    run_parser.set_defaults(handler=run_set)

    witness_parser = subparsers.add_parser("witness-set", help="Record independent state witness review evidence.")
    witness_parser.add_argument("artifact_dir", type=Path)
    witness_parser.add_argument("--status", required=True, choices=("pass", "fail", "blocked"))
    witness_parser.add_argument("--reviewer-id", default="")
    witness_parser.add_argument("--verification-tier", choices=VERIFICATION_TIERS, default="policy")
    witness_parser.add_argument("--evidence-file", action="append", default=[])
    witness_parser.add_argument("--reason", default="")
    witness_parser.add_argument("--actor-id", default="")
    witness_parser.add_argument("--owner-epoch", type=int)
    witness_parser.set_defaults(handler=witness_set)

    dispatch_create_parser = subparsers.add_parser("dispatch-create", help="Persist a manager-owned worker dispatch.")
    dispatch_create_parser.add_argument("artifact_dir", type=Path)
    dispatch_create_parser.add_argument("--worker-id", required=True)
    dispatch_create_parser.add_argument("--task-id", required=True)
    dispatch_create_parser.add_argument("--contract-path", required=True)
    dispatch_create_parser.add_argument("--report-path", required=True)
    dispatch_create_parser.add_argument("--runtime", default="universal")
    dispatch_create_parser.add_argument("--profile", choices=sorted(AGENT_PROFILES), default="main")
    dispatch_create_parser.add_argument("--requested-model", default="")
    dispatch_create_parser.add_argument("--resolved-model", default="")
    dispatch_create_parser.add_argument("--reasoning-effort", default="")
    dispatch_create_parser.add_argument("--route-reason", default="")
    dispatch_create_parser.add_argument("--escalation-count", type=int, default=0)
    dispatch_create_parser.add_argument("--actor-id", default="")
    dispatch_create_parser.add_argument("--owner-epoch", type=int)
    dispatch_create_parser.set_defaults(handler=dispatch_create)

    dispatch_update_parser = subparsers.add_parser("dispatch-update", help="Advance a persisted worker dispatch lifecycle.")
    dispatch_update_parser.add_argument("artifact_dir", type=Path)
    dispatch_update_parser.add_argument("--dispatch-id", required=True)
    dispatch_update_parser.add_argument("--status", required=True, choices=sorted(DISPATCH_STATUSES - {"dispatched"}))
    dispatch_update_parser.add_argument("--stop-reason", default="")
    dispatch_update_parser.add_argument("--actor-id", default="")
    dispatch_update_parser.add_argument("--owner-epoch", type=int)
    dispatch_update_parser.set_defaults(handler=dispatch_update)

    recover_parser = subparsers.add_parser("recover", help="Reconcile interrupted journaled transitions.")
    recover_parser.add_argument("artifact_dir", type=Path)
    recover_parser.add_argument("--actor-id", default="")
    recover_parser.add_argument("--owner-epoch", type=int)
    recover_parser.set_defaults(handler=recover_artifact)
    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    try:
        return int(args.handler(args))
    except (OSError, ValueError, PermissionError) as exc:
        print(f"ERROR {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
