#!/usr/bin/env python3
"""Repository-only golden checks for the public CLI and JSON contracts."""

from __future__ import annotations

import hashlib
import json
import re
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
SKILL_ROOT = REPOSITORY_ROOT / "skills" / "agent-harness"
SCHEMA_ROOT = SKILL_ROOT / "schemas"


def run(*args: str, cwd: Path = SKILL_ROOT) -> subprocess.CompletedProcess[str]:
    return subprocess.run(args, cwd=cwd, text=True, capture_output=True, check=False)


def load_object(path: Path) -> dict[str, object]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise AssertionError(f"expected object JSON: {path}")
    return value


class HarnessctlContractTests(unittest.TestCase):
    def test_subcommand_surface_and_help_exit_codes_are_frozen(self) -> None:
        sys.path.insert(0, str(SKILL_ROOT / "scripts"))
        import harnessctl  # type: ignore

        parser = harnessctl.build_parser()
        subparsers = next(
            action for action in parser._actions if getattr(action, "dest", None) == "command"
        )
        commands = tuple(sorted(subparsers.choices))
        expected = (
            "acceptance-refresh",
            "acceptance-set",
            "checkpoint",
            "close",
            "discover",
            "dispatch-create",
            "dispatch-update",
            "handoff",
            "lesson-add",
            "materialize",
            "pack",
            "recover",
            "resume",
            "run-set",
            "seal",
            "task-refresh",
            "task-set",
            "validate",
            "witness-set",
        )
        self.assertEqual(commands, expected)

        help_result = run(sys.executable, "scripts/harnessctl.py", "--help")
        self.assertEqual(help_result.returncode, 0, help_result.stderr)
        for command in expected:
            with self.subTest(command=command):
                result = run(sys.executable, "scripts/harnessctl.py", command, "--help")
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertIn(command, result.stdout)

        missing = run(sys.executable, "scripts/harnessctl.py")
        self.assertEqual(missing.returncode, 2)
        guarded = run(sys.executable, "scripts/harnessctl.py", "pack", str(REPOSITORY_ROOT / "missing-contract"))
        self.assertEqual(guarded.returncode, 2)
        self.assertIn("ERROR", guarded.stderr)
        invalid = run(sys.executable, "scripts/harnessctl.py", "validate", str(REPOSITORY_ROOT / "missing-artifact"))
        self.assertEqual(invalid.returncode, 1)
        self.assertIn("FAIL", invalid.stdout)

    def test_status_json_and_historical_strict_gate_have_stable_exit_behavior(self) -> None:
        with tempfile.TemporaryDirectory(prefix="arh-status-contract-") as temp_name:
            temp = Path(temp_name)
            initialized = run(
                sys.executable,
                "scripts/init_run.py",
                "--mode",
                "audited",
                "--project-root",
                str(temp),
                "--title",
                "status contract",
                "--agents",
                "docs",
                "--force",
            )
            self.assertEqual(initialized.returncode, 0, initialized.stdout + initialized.stderr)
            state_path = temp / "workspace" / "status-contract" / "run_state.json"

            human = run(sys.executable, "scripts/status.py", str(state_path))
            self.assertEqual(human.returncode, 0, human.stderr)
            self.assertTrue(human.stdout.startswith("Run: status contract | Mode: audited | Status: intake\n"))

            strict = run(sys.executable, "scripts/status.py", str(state_path), "--require-high-confidence")
            self.assertEqual(strict.returncode, 1)
            self.assertIn("Status gate: requires high completion confidence", strict.stdout)

            machine = run(sys.executable, "scripts/status.py", str(state_path), "--json")
            self.assertEqual(machine.returncode, 0, machine.stderr)
            payload = json.loads(machine.stdout)
            self.assertEqual(payload["schema"], "arh-status-v1")
            self.assertEqual(payload["version"], 1)
            self.assertEqual(payload["title"], "status contract")
            self.assertEqual(payload["mode"], "audited")
            self.assertEqual(payload["status"], "intake")
            self.assertEqual(payload["completion_confidence"], "low")
            self.assertIn("integrity_errors", payload)
            self.assertIsInstance(payload["tasks"], list)

            strict_machine = run(
                sys.executable,
                "scripts/status.py",
                str(state_path),
                "--json",
                "--require-high-confidence",
            )
            self.assertEqual(strict_machine.returncode, 1)
            self.assertNotIn("Status gate:", strict_machine.stdout)
            strict_payload = json.loads(strict_machine.stdout)
            self.assertEqual(strict_payload["schema"], "arh-status-v1")
            self.assertEqual(strict_payload["completion_confidence"], "low")

            state = load_object(state_path)
            state["tasks"][0]["status"] = "blocked"  # type: ignore[index]
            state["tasks"][0]["stop_reason"] = "dependency unavailable"  # type: ignore[index]
            state_path.write_text(json.dumps(state, indent=2) + "\n", encoding="utf-8")
            blocked = run(sys.executable, "scripts/status.py", str(state_path), "--json")
            self.assertEqual(blocked.returncode, 0, blocked.stderr)
            blocked_payload = json.loads(blocked.stdout)
            self.assertEqual(blocked_payload["completion_confidence"], "blocked")
            self.assertEqual(blocked_payload["blockers"], ["1.1 docs: dependency unavailable"])

            human_blocked = run(sys.executable, "scripts/status.py", str(state_path))
            self.assertEqual(human_blocked.returncode, 0)
            self.assertIn("Blockers: 1.1 docs: dependency unavailable", human_blocked.stdout)
            self.assertIn("Integrity errors:", human_blocked.stdout)

            tampered = load_object(state_path)
            tampered["title"] = "tampered status contract"
            tampered["continuation"]["owner"]["epoch"] = "corrupt"  # type: ignore[index]
            state_path.write_text(json.dumps(tampered, indent=2) + "\n", encoding="utf-8")
            integrity = run(sys.executable, "scripts/status.py", str(state_path), "--json")
            self.assertEqual(integrity.returncode, 0, integrity.stderr)
            integrity_payload = json.loads(integrity.stdout)
            self.assertTrue(integrity_payload["integrity_errors"])
            self.assertEqual(integrity_payload["completion_confidence"], "blocked")
            self.assertEqual(integrity_payload["continuation"]["owner"]["epoch"], 0)


