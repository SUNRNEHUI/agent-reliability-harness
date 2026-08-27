#!/usr/bin/env python3
"""Regression tests for the controller's artifact path invariant."""

from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

SKILL_ROOT = Path(__file__).resolve().parents[1] / "skills" / "agent-reliability-harness"
sys.path.insert(0, str(SKILL_ROOT / "scripts"))

from harnessctl import validate_artifact_dir_binding


class ArtifactBindingTests(unittest.TestCase):
    def test_current_absolute_path_passes(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            artifact = Path(temporary) / "workspace" / "run"
            artifact.mkdir(parents=True)
            (artifact / "run_state.json").write_text(
                json.dumps({"artifact_dir": str(artifact)}) + "\n", encoding="utf-8"
            )
            self.assertEqual(validate_artifact_dir_binding(artifact), [])

    def test_workspace_relative_path_passes(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            project = Path(temporary)
            artifact = project / "workspace" / "run"
            artifact.mkdir(parents=True)
            (artifact / "run_state.json").write_text(
                json.dumps({"artifact_dir": "workspace/run"}) + "\n", encoding="utf-8"
            )
            self.assertEqual(validate_artifact_dir_binding(artifact), [])

    def test_stale_path_fails(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            artifact = Path(temporary) / "workspace" / "current-run"
            artifact.mkdir(parents=True)
            (artifact / "run_state.json").write_text(
                json.dumps({"artifact_dir": str(Path(temporary) / "workspace" / "old-run")}) + "\n",
                encoding="utf-8",
            )
            errors = validate_artifact_dir_binding(artifact)
            self.assertEqual(len(errors), 1)
            self.assertIn("does not match opened artifact directory", errors[0])


if __name__ == "__main__":
    unittest.main()
