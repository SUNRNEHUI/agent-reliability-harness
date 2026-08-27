#!/usr/bin/env python3
"""Behavioral tests for Plan-native routing and the portable v2 contract."""

from __future__ import annotations

import hashlib
import json
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

try:
    from .test_handoff_resume import remove_readonly
except ImportError:  # unittest discover -s tests imports modules without a package
    from test_handoff_resume import remove_readonly


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
ROOT = REPOSITORY_ROOT / "skills" / "agent-reliability-harness"


def run(*args: str, cwd: Path = ROOT) -> subprocess.CompletedProcess[str]:
    return subprocess.run(args, cwd=cwd, text=True, capture_output=True, check=False)


def require_success(result: subprocess.CompletedProcess[str]) -> None:
    if result.returncode != 0:
        raise AssertionError(result.stdout + result.stderr)


def load_json(path: Path) -> dict[str, object]:
    value = json.loads(path.read_text(encoding="utf-8"))
    assert isinstance(value, dict)
    return value


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


class ProgressCircuitBreakerPolicyTests(unittest.TestCase):
    def test_progress_circuit_breaker_is_explicit_and_domain_neutral(self) -> None:
        skill = (ROOT / "SKILL.md").read_text(encoding="utf-8")
        normalized = " ".join(skill.split())
        for term in (
            "Progress Circuit Breaker",
            "new evidence",
            "artifact change",
            "test result",
            "binding decision",
            "named `done_when` criterion",
            "named critical-path blocker",
            "does not count as progress",
            "Generated metadata, reports, package rebuilds",
            "two consecutive",
            "`STALLED`",
            "falsifying experiment",
            "must not increase reasoning effort",
        ):
            self.assertIn(term, normalized)
        self.assertNotIn("Effect Reconstruction Fast Lane", skill)


class WorkflowCompositionPolicyTests(unittest.TestCase):
    def test_code_work_reuses_available_workflow_without_a_companion_dependency(self) -> None:
        skill = (ROOT / "SKILL.md").read_text(encoding="utf-8")
        normalized = " ".join(skill.split()).casefold()

        for term in (
            "repository's established coding workflow",
            "available matching coding skill",
            "does not replace, copy, or weaken",
            "do not require a particular companion skill by name",
        ):
            self.assertIn(term, normalized)
        self.assertNotIn("coding-workflow", normalized)
        self.assertNotIn("~/.codex", normalized)


class ComplexityAndDelegationPolicyTests(unittest.TestCase):
    def test_mode_does_not_change_bounded_implementation_delegation(self) -> None:
        skill = (ROOT / "SKILL.md").read_text(encoding="utf-8")
        normalized = " ".join(skill.split()).casefold()

        for term in (
            "delegation is independent of mode",
            "v3 micro work may stay on the parent/main",
            "ordinary or execution-heavy work uses one",
            "explicit user delegation overrides the micro direct route",
            "coupled writes stay serial",
            "they do not recursively delegate",
            "one runtime plan",
            "independent modules or ownership boundaries",
            "track worker status and evidence",
            "mode controls persistence and evidence depth",
            "`delegation-cost-higher` confirmations",
        ):
            self.assertIn(term, normalized)