class PlatformBaselineTests(unittest.TestCase):
    def test_ci_matrix_pins_actions_and_checks_a_real_commit_diff(self) -> None:
        workflow = (REPOSITORY_ROOT / ".github" / "workflows" / "ci.yml").read_text(
            encoding="utf-8"
        )
        expected_actions = {
            "actions/checkout": "3d3c42e5aac5ba805825da76410c181273ba90b1",
            "actions/setup-python": "5fda3b95a4ea91299a34e894583c3862153e4b97",
            "actions/setup-node": "820762786026740c76f36085b0efc47a31fe5020",
        }
        pinned_actions = dict(
            re.findall(r"uses:\s*(actions/[A-Za-z0-9_.-]+)@([0-9a-f]{40})\b", workflow)
        )
        self.assertEqual(pinned_actions, expected_actions)
        self.assertNotRegex(workflow, r"uses:\s*actions/[^@\s]+@v\d")
        self.assertRegex(workflow, r"- os: macos-latest\s+python-version: \"3\.14\"")
        self.assertRegex(workflow, r"- os: windows-latest\s+python-version: \"3\.14\"")
        self.assertIn('python-version: ["3.10", "3.11", "3.12", "3.13", "3.14"]', workflow)
        self.assertEqual(workflow.count("fetch-depth: 2"), 2)
        self.assertIn("run: git diff --check HEAD^ HEAD", workflow)


