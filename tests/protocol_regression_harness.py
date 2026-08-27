#!/usr/bin/env python3
"""Run adversarial, runtime-neutral regression cases for the harness protocol.

The static skill scorer checks that protocol words and files exist. This harness
executes the rejection boundaries that have historically been easy to fake:
TDD chronology, gate downgrades, wrapper provenance, and semantic Markdown
validation. It intentionally uses only the Python standard library.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import tempfile
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Callable


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
TESTS_ROOT = REPOSITORY_ROOT / "tests"
LEGACY_TEMPLATES = REPOSITORY_ROOT / "docs" / "legacy" / "templates"


@dataclass
class CaseResult:
    name: str
    status: str
    detail: str


def load_modules(skill_root: Path):
    scripts = skill_root / "scripts"
    sys.path.insert(0, str(scripts))
    import tdd_gate_check  # type: ignore
    import harness_test_run  # type: ignore
    import validate_report  # type: ignore
    import status  # type: ignore

    return tdd_gate_check, harness_test_run, validate_report, status


def trace_event(event: str, **fields: object) -> dict[str, object]:
    return {"event": event, **fields}


def write_trace(path: Path, events: list[dict[str, object]]) -> None:
    path.write_text(
        "".join(json.dumps(event, ensure_ascii=False) + "\n" for event in events),
        encoding="utf-8",
    )


def expect_errors(errors: list[str], needle: str) -> None:
    if not errors:
        raise AssertionError(f"expected rejection containing {needle!r}, got PASS")
    if not any(needle.casefold() in error.casefold() for error in errors):
        raise AssertionError(f"rejection did not mention {needle!r}: {errors}")


def expect_pass(errors: list[str]) -> None:
    if errors:
        raise AssertionError("expected PASS, got: " + "; ".join(errors))


def test_first_red_must_precede_edit(tdd, tmp: Path) -> None:
    trace = tmp / "post-fix-red.jsonl"
    write_trace(
        trace,
        [
            trace_event("gate_decision", gate_mode="test_first_evidence", reason="behavior change"),
            trace_event("file_modified", path="src/retry.py"),
            trace_event(
                "test_run",
                phase="RED",
                result="FAIL",
                source="harness_test_run",
                stderr_tail="expected retry but got immediate failure",
            ),
            trace_event("test_run", phase="GREEN", result="PASS", source="harness_test_run"),
        ],
    )
    expect_errors(tdd.validate_trace(trace, source_paths=[], tolerance_seconds=1.0), "before")


def test_gate_cannot_downgrade(tdd, tmp: Path) -> None:
    trace = tmp / "gate-downgrade.jsonl"
    write_trace(
        trace,
        [
            trace_event("gate_decision", gate_mode="strict_tdd", reason="bug fix"),
            trace_event(
                "test_run",
                phase="RED",
                result="FAIL",
                source="harness_test_run",
                stderr_tail="reproduction fails",
            ),
            trace_event("gate_decision", gate_mode="not_applicable", reason="ignore the test"),
        ],
    )
    expect_errors(tdd.validate_trace(trace, source_paths=[], tolerance_seconds=1.0), "gate")


def test_gap_evidence_must_precede_edit(tdd, tmp: Path) -> None:
    trace = tmp / "post-fix-gap.jsonl"
    write_trace(
        trace,
        [
            trace_event("gate_decision", gate_mode="test_first_evidence", reason="behavior change"),
            trace_event("file_modified", path="src/retry.py"),
            trace_event(
                "test_run",
                phase="GAP",
                result="PASS",
                source="harness_test_run",
                gap_evidence="existing test did not cover retry exhaustion",
            ),
            trace_event("test_run", phase="GREEN", result="PASS", source="harness_test_run"),
        ],
    )
    expect_errors(tdd.validate_trace(trace, source_paths=[], tolerance_seconds=1.0), "before")


def test_cross_task_evidence_isolated(tdd, tmp: Path) -> None:
    trace = tmp / "cross-task-splice.jsonl"
    write_trace(
        trace,
        [
            trace_event("gate_decision", gate_mode="test_first_evidence", reason="task A", task_id="A"),
            trace_event(
                "test_run",
                phase="RED",
                result="FAIL",
                source="harness_test_run",
                stderr_tail="task A reproduction fails",
                task_id="A",
            ),
            trace_event("file_modified", path="src/a.py", task_id="A"),
            trace_event("test_run", phase="GREEN", result="PASS", source="harness_test_run", task_id="B"),
        ],
    )
    expect_errors(
        tdd.validate_trace(trace, source_paths=[], tolerance_seconds=1.0, task_id="A"),
        "GREEN",
    )


def test_protected_gate_rejects_handwritten_trace(tdd, tmp: Path) -> None:
    trace = tmp / "handwritten.jsonl"
    write_trace(
        trace,
        [
            trace_event("gate_decision", gate_mode="test_first_evidence", reason="behavior change"),
            trace_event(
                "test_run",
                phase="RED",
                result="FAIL",
                source="worker_report",
                stderr_tail="reproduction fails",
            ),
            trace_event("file_modified", path="src/retry.py"),
            trace_event("test_run", phase="GREEN", result="PASS", source="worker_report"),
        ],
    )
    expect_errors(
        tdd.validate_trace(trace, source_paths=[], tolerance_seconds=1.0, require_wrapper=True),
        "wrapper",
    )


def test_wrapper_trace_remains_valid(tdd, tmp: Path) -> None:
    trace = tmp / "wrapper-valid.jsonl"
    write_trace(
        trace,
        [
            trace_event("gate_decision", gate_mode="strict_tdd", reason="bug fix"),
            trace_event(
                "test_run",
                phase="RED",
                result="FAIL",
                source="harness_test_run",
                stderr_tail="reproduction fails",
            ),
            trace_event("file_modified", path="src/retry.py"),
            trace_event("test_run", phase="GREEN", result="PASS", source="harness_test_run"),
            trace_event("test_run", phase="REFACTOR", result="PASS", source="harness_test_run"),
        ],
    )
    expect_pass(tdd.validate_trace(trace, source_paths=[], tolerance_seconds=1.0, require_wrapper=True))


def test_red_needs_failure_context(tdd, tmp: Path) -> None:
    trace = tmp / "empty-red.jsonl"
    write_trace(
        trace,
        [
            trace_event("gate_decision", gate_mode="strict_tdd", reason="bug fix"),
            trace_event("test_run", phase="RED", result="FAIL", source="harness_test_run"),
            trace_event("file_modified", path="src/retry.py"),
            trace_event("test_run", phase="GREEN", result="PASS", source="harness_test_run"),
            trace_event("test_run", phase="REFACTOR", result="PASS", source="harness_test_run"),
        ],
    )
    expect_errors(tdd.validate_trace(trace, source_paths=[], tolerance_seconds=1.0), "failure")


def test_wrapper_updates_gate_record(wrapper, tmp: Path) -> None:
    state_path = tmp / "wrapper-state.json"
    gate = {
        "mode": "test_first_evidence",
        "tdd_trace_path": "",
        "red_command": "",
        "red_result": "",
        "red_failure_reason": "",
        "green_command": "",
        "green_result": "",
        "refactor_check": "",
        "substitute_check": "",
        "no_test_reason": "",
    }
    state_path.write_text(
        json.dumps({"mode": "lite", "tasks": [{"id": "1.1", "verification_gate": gate}]}),
        encoding="utf-8",
    )
    wrapper.update_run_state(
        state_path,
        task_id="1.1",
        gate_mode="test_first_evidence",
        phase="RED",
        command="pytest tests/repro.py",
        result="FAIL",
        exit_code=1,
        trace_path=tmp / "tdd_trace.jsonl",
        stdout_tail="",
        stderr_tail="expected failure",
        summary="reproduction before implementation",
    )
    updated = json.loads(state_path.read_text(encoding="utf-8"))
    updated_gate = updated["tasks"][0]["verification_gate"]
    if updated_gate["red_command"] != "pytest tests/repro.py" or updated_gate["red_result"] != "FAIL":
        raise AssertionError("wrapper did not persist RED gate fields")
    if updated_gate["red_failure_reason"] != "reproduction before implementation":
        raise AssertionError("wrapper did not persist RED failure context")
    if updated_gate["tdd_trace_path"] != "tdd_trace.jsonl":
        raise AssertionError("wrapper did not normalize the trace path")


def test_protected_criterion_requires_task_binding(report, skill_root: Path, tmp: Path) -> None:
    registry = json.loads(
        (LEGACY_TEMPLATES / "acceptance_registry.json").read_text(encoding="utf-8")
    )
    criterion = registry["criteria"][0]
    criterion.update(
        {
            "id": "AC-BOUND",
            "description": "bound criterion",
            "status": "pass",
            "pass_algorithm": "PASS when a wrapper trace proves the behavior.",
            "linked_tasks": [],
            "verification_gate": {
                "mode": "test_first_evidence",
                "tdd_trace_path": "tdd_trace.jsonl",
                "red_command": "pytest tests/repro.py",
                "red_result": "FAIL",
                "red_failure_reason": "expected failure",
                "green_command": "pytest tests/repro.py",
                "green_result": "PASS",
                "refactor_check": "",
                "substitute_check": "",
                "no_test_reason": "",
            },
        }
    )
    path = tmp / "unbound-criterion.json"
    path.write_text(json.dumps(registry), encoding="utf-8")
    expect_errors(report.validate_acceptance_registry(path), "linked_tasks")


def test_terminal_status_hides_stale_checkpoint(status) -> None:
    text = status.format_status(
        {
            "title": "accepted run",
            "mode": "full",
            "status": "accepted",
            "continuation": {
                "status": "unclaimed",
                "owner": {},
                "checkpoint": {
                    "sequence": 0,
                    "current_task": "0.1",
                    "next_action": "stale initialization action",
                },
            },
        }
    )
    if "no resume checkpoint required" not in text or "stale initialization action" in text:
        raise AssertionError("terminal status exposed a stale resume checkpoint")


def run_markdown_case(skill_root: Path, tmp: Path, *, localized: bool) -> None:
    path = tmp / ("localized.md" if localized else "fenced.md")
    if localized:
        content = """# Spec\n\n## 1. 目标\n实现可复验的协议回归。\n## 2. 用户可见结果\n命令输出逐案结果。\n## （二）非目标\n不做多 agent 调度。\n## 约束\n仅用标准库。\n## 3. 验收标准\n所有反例按预期拒绝。\n## 验证证据\n保存 JSON 报告。\n## 风险\nwrapper 标记不是签名。\n## 预算\n单 owner。\n## 停止条件\n重复失败两次即停。\n## 产物位置\nartifact/evidence。\n"""
    else:
        content = """# Spec\n\n```markdown\n## Goal\nplaceholder\n## User-Facing Outcome\nplaceholder\n## Non-Goals\nplaceholder\n## Constraints\nplaceholder\n## Acceptance Criteria\nplaceholder\n## Verification Evidence\nplaceholder\n## Risks\nplaceholder\n## Budget\nplaceholder\n## Stop Conditions\nplaceholder\n## Artifact Location\nplaceholder\n```\n"""
    path.write_text(content, encoding="utf-8")
    command = [
        sys.executable,
        str(skill_root / "scripts" / "validate_report.py"),
        str(path),
        "--type",
        "spec",
        "--require-filled",
    ]
    completed = subprocess.run(command, text=True, capture_output=True, check=False)
    if localized and completed.returncode != 0:
        raise AssertionError("localized numbered spec should pass: " + completed.stdout + completed.stderr)
    if not localized and completed.returncode == 0:
        raise AssertionError("fenced example-only spec should be rejected")


