#!/usr/bin/env python3
"""Tests for the repository-only forward routing evaluation scorer."""

from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
EVAL_ROOT = REPOSITORY_ROOT / "tests" / "evals"
sys.path.insert(0, str(EVAL_ROOT))

from score_forward import load_cases, score_files, score_results  # noqa: E402


class ForwardScorerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.cases_path = EVAL_ROOT / "forward_cases.json"
        cls.cases = load_cases(cls.cases_path)

    def _matching_results(self) -> list[dict[str, object]]:
        return [
            {"case_id": case["id"], **case["expected"]}
            for case in self.cases
        ]

    def test_accepts_matching_structured_results(self) -> None:
        report = score_results(self.cases, self._matching_results())

        self.assertEqual(report["status"], "PASS")
        self.assertEqual(report["passed"], len(self.cases))
        self.assertEqual(report["failed"], 0)
        self.assertTrue(all(item["status"] == "PASS" for item in report["items"]))

    def test_rejects_wrong_routing_decision(self) -> None:
        results = self._matching_results()
        results[2]["delegation"] = "none"

        report = score_results(self.cases, results)

        self.assertEqual(report["status"], "FAIL")
        item = next(item for item in report["items"] if item["case_id"] == "native_complex_modules")
        self.assertEqual(item["status"], "FAIL")
        self.assertIn("delegation", item["failures"][0])

    def test_missing_field_is_a_case_failure(self) -> None:
        results = self._matching_results()
        del results[0]["approval"]

        report = score_results(self.cases, results)

        item = next(item for item in report["items"] if item["case_id"] == "native_typo")
        self.assertEqual(item["status"], "FAIL")
        self.assertEqual(item["failures"], ["missing field: approval"])

    def test_rejects_invalid_expected_value_in_case_fixture(self) -> None:
        cases = [dict(case) for case in self.cases]
        cases[0] = {**cases[0], "expected": {**cases[0]["expected"], "mode": "nativ"}}

        with self.assertRaisesRegex(ValueError, "invalid expected mode"):
            score_results(cases, self._matching_results())

    def test_reads_agent_json_result_file(self) -> None:
        results = {"results": self._matching_results()}
        with tempfile.TemporaryDirectory() as temporary:
            result_path = Path(temporary) / "agent-results.json"
            result_path.write_text(json.dumps(results, ensure_ascii=False), encoding="utf-8")

            report = score_files(self.cases_path, result_path)

        self.assertEqual(report["status"], "PASS")


if __name__ == "__main__":
    unittest.main()