class SchemaContractTests(unittest.TestCase):
    EXPECTED_SCHEMAS = {
        "portable-contract-v2.schema.json": ("urn:agent-harness:portable:v2", "schema_version"),
        "audited-run-state-v1.schema.json": ("urn:agent-harness:audited-run-state:v1", "version"),
        "acceptance-registry-v1.schema.json": ("urn:agent-harness:acceptance-registry:v1", "version"),
        "worker-result-v2.schema.json": ("urn:agent-harness:worker-result:v2", "schema"),
        "status-output-v1.schema.json": ("urn:agent-harness:status-output:v1", "schema"),
    }

    def test_versioned_schema_bundle_is_complete_and_machine_readable(self) -> None:
        self.assertEqual(set(path.name for path in SCHEMA_ROOT.glob("*.schema.json")), set(self.EXPECTED_SCHEMAS))
        for filename, (schema_id, version_key) in self.EXPECTED_SCHEMAS.items():
            with self.subTest(filename=filename):
                schema = load_object(SCHEMA_ROOT / filename)
                self.assertEqual(schema["$schema"], "https://json-schema.org/draft/2020-12/schema")
                self.assertEqual(schema["$id"], schema_id)
                self.assertEqual(schema["type"], "object")
                required = schema["required"]
                self.assertIsInstance(required, list)
                self.assertIn(version_key, required)

    def test_generated_artifacts_match_declared_top_level_structure(self) -> None:
        with tempfile.TemporaryDirectory(prefix="arh-schema-contract-") as temp_name:
            temp = Path(temp_name)
            portable = run(
                sys.executable,
                "scripts/harnessctl.py",
                "materialize",
                str(temp),
                "--title",
                "schema portable",
                "--goal",
                "Preserve a machine-readable contract",
                "--done-when",
                "Schema smoke passes",
                "--next-action",
                "Run schema checks",
            )
            self.assertEqual(portable.returncode, 0, portable.stdout + portable.stderr)
            portable_payload = json.loads(portable.stdout)
            portable_contract = load_object(Path(portable_payload["contract_path"]))
            portable_schema = load_object(SCHEMA_ROOT / "portable-contract-v2.schema.json")
            self.assertTrue(set(portable_schema["required"]).issubset(portable_contract))

            audited = run(
                sys.executable,
                "scripts/init_run.py",
                "--mode",
                "audited",
                "--project-root",
                str(temp),
                "--title",
                "schema audited",
                "--agents",
                "docs",
                "--force",
            )
            self.assertEqual(audited.returncode, 0, audited.stdout + audited.stderr)
            audited_root = temp / "workspace" / "schema-audited"
            run_state = load_object(audited_root / "run_state.json")
            acceptance = load_object(audited_root / "acceptance_registry.json")
            self.assertTrue(
                set(load_object(SCHEMA_ROOT / "audited-run-state-v1.schema.json")["required"]).issubset(run_state)
            )
            self.assertTrue(
                set(load_object(SCHEMA_ROOT / "acceptance-registry-v1.schema.json")["required"]).issubset(acceptance)
            )

    def test_generated_canonical_bytes_match_digest_anchors_without_crlf(self) -> None:
        with tempfile.TemporaryDirectory(prefix="arh-canonical-bytes-contract-") as temp_name:
            temp = Path(temp_name)
            audited = run(
                sys.executable,
                "scripts/init_run.py",
                "--mode",
                "audited",
                "--project-root",
                str(temp),
                "--title",
                "canonical bytes",
                "--agents",
                "docs",
                "--force",
            )
            self.assertEqual(audited.returncode, 0, audited.stdout + audited.stderr)
            audited_root = temp / "workspace" / "canonical-bytes"
            trace_path = audited_root / "trace.jsonl"
            initialized = json.loads(trace_path.read_text(encoding="utf-8").splitlines()[0])
            for filename in ("run_state.json", "acceptance_registry.json"):
                with self.subTest(stage="initial", filename=filename):
                    raw = (audited_root / filename).read_bytes()
                    self.assertNotIn(b"\r", raw)
                    self.assertEqual(
                        initialized["state_digests"][filename],
                        hashlib.sha256(raw).hexdigest(),
                    )

            sealed = run(
                sys.executable,
                "scripts/harnessctl.py",
                "seal",
                str(audited_root),
                "--reason",
                "canonical bytes contract",
            )
            self.assertEqual(sealed.returncode, 0, sealed.stdout + sealed.stderr)
            transitioned = run(
                sys.executable,
                "scripts/harnessctl.py",
                "run-set",
                str(audited_root),
                "--status",
                "gated",
            )
            self.assertEqual(transitioned.returncode, 0, transitioned.stdout + transitioned.stderr)
            events = [
                json.loads(line)
                for line in trace_path.read_text(encoding="utf-8").splitlines()
                if line.strip()
            ]
            transition = next(event for event in reversed(events) if event.get("event") == "run_transition")
            state_raw = (audited_root / "run_state.json").read_bytes()
            self.assertNotIn(b"\r", state_raw)
            self.assertEqual(transition["after_sha256"], hashlib.sha256(state_raw).hexdigest())

            portable = run(
                sys.executable,
                "scripts/harnessctl.py",
                "materialize",
                str(temp),
                "--title",
                "canonical portable",
                "--goal",
                "Preserve canonical bytes",
                "--done-when",
                "Digest anchor matches",
                "--next-action",
                "Inspect canonical bytes",
            )
            self.assertEqual(portable.returncode, 0, portable.stdout + portable.stderr)
            portable_payload = json.loads(portable.stdout)
            contract_path = Path(portable_payload["contract_path"])
            contract_raw = contract_path.read_bytes()
            self.assertNotIn(b"\r", contract_raw)
            portable_event = json.loads(
                (contract_path.parent / "events.jsonl").read_text(encoding="utf-8").splitlines()[0]
            )
            self.assertEqual(
                portable_event["contract_sha256"],
                hashlib.sha256(contract_raw).hexdigest(),
            )

    def test_worker_result_template_contains_the_frozen_envelope(self) -> None:
        worker = load_object(SKILL_ROOT / "templates" / "worker_result.json")
        schema = load_object(SCHEMA_ROOT / "worker-result-v2.schema.json")
        self.assertTrue(set(schema["required"]).issubset(worker))
        self.assertEqual(worker["schema"], "arh-worker-result-v2")


if __name__ == "__main__":
    unittest.main()