def run_command_check(command: list[str], cwd: Path) -> None:
    completed = subprocess.run(command, cwd=cwd, text=True, capture_output=True, check=False)
    if completed.returncode != 0:
        output = (completed.stdout + completed.stderr).strip()
        raise AssertionError(f"command failed ({completed.returncode}): {' '.join(command)}\n{output}")


def run_case(name: str, fn: Callable[[], None]) -> CaseResult:
    try:
        fn()
    except Exception as exc:  # the report must preserve the exact failing boundary
        return CaseResult(name, "FAIL", str(exc))
    return CaseResult(name, "PASS", "expected acceptance/rejection observed")


def run(skill_root: Path) -> dict[str, object]:
    tdd, wrapper, report_validator, status = load_modules(skill_root)
    results: list[CaseResult] = []
    with tempfile.TemporaryDirectory(prefix="protocol-regression-") as raw_tmp:
        tmp = Path(raw_tmp)
        cases: list[tuple[str, Callable[[], None]]] = [
            ("test_first_red_precedes_edit", lambda: test_first_red_must_precede_edit(tdd, tmp)),
            ("gate_downgrade_rejected", lambda: test_gate_cannot_downgrade(tdd, tmp)),
            ("test_first_gap_precedes_edit", lambda: test_gap_evidence_must_precede_edit(tdd, tmp)),
            ("cross_task_evidence_isolated", lambda: test_cross_task_evidence_isolated(tdd, tmp)),
            ("handwritten_trace_rejected_for_protected_gate", lambda: test_protected_gate_rejects_handwritten_trace(tdd, tmp)),
            ("wrapper_trace_accepted", lambda: test_wrapper_trace_remains_valid(tdd, tmp)),
            ("red_failure_context_required", lambda: test_red_needs_failure_context(tdd, tmp)),
            ("wrapper_updates_gate_record", lambda: test_wrapper_updates_gate_record(wrapper, tmp)),
            (
                "protected_criterion_requires_task_binding",
                lambda: test_protected_criterion_requires_task_binding(report_validator, skill_root, tmp),
            ),
            ("terminal_status_hides_stale_checkpoint", lambda: test_terminal_status_hides_stale_checkpoint(status)),
            ("localized_numbered_spec_accepted", lambda: run_markdown_case(skill_root, tmp, localized=True)),
            ("fenced_example_only_spec_rejected", lambda: run_markdown_case(skill_root, tmp, localized=False)),
            (
                "artifact_binding_tests",
                lambda: run_command_check(
                    [sys.executable, str(TESTS_ROOT / "test_artifact_binding.py")],
                    REPOSITORY_ROOT,
                ),
            ),
            (
                "lesson_ledger_tests",
                lambda: run_command_check(
                    [sys.executable, str(TESTS_ROOT / "test_lessons.py")],
                    REPOSITORY_ROOT,
                ),
            ),
            (
                "model_routing_tests",
                lambda: run_command_check(
                    [sys.executable, str(TESTS_ROOT / "test_model_routing.py")],
                    REPOSITORY_ROOT,
                ),
            ),
            (
                "all_scripts_compile",
                lambda: run_command_check(
                    [sys.executable, "-m", "py_compile", *[str(path) for path in sorted((skill_root / "scripts").glob("*.py"))]],
                    skill_root,
                ),
            ),
        ]
        for name, case in cases:
            results.append(run_case(name, case))

    return {
        "harness": "protocol-regression-v1",
        "skill_root": str(skill_root),
        "cases": [asdict(result) for result in results],
        "passed": sum(result.status == "PASS" for result in results),
        "failed": sum(result.status == "FAIL" for result in results),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Run adversarial protocol regression cases.")
    parser.add_argument("--skill-root", required=True, type=Path)
    parser.add_argument("--out", type=Path, default=None)
    parser.add_argument("--pretty", action="store_true")
    args = parser.parse_args()

    report = run(args.skill_root.expanduser().resolve())
    serialized = json.dumps(report, ensure_ascii=False, indent=2) + "\n"
    if args.out:
        args.out.expanduser().resolve().parent.mkdir(parents=True, exist_ok=True)
        args.out.expanduser().resolve().write_text(serialized, encoding="utf-8")
    if args.pretty or not args.out:
        print(f"protocol_regression passed={report['passed']} failed={report['failed']}")
        for case in report["cases"]:
            mark = "PASS" if case["status"] == "PASS" else "FAIL"
            print(f"  [{mark}] {case['name']}: {case['detail']}")
    else:
        print(serialized, end="")
    return 0 if report["failed"] == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