class PlanNativePortableTests(unittest.TestCase):
    def setUp(self) -> None:
        self.project = Path(tempfile.mkdtemp(prefix="arh-portable-"))
        require_success(run("git", "init", "-q", str(self.project)))
        require_success(run("git", "config", "user.email", "harness@example.invalid", cwd=self.project))
        require_success(run("git", "config", "user.name", "Harness Test", cwd=self.project))
        (self.project / "README.md").write_text("initial\n", encoding="utf-8")
        require_success(run("git", "add", "README.md", cwd=self.project))
        require_success(run("git", "commit", "-qm", "initial", cwd=self.project))

    def tearDown(self) -> None:
        shutil.rmtree(self.project, onerror=remove_readonly)

    def harness(self, command: str, *args: str) -> subprocess.CompletedProcess[str]:
        return run("python3", "scripts/harnessctl.py", command, *args)

    def materialize(self, title: str = "portable task") -> Path:
        result = self.harness(
            "materialize",
            str(self.project),
            "--title",
            title,
            "--goal",
            "Deliver a portable, verified result",
            "--done-when",
            "Focused verification passes",
            "--constraint",
            "Preserve unrelated files",
            "--non-goal",
            "Do not redesign unrelated protocols",
            "--next-action",
            "Inspect the target module",
        )
        require_success(result)
        payload = json.loads(result.stdout)
        return Path(payload["artifact_dir"])

    def test_materialize_creates_only_the_portable_core(self) -> None:
        artifact = self.materialize()
        self.assertEqual(artifact.resolve(), (self.project / ".harness" / "portable-task").resolve())
        files = sorted(
            str(path.relative_to(artifact))
            for path in artifact.rglob("*")
            if path.is_file() and not path.name.endswith(".lock")
        )
        self.assertEqual(files, ["capsule.md", "contract.json", "events.jsonl"])

        contract = load_json(artifact / "contract.json")
        self.assertEqual(contract["protocol"], "arh-portable-v2")
        self.assertEqual(contract["mode"], "portable")
        self.assertEqual(contract["objective"]["done_when"], ["Focused verification passes"])
        self.assertEqual(contract["objective"]["non_goals"], ["Do not redesign unrelated protocols"])
        self.assertEqual(contract["execution"]["next_action"], "Inspect the target module")
        self.assertNotIn("routing_policy", contract)
        self.assertNotIn("tdd_current_cycle_context", contract)
        self.assertNotIn("state_witness", contract)

        capsule = (artifact / "capsule.md").read_text(encoding="utf-8")
        self.assertLessEqual(len(capsule), 6000)
        for value in (
            "Deliver a portable, verified result",
            "Focused verification passes",
            "Do not redesign unrelated protocols",
            "Inspect the target module",
            "filesystem",
        ):
            self.assertIn(value, capsule)

    def test_checkpoint_projects_evidence_without_copying_output(self) -> None:
        artifact = self.materialize("checkpoint task")
        result = self.harness(
            "checkpoint",
            str(self.project),
            "--runtime",
            "codex",
            "--actor-id",
            "codex-main",
            "--next-action",
            "Implement the focused change",
            "--completed",
            "Mapped the production path",
            "--pending-verification",
            "Run the focused regression",
            "--decision",
            "Use the existing state machine",
            "--decision-reason",
            "It preserves compatibility",
            "--evidence-file",
            "README.md",
            "--reason",
            "Verified planning boundary",
        )
        require_success(result)
        payload = json.loads(result.stdout)
        self.assertEqual(payload["mode"], "portable")

        contract = load_json(artifact / "contract.json")
        self.assertEqual(contract["execution"]["completed"], ["Mapped the production path"])
        self.assertEqual(contract["execution"]["pending_verification"], ["Run the focused regression"])
        self.assertEqual(contract["decisions"][0]["decision"], "Use the existing state machine")
        self.assertEqual(contract["evidence"][0]["path"], "README.md")
        self.assertEqual(contract["evidence"][0]["sha256"], sha256(self.project / "README.md"))
        self.assertNotIn("initial", json.dumps(contract["evidence"]))

    def test_checkpoint_accepts_explicit_capsule_limit_for_long_running_contract(self) -> None:
        artifact = self.materialize("long checkpoint task")
        checkpoint = self.harness(
            "checkpoint",
            str(artifact),
            "--runtime",
            "codex-desktop",
            "--actor-id",
            "root",
            "--owner-epoch",
            "1",
            "--next-action",
            "Continue the long-running task",
            "--completed",
            "x" * 5800,
            "--max-chars",
            "8000",
            "--reason",
            "Preserve a bounded but larger resume capsule",
        )
        require_success(checkpoint)
        capsule = (artifact / "capsule.md").read_text(encoding="utf-8")
        self.assertGreater(len(capsule), 6000)
        self.assertLessEqual(len(capsule), 8000)

    def test_resume_returns_capsule_and_tiered_reads(self) -> None:
        artifact = self.materialize("resume task")
        checkpoint = self.harness(
            "checkpoint",
            str(self.project),
            "--runtime",
            "codex",
            "--actor-id",
            "codex-main",
            "--next-action",
            "Continue implementation",
            "--reason",
            "Safe handoff boundary",
        )
        require_success(checkpoint)
        handed_off = self.harness(
            "handoff",
            str(self.project),
            "--actor-id",
            "codex-main",
            "--owner-epoch",
            "1",
            "--next-action",
            "Continue implementation",
            "--reason",
            "Switch runtime",
        )
        require_success(handed_off)

        resumed = self.harness(
            "resume",
            str(self.project),
            "--runtime",
            "claude",
            "--actor-id",
            "claude-main",
        )
        require_success(resumed)
        packet = json.loads(resumed.stdout)
        self.assertEqual(packet["protocol"], "arh-portable-v2")
        self.assertEqual(packet["owner"]["actor_id"], "claude-main")
        self.assertEqual(packet["previous_owner"]["actor_id"], "codex-main")
        self.assertEqual(packet["must_read"], ["capsule.md"])
        self.assertIn("events.jsonl", packet["read_if_needed"])
        self.assertEqual(packet["required_capabilities"], ["filesystem"])
        self.assertEqual(packet["optional_capabilities"], [])
        self.assertNotIn("required_reads", packet)
        self.assertIn("Continue implementation", packet["capsule"])
        self.assertLessEqual(len(packet["capsule"]), 6000)
        self.assertEqual(Path(packet["capsule_path"]), artifact / "capsule.md")

    def test_resume_reports_workspace_drift(self) -> None:
        self.materialize("drift task")
        checkpoint = self.harness(
            "checkpoint",
            str(self.project),
            "--runtime",
            "codex",
            "--actor-id",
            "codex-main",
            "--next-action",
            "Run the next check",
            "--reason",
            "Capture clean state",
        )
        require_success(checkpoint)
        (self.project / "README.md").write_text("changed\n", encoding="utf-8")

        resumed = self.harness(
            "resume",
            str(self.project),
            "--runtime",
            "codex",
            "--actor-id",
            "codex-main",
            "--owner-epoch",
            "1",
        )
        require_success(resumed)
        packet = json.loads(resumed.stdout)
        self.assertTrue(packet["workspace_drift"])
        self.assertEqual(packet["changed_paths"], ["README.md"])
        self.assertIn("reconcile workspace drift", packet["next_action"].casefold())

    def test_invalid_contract_fails_closed(self) -> None:
        artifact = self.materialize("invalid task")
        contract = load_json(artifact / "contract.json")
        contract["objective"]["done_when"] = []
        (artifact / "contract.json").write_text(
            json.dumps(contract, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        result = self.harness("validate", str(artifact))
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("done_when", result.stdout + result.stderr)

    def test_project_root_binding_fails_before_external_lock_creation(self) -> None:
        artifact = self.materialize("wrong root")
        wrong_root = self.project.parent / f"{self.project.name}-wrong-root"
        contract = load_json(artifact / "contract.json")
        contract["project_root"] = str(wrong_root)
        (artifact / "contract.json").write_text(
            json.dumps(contract, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )

        resumed = self.harness(
            "resume",
            str(artifact),
            "--runtime",
            "codex",
            "--actor-id",
            "codex-main",
        )

        self.assertNotEqual(resumed.returncode, 0)
        self.assertIn("project_root", resumed.stdout + resumed.stderr)
        self.assertFalse(wrong_root.exists())

    def test_invalid_events_jsonl_fails_closed(self) -> None:
        artifact = self.materialize("invalid events")
        with (artifact / "events.jsonl").open("a", encoding="utf-8") as handle:
            handle.write("{broken\n")

        result = self.harness("validate", str(artifact))

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("events.jsonl", result.stdout + result.stderr)

    def test_resume_rejects_active_portable_and_audited_ambiguity(self) -> None:
        portable = self.materialize("portable active")
        initialized = run(
            "python3",
            "scripts/init_run.py",
            "--project-root",
            str(self.project),
            "--mode",
            "audited",
            "--title",
            "audited active",
            "--agents",
            "implementation",
        )
        require_success(initialized)
        audited = self.project / "workspace" / "audited-active"
        self.assertEqual(load_json(audited / "run_state.json")["mode"], "audited")
        before = {
            portable / "contract.json": sha256(portable / "contract.json"),
            audited / "run_state.json": sha256(audited / "run_state.json"),
        }

        resumed = self.harness(
            "resume",
            str(self.project),
            "--runtime",
            "codex",
            "--actor-id",
            "codex-main",
        )

        self.assertNotEqual(resumed.returncode, 0)
        self.assertIn("ambiguous", (resumed.stdout + resumed.stderr).casefold())
        self.assertEqual(before, {path: sha256(path) for path in before})

    def test_close_accepts_verified_contract_and_removes_it_from_active_selection(self) -> None:
        artifact = self.materialize("completed task")
        checkpoint = self.harness(
            "checkpoint",
            str(self.project),
            "--runtime",
            "codex",
            "--actor-id",
            "codex-main",
            "--next-action",
            "Close the verified contract",
            "--evidence-file",
            "README.md",
            "--reason",
            "Verification completed",
        )
        require_success(checkpoint)

        closed = self.harness(
            "close",
            str(self.project),
            "--status",
            "accepted",
            "--actor-id",
            "codex-main",
            "--owner-epoch",
            "1",
            "--reason",
            "All done_when criteria were verified",
        )
        require_success(closed)
        self.assertEqual(load_json(artifact / "contract.json")["status"], "accepted")
        capsule = (artifact / "capsule.md").read_text(encoding="utf-8")
        self.assertIn("Status: accepted", capsule)
        self.assertIn("All done_when criteria were verified", capsule)

        next_artifact = self.materialize("next task")
        resumed = self.harness(
            "resume",
            str(self.project),
            "--runtime",
            "codex",
            "--actor-id",
            "codex-next",
        )
        require_success(resumed)
        self.assertEqual(Path(json.loads(resumed.stdout)["artifact_dir"]), next_artifact)

    def test_close_rejects_pending_verification(self) -> None:
        self.materialize("not verified")
        checkpoint = self.harness(
            "checkpoint",
            str(self.project),
            "--runtime",
            "codex",
            "--actor-id",
            "codex-main",
            "--next-action",
            "Run the remaining verification",
            "--pending-verification",
            "Regression suite",
            "--evidence-file",
            "README.md",
            "--reason",
            "Partial verification completed",
        )
        require_success(checkpoint)

        closed = self.harness(
            "close",
            str(self.project),
            "--status",
            "accepted",
            "--actor-id",
            "codex-main",
            "--owner-epoch",
            "1",
            "--reason",
            "Attempt premature acceptance",
        )

        self.assertNotEqual(closed.returncode, 0)
        self.assertIn("pending verification", (closed.stdout + closed.stderr).casefold())

        cleared = self.harness(
            "checkpoint",
            str(self.project),
            "--runtime",
            "codex",
            "--actor-id",
            "codex-main",
            "--owner-epoch",
            "1",
            "--next-action",
            "Close the verified contract",
            "--clear-pending-verification",
            "--reason",
            "Regression suite passed",
        )
        require_success(cleared)
        accepted = self.harness(
            "close",
            str(self.project),
            "--status",
            "accepted",
            "--actor-id",
            "codex-main",
            "--owner-epoch",
            "1",
            "--reason",
            "All verification completed",
        )
        require_success(accepted)


if __name__ == "__main__":
    unittest.main(verbosity=2)
