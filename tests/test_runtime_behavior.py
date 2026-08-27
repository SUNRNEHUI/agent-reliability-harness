#!/usr/bin/env python3
"""Runtime checks for the current packaged harness contract."""

from __future__ import annotations

import json
import shutil
import subprocess
import tempfile
from pathlib import Path


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
ROOT = REPOSITORY_ROOT / "skills" / "agent-reliability-harness"
PACKAGE_SCRIPT = REPOSITORY_ROOT / "scripts" / "package_skill.py"
LEGACY_TEMPLATES = REPOSITORY_ROOT / "docs" / "legacy" / "templates"


def run(args: list[str], *, check: bool = True) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(
        args,
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )
    if check and result.returncode != 0:
        raise AssertionError(f"command failed: {' '.join(args)}\n{result.stdout}\n{result.stderr}")
    return result


def load_json(path: Path) -> dict[str, object]:
    value = json.loads(path.read_text(encoding="utf-8"))
    assert isinstance(value, dict)
    return value


def init_artifact(temp: Path, *, mode: str, title: str, state_witness: bool = False) -> Path:
    command = [
        "python3",
        "scripts/init_run.py",
        "--mode",
        mode,
        "--project-root",
        str(temp),
        "--title",
        title,
        "--agents",
        "docs,review" if mode in {"audited", "full"} else "",
        "--force",
    ]
    if state_witness:
        command.extend(["--with-state-witness", "--required-verification-tier", "user_visible"])
    run(command)
    return temp / "workspace" / title.replace(" ", "-")


def mark_audited_passed(artifact_dir: Path) -> None:
    """Build a valid accepted fixture through the public controller commands."""
    run(["python3", "scripts/harnessctl.py", "seal", str(artifact_dir), "--reason", "runtime test fixture"])
    state = load_json(artifact_dir / "run_state.json")
    for task in state["tasks"]:
        run(["python3", "scripts/harnessctl.py", "task-set", str(artifact_dir), "--task-id", str(task["id"]), "--status", "ready"])
    for status in ("gated", "specified", "dispatched"):
        run(["python3", "scripts/harnessctl.py", "run-set", str(artifact_dir), "--status", status])

    state = load_json(artifact_dir / "run_state.json")
    for task in state["tasks"]:
        task_id = str(task["id"])
        report_path = artifact_dir / str(task["report_path"])
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report_path.write_text(f"# Report {task_id}\n\nRuntime fixture evidence.\n", encoding="utf-8")
        run(
            [
                "python3",
                "scripts/harnessctl.py",
                "dispatch-create",
                str(artifact_dir),
                "--worker-id",
                f"worker-{task_id}",
                "--task-id",
                task_id,
                "--contract-path",
                str(task["task_path"]),
                "--report-path",
                str(task["report_path"]),
            ]
        )
        state = load_json(artifact_dir / "run_state.json")
        dispatch = next(
            item
            for item in state["state_layers"]["session_state"]["delegation_state"]
            if item["task_id"] == task_id
        )
        run(
            [
                "python3",
                "scripts/harnessctl.py",
                "dispatch-update",
                str(artifact_dir),
                "--dispatch-id",
                str(dispatch["dispatch_id"]),
                "--status",
                "reported",
            ]
        )
        run(["python3", "scripts/harnessctl.py", "task-set", str(artifact_dir), "--task-id", task_id, "--status", "running"])
        run(
            [
                "python3",
                "scripts/harnessctl.py",
                "task-set",
                str(artifact_dir),
                "--task-id",
                task_id,
                "--status",
                "passed",
                "--evidence-file",
                "progress.md",
                "--no-test-reason",
                "runtime fixture uses substitute verification",
            ]
        )

    run(
        [
            "python3",
            "scripts/harnessctl.py",
            "acceptance-set",
            str(artifact_dir),
            "--criterion-id",
            "AC-001",
            "--status",
            "pass",
            "--evidence-file",
            "progress.md",
            "--pass-algorithm",
            "runtime fixture reaches accepted state",
            "--no-test-reason",
            "runtime fixture uses substitute verification",
        ]
    )
    for status in ("reported", "evaluating"):
        run(["python3", "scripts/harnessctl.py", "run-set", str(artifact_dir), "--status", status])
    run(["python3", "scripts/harnessctl.py", "run-set", str(artifact_dir), "--status", "accepted", "--evidence-file", "progress.md"])


