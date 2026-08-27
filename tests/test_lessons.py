#!/usr/bin/env python3
"""Regression tests for evidence-backed lesson recording."""

from __future__ import annotations

import json
import subprocess
import tempfile
import unittest
from pathlib import Path


HARNESS_ROOT = (
    Path(__file__).resolve().parents[1] / "skills" / "agent-harness"
)
INIT_RUN = HARNESS_ROOT / "scripts" / "init_run.py"
HARNESSCTL = HARNESS_ROOT / "scripts" / "harnessctl.py"


class LessonLedgerTests(unittest.TestCase):
    def test_lesson_add_records_evidence_and_trace_binding(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            project = Path(temporary) / "project"
            init = subprocess.run(
                [
                    "python3",
                    str(INIT_RUN),
                    "--project-root",
                    str(project),
                    "--title",
                    "lesson ledger test",
                ],
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(init.returncode, 0, init.stdout + init.stderr)
            artifact = project / "workspace" / "lesson-ledger-test"
            evidence = artifact / "evidence" / "lesson-report.md"
            evidence.parent.mkdir(parents=True, exist_ok=True)
            evidence.write_text("verified browser screenshot and geometry measurement\n", encoding="utf-8")
            command = [
                "python3",
                str(HARNESSCTL),
                "lesson-add",
                str(artifact),
                "--source-case",
                "Desktop/namo project/case/nomo-1.8.6",
                "--category",
                "viewfinder-geometry",
                "--symptom",
                "preview bleeds outside the device chrome",
                "--root-cause",
                "transparent board fallback was treated as the hole",
                "--fix",
                "use evidence-backed mask and clip preview below frame overlays",
                "--verification",
                "browser bounding boxes and overflow audit pass",
                "--reusable-rule",
                "never infer a viewfinder hole from a tiny alpha component",
                "--verification-tier",
                "user_visible",
                "--evidence-file",
                "evidence/lesson-report.md",
                "--actor-id",
                "lesson-test-manager",
            ]
            recorded = subprocess.run(command, capture_output=True, text=True, check=False)
            self.assertEqual(recorded.returncode, 0, recorded.stdout + recorded.stderr)
            ledger = (artifact / "lessons.jsonl").read_text(encoding="utf-8").splitlines()
            self.assertEqual(len(ledger), 1)
            record = json.loads(ledger[0])
            self.assertEqual(record["status"], "verified")
            self.assertEqual(record["evidence"][0]["path"], "evidence/lesson-report.md")
            self.assertEqual(record["verification_tier"], "user_visible")
            trace = (artifact / "trace.jsonl").read_text(encoding="utf-8")
            self.assertIn('"event": "lesson_recorded"', trace)

            validated = subprocess.run(
                ["python3", str(HARNESSCTL), "validate", str(artifact)],
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(validated.returncode, 0, validated.stdout + validated.stderr)

    def test_tampered_lesson_evidence_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            project = Path(temporary) / "project"
            subprocess.run(
                ["python3", str(INIT_RUN), "--project-root", str(project), "--title", "lesson tamper test"],
                capture_output=True,
                text=True,
                check=True,
            )
            artifact = project / "workspace" / "lesson-tamper-test"
            evidence = artifact / "evidence" / "lesson-report.md"
            evidence.parent.mkdir(parents=True, exist_ok=True)
            evidence.write_text("original evidence\n", encoding="utf-8")
            subprocess.run(
                [
                    "python3",
                    str(HARNESSCTL),
                    "lesson-add",
                    str(artifact),
                    "--source-case",
                    "historical-case",
                    "--category",
                    "export",
                    "--symptom",
                    "export differs from preview",
                    "--root-cause",
                    "separate renderer paths",
                    "--fix",
                    "share the snapshot buffer",
                    "--verification",
                    "fixture hash comparison",
                    "--reusable-rule",
                    "preview and export must share source and recipe",
                    "--evidence-file",
                    "evidence/lesson-report.md",
                    "--actor-id",
                    "lesson-test-manager",
                ],
                capture_output=True,
                text=True,
                check=True,
            )
            evidence.write_text("tampered evidence\n", encoding="utf-8")
            validated = subprocess.run(
                ["python3", str(HARNESSCTL), "validate", str(artifact)],
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertNotEqual(validated.returncode, 0)
            self.assertIn("sha256 does not match", validated.stdout)


if __name__ == "__main__":
    unittest.main()