def test_progress_template_is_lightweight() -> None:
    text = (ROOT / "templates" / "progress_ledger.md").read_text(encoding="utf-8")
    headings = {line[3:].strip() for line in text.splitlines() if line.startswith("## ")}
    assert len(text.splitlines()) <= 35
    assert not headings.intersection({"Run State", "Working State", "Session State", "Execution Log", "Task Ledger"})


def test_lite_init_is_minimal_and_state_witness_is_opt_in() -> None:
    temp = Path(tempfile.mkdtemp(prefix="adh-test-lite-"))
    try:
        artifact = init_artifact(temp, mode="lite", title="lite behavior")
        assert sorted(str(path.relative_to(artifact)) for path in artifact.rglob("*") if path.is_file()) == [
            "lite_plan.md",
            "run_state.json",
        ]
        state = load_json(artifact / "run_state.json")
        assert state["state_witness"]["required"] is False

        stateful = init_artifact(temp, mode="lite", title="lite stateful", state_witness=True)
        state = load_json(stateful / "run_state.json")
        assert state["state_witness"]["required"] is True
        assert (stateful / "state_witness.md").is_file()
    finally:
        shutil.rmtree(temp)


def test_audited_lifecycle_reaches_high_confidence() -> None:
    temp = Path(tempfile.mkdtemp(prefix="arh-test-audited-"))
    try:
        artifact = init_artifact(temp, mode="audited", title="high confidence")
        assert load_json(artifact / "run_state.json")["mode"] == "audited"
        mark_audited_passed(artifact)
        result = run(["python3", "scripts/status.py", str(artifact / "run_state.json")])
        assert "Acceptance: 1 pass, 0 pending, 0 fail, 0 blocked, 0 scoped_out" in result.stdout
        assert "Completion confidence: high" in result.stdout
        assert "Integrity errors: none" in result.stdout
        strict = run(
            [
                "python3",
                "scripts/status.py",
                str(artifact / "run_state.json"),
                "--require-high-confidence",
            ]
        )
        assert "Status gate:" not in strict.stdout
        strict_json = run(
            [
                "python3",
                "scripts/status.py",
                str(artifact / "run_state.json"),
                "--json",
                "--require-high-confidence",
            ]
        )
        strict_payload = json.loads(strict_json.stdout)
        assert isinstance(strict_payload, dict)
        assert strict_payload["completion_confidence"] == "high"
    finally:
        shutil.rmtree(temp)


def test_legacy_full_cli_alias_writes_current_audited_mode() -> None:
    temp = Path(tempfile.mkdtemp(prefix="arh-test-full-alias-"))
    try:
        artifact = init_artifact(temp, mode="full", title="legacy alias")
        assert load_json(artifact / "run_state.json")["mode"] == "audited"
    finally:
        shutil.rmtree(temp)


def test_integrity_breaker_prevents_high_confidence() -> None:
    temp = Path(tempfile.mkdtemp(prefix="adh-test-integrity-"))
    try:
        artifact = init_artifact(temp, mode="audited", title="integrity breaker")
        state_path = artifact / "run_state.json"
        state = load_json(state_path)
        state["status"] = "accepted"
        state_path.write_text(json.dumps(state, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        result = run(["python3", "scripts/status.py", str(state_path)])
        assert "Integrity errors:" in result.stdout
        assert "Completion confidence: high" not in result.stdout
    finally:
        shutil.rmtree(temp)


def test_negative_validator_and_package_check() -> None:
    temp = Path(tempfile.mkdtemp(prefix="adh-test-package-"))
    try:
        bad_review = temp / "lite_review.md"
        bad_review.write_text(
            (LEGACY_TEMPLATES / "lite_review.md").read_text(encoding="utf-8").replace("blocked", "maybe"),
            encoding="utf-8",
        )
        result = run(["python3", "scripts/validate_report.py", str(bad_review), "--type", "lite_review"], check=False)
        assert result.returncode != 0
        assert "status must be one of" in result.stdout

        package_dir = temp / "pkg"
        run(["python3", str(PACKAGE_SCRIPT), "--output", str(package_dir), "--force"])
        (package_dir / "EXTRA").write_text("x", encoding="utf-8")
        result = run(["python3", str(PACKAGE_SCRIPT), "--check", str(package_dir)], check=False)
        assert result.returncode != 0
        assert "extra in install: EXTRA" in result.stdout
        (package_dir / "EXTRA").unlink()
        (package_dir / "workspace" / "preserved-run").mkdir(parents=True)
        (package_dir / "workspace" / "preserved-run" / "run_state.json").write_text(
            "{}\n", encoding="utf-8"
        )
        result = run(["python3", str(PACKAGE_SCRIPT), "--check", str(package_dir)], check=False)
        assert result.returncode == 0, result.stdout + result.stderr
    finally:
        shutil.rmtree(temp)


def test_runtime_package_contains_state_witness_runtime() -> None:
    temp = Path(tempfile.mkdtemp(prefix="adh-test-witness-package-"))
    try:
        package_dir = temp / "pkg"
        run(["python3", str(PACKAGE_SCRIPT), "--output", str(package_dir), "--force"])
        for relative in (
            "references/state-witness.md",
            "scripts/state_witness_check.py",
            "templates/state_witness.md",
        ):
            assert (package_dir / relative).is_file(), relative
    finally:
        shutil.rmtree(temp)


def test_parallel_package_checks_use_isolated_temp_dirs() -> None:
    temp = Path(tempfile.mkdtemp(prefix="adh-test-parallel-package-"))
    try:
        package_dir = temp / "pkg"
        run(["python3", str(PACKAGE_SCRIPT), "--output", str(package_dir), "--force"])
        command = ["python3", str(PACKAGE_SCRIPT), "--check", str(package_dir)]
        processes = [
            subprocess.Popen(
                command,
                cwd=ROOT,
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )
            for _ in range(8)
        ]
        results = [process.communicate() + (process.returncode,) for process in processes]
        failures = [stdout + stderr for stdout, stderr, returncode in results if returncode]
        assert not failures, "\n".join(failures)
    finally:
        shutil.rmtree(temp)


def test_trigger_shortcuts_run_the_mode_gate_without_forcing_work() -> None:
    skill = (ROOT / "SKILL.md").read_text(encoding="utf-8").lower()
    normalized_skill = " ".join(skill.split())
    default_prompt = (ROOT / "agents" / "openai.yaml").read_text(encoding="utf-8").lower()

    for trigger in ("你是主 agent", "写一个 harness"):
        assert trigger in normalized_skill
    for mode in ("native", "portable", "audited"):
        assert mode in default_prompt
    assert "mode gate" in normalized_skill
    assert "delegation is independent of mode" in normalized_skill
    assert "ordinary implementation, planning, and testing" in normalized_skill
    assert "do not load references" in normalized_skill
    assert "create harness files" in normalized_skill
    assert "v3 micro work may stay on the parent/main" in normalized_skill
    assert "ordinary or execution-heavy work uses one bounded" in normalized_skill
    assert "explicit user delegation overrides the micro direct route" in normalized_skill
    assert "try another verifiable bounded worker first" in normalized_skill
    assert "if none exists or resolution fails, block" in normalized_skill
    assert "explicit user authorization" in normalized_skill
    assert "$agent-reliability-harness" in default_prompt


def test_optional_model_routing_policy_is_present() -> None:
    routing = (ROOT / "references" / "model-routing.md").read_text(encoding="utf-8")
    adapter = (ROOT / "adapters" / "codex.md").read_text(encoding="utf-8")
    normalized_adapter = " ".join(adapter.split())
    metadata = (ROOT / "agents" / "openai.yaml").read_text(encoding="utf-8")
    for term in (
        "gpt-5.6-luna",
        "gpt-5.6-sol",
        "Luna `max`",
        "Sol `high`",
        "bounded Sol",
        "progress-bounded-v3",
        "progress-bounded-v2",
        "--routing-policy progress-bounded-v2",
        "block implementation",
        "explicit user authorization",
    ):
        assert term in routing
    assert "gpt-5.6-luna" in adapter
    assert "progress circuit breaker" in adapter.casefold()
    assert "Model routing does not authorize delegation" in routing
    assert "Delegation is independent of mode" in routing
    assert "implementation work" in routing.casefold()
    assert "--micro-implementation" in routing
    assert "no-protected-boundary" in routing
    assert "auditable routing assertions" in routing
    assert "cost-aware-v1" in routing
    assert "bounded mechanical route" in routing.casefold()
    assert "serial" in routing.casefold()
    assert "recursive" in routing.casefold()
    for text in (routing, adapter, metadata):
        assert "luna_worker" in text
    assert "fork_turns=none" in adapter
    assert "self-contained" in adapter
    assert "another verifiable bounded worker" in normalized_adapter
    assert "Parent direct execution requires explicit user authorization" in normalized_adapter
    assert "micro implementation" in normalized_adapter.casefold()
    assert "active Native thread" not in adapter
    assert "when configured" in metadata.casefold()


def test_progress_circuit_breaker_is_in_the_skill_entry() -> None:
    skill = (ROOT / "SKILL.md").read_text(encoding="utf-8")
    normalized_skill = " ".join(skill.split())
    for term in ("Progress Circuit Breaker", "STALLED", "falsifying experiment"):
        assert term in normalized_skill
    assert "must not increase reasoning effort" in normalized_skill


def test_plan_native_entry_is_lean_and_provider_neutral() -> None:
    skill = (ROOT / "SKILL.md").read_text(encoding="utf-8")
    metadata = (ROOT / "agents" / "openai.yaml").read_text(encoding="utf-8")

    assert len(skill.split()) <= 750
    for term in ("Native", "Portable", "Audited", "materialize", "capsule"):
        assert term in skill
    for provider_slug in ("gpt-5.6-luna", "gpt-5.6-sol", "grok-api"):
        assert provider_slug not in skill
    assert "Direct / Lite / Full" not in skill
    assert len(metadata.split()) <= 120
    assert "$agent-reliability-harness" in metadata
    for term in ("Native", "Portable", "Audited"):
        assert term in metadata


def test_runtime_model_maps_are_outside_core_schema() -> None:
    schema = (ROOT / "scripts" / "harness_schema.py").read_text(encoding="utf-8")
    profiles = (ROOT / "scripts" / "runtime_profiles.py").read_text(encoding="utf-8")
    router = (ROOT / "scripts" / "model_router.py").read_text(encoding="utf-8")
    for provider_slug in ("gpt-5.6-luna", "gpt-5.6-sol", "grok-api"):
        assert provider_slug not in schema
        assert provider_slug in profiles
    assert "from runtime_profiles import" in router
    assert "--implementation" in router


def test_runtime_package_contains_runtime_and_excludes_development_assets() -> None:
    temp = Path(tempfile.mkdtemp(prefix="arh-test-portable-package-"))
    try:
        package_dir = temp / "pkg"
        run(["python3", str(PACKAGE_SCRIPT), "--output", str(package_dir), "--force"])
        for relative in (
            "references/portable-contract.md",
            "references/harness-protocol.md",
            "scripts/harnessctl.py",
            "scripts/harness_test_run.py",
            "scripts/runtime_profiles.py",
            "templates/worker_result.json",
        ):
            assert (package_dir / relative).is_file(), relative
        for relative in (
            "master-prompt.md",
            "sub-prompt.md",
            "references/closed-loop-pattern.md",
            "references/bugfix-lane.md",
            "references/eval_cases.md",
            "references/examples/fuzzy-goal-full-harness.md",
            "references/feature-spec-lane.md",
            "references/roles.md",
            "references/state-memory-boundary.md",
            "references/superpowers-integration.md",
            "scripts/protocol_regression_harness.py",
            "scripts/score_skill_protocol.py",
            "scripts/test_artifact_binding.py",
            "scripts/test_lessons.py",
            "scripts/test_model_routing.py",
            "scripts/test_plan_native_portable.py",
            "scripts/validate_workspace.py",
            "templates/acceptance_registry.json",
            "templates/capability_snapshot.md",
            "templates/lite_review.md",
            "templates/run_state.json",
            "templates/subagent_report.md",
            "templates/tdd_trace.jsonl",
            "templates/trace.jsonl",
        ):
            assert not (package_dir / relative).exists(), relative
    finally:
        shutil.rmtree(temp)


def main() -> int:
    tests = [
        test_progress_template_is_lightweight,
        test_lite_init_is_minimal_and_state_witness_is_opt_in,
        test_audited_lifecycle_reaches_high_confidence,
        test_legacy_full_cli_alias_writes_current_audited_mode,
        test_integrity_breaker_prevents_high_confidence,
        test_negative_validator_and_package_check,
        test_runtime_package_contains_state_witness_runtime,
        test_parallel_package_checks_use_isolated_temp_dirs,
        test_trigger_shortcuts_run_the_mode_gate_without_forcing_work,
        test_optional_model_routing_policy_is_present,
        test_progress_circuit_breaker_is_in_the_skill_entry,
        test_plan_native_entry_is_lean_and_provider_neutral,
        test_runtime_model_maps_are_outside_core_schema,
        test_runtime_package_contains_runtime_and_excludes_development_assets,
    ]
    for test in tests:
        test()
        print(f"PASS {test.__name__}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
