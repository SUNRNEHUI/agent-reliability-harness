#!/usr/bin/env python3
"""Score structured forward-routing results without inspecting agent prose.

The cases describe expected routing decisions.  An agent supplies one JSON
object per case; this scorer compares the declared fields exactly and reports
PASS/FAIL for every case.  It deliberately does not infer behavior from
prompt keywords or free-form notes.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Mapping, Sequence


ROUTING_FIELDS = (
    "mode",
    "load_coding_workflow",
    "delegation",
    "durable_artifacts",
    "approval",
)
ENUM_VALUES = {
    "mode": {"native", "portable", "audited"},
    "delegation": {"none", "bounded", "deferred"},
    "approval": {"not_required", "required_before_action"},
}
BOOLEAN_FIELDS = ("load_coding_workflow", "durable_artifacts")


def _read_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except OSError as exc:
        raise ValueError(f"cannot read JSON file {path}: {exc}") from exc
    except json.JSONDecodeError as exc:
        raise ValueError(f"invalid JSON in {path}: {exc}") from exc


def _as_mapping(value: Any, *, label: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise ValueError(f"{label} must be a JSON object")
    return value


def _case_expected(case: Mapping[str, Any]) -> Mapping[str, Any]:
    expected = case.get("expected", case.get("expect"))
    expected = _as_mapping(expected, label=f"case {case.get('id', '<unknown>')} expected")
    missing = [field for field in ROUTING_FIELDS if field not in expected]
    if missing:
        raise ValueError(
            f"case {case.get('id', '<unknown>')} is missing expected field(s): "
            + ", ".join(missing)
        )
    for field, allowed in ENUM_VALUES.items():
        if expected[field] not in allowed:
            raise ValueError(
                f"case {case.get('id', '<unknown>')} has invalid expected {field}: "
                f"{expected[field]!r}"
            )
    for field in BOOLEAN_FIELDS:
        if type(expected[field]) is not bool:
            raise ValueError(
                f"case {case.get('id', '<unknown>')} expected {field} must be boolean"
            )
    return expected


def load_cases(path: Path) -> list[dict[str, Any]]:
    """Load and validate the routing case fixture."""

    root = _as_mapping(_read_json(path), label="cases file")
    cases = root.get("cases")
    if not isinstance(cases, list) or not cases:
        raise ValueError("cases file must contain a non-empty 'cases' array")

    normalized: list[dict[str, Any]] = []
    seen: set[str] = set()
    for index, raw_case in enumerate(cases):
        case = _as_mapping(raw_case, label=f"case at index {index}")
        case_id = case.get("id")
        if not isinstance(case_id, str) or not case_id.strip():
            raise ValueError(f"case at index {index} has no non-empty string id")
        if case_id in seen:
            raise ValueError(f"duplicate case id: {case_id}")
        prompt = case.get("prompt")
        if not isinstance(prompt, str) or not prompt.strip():
            raise ValueError(f"case {case_id} has no non-empty string prompt")
        expected = _case_expected(case)
        seen.add(case_id)
        normalized.append({"id": case_id, "prompt": prompt, "expected": dict(expected)})
    return normalized


def load_results(path: Path) -> list[dict[str, Any]]:
    """Load agent results from ``{"results": [...]}`` JSON."""

    root = _as_mapping(_read_json(path), label="results file")
    results = root.get("results")
    if not isinstance(results, list):
        raise ValueError("results file must contain a 'results' array")
    normalized: list[dict[str, Any]] = []
    for index, raw_result in enumerate(results):
        result = _as_mapping(raw_result, label=f"result at index {index}")
        case_id = result.get("case_id")
        if not isinstance(case_id, str) or not case_id.strip():
            raise ValueError(f"result at index {index} has no non-empty string case_id")
        normalized.append(dict(result))
    return normalized


def _same_value(actual: Any, expected: Any) -> bool:
    """Compare both value and JSON scalar/container type."""

    return type(actual) is type(expected) and actual == expected


def score_results(
    cases: Sequence[Mapping[str, Any]], results: Sequence[Mapping[str, Any]]
) -> dict[str, Any]:
    """Return a deterministic per-case PASS/FAIL report.

    Missing fields, duplicate result IDs, and unexpected result IDs are
    failures.  No prompt or free-form result text is examined.
    """

    case_by_id: dict[str, Mapping[str, Any]] = {}
    for case in cases:
        case_id = case.get("id")
        if not isinstance(case_id, str) or not case_id.strip():
            raise ValueError("each case must have a non-empty string id")
        if case_id in case_by_id:
            raise ValueError(f"duplicate case id: {case_id}")
        _case_expected(case)
        case_by_id[case_id] = case

    result_by_id: dict[str, Mapping[str, Any]] = {}
    duplicate_ids: list[str] = []
    for result in results:
        case_id = result.get("case_id")
        if not isinstance(case_id, str) or not case_id.strip():
            raise ValueError("each result must have a non-empty string case_id")
        if case_id in result_by_id:
            duplicate_ids.append(case_id)
        else:
            result_by_id[case_id] = result

    items: list[dict[str, Any]] = []
    for case_id, case in case_by_id.items():
        expected = _case_expected(case)
        actual = result_by_id.get(case_id)
        failures: list[str] = []
        if actual is None:
            failures.append("missing result")
        else:
            for field in ROUTING_FIELDS:
                if field not in actual:
                    failures.append(f"missing field: {field}")
                elif not _same_value(actual[field], expected[field]):
                    failures.append(
                        f"{field}: expected {expected[field]!r}, got {actual[field]!r}"
                    )
        items.append(
            {
                "case_id": case_id,
                "status": "PASS" if not failures else "FAIL",
                "failures": failures,
            }
        )

    expected_ids = set(case_by_id)
    unexpected_ids = sorted(set(result_by_id) - expected_ids)
    for case_id in unexpected_ids:
        items.append(
            {
                "case_id": case_id,
                "status": "FAIL",
                "failures": ["unexpected case_id"],
            }
        )
    for case_id in sorted(set(duplicate_ids)):
        items.append(
            {
                "case_id": case_id,
                "status": "FAIL",
                "failures": ["duplicate result case_id"],
            }
        )

    passed = sum(item["status"] == "PASS" for item in items)
    failed = len(items) - passed
    return {
        "status": "PASS" if failed == 0 and len(items) == len(case_by_id) else "FAIL",
        "total": len(items),
        "passed": passed,
        "failed": failed,
        "items": items,
    }


def score_files(cases_path: Path, results_path: Path) -> dict[str, Any]:
    """Load fixture and agent output files, then score them."""

    return score_results(load_cases(cases_path), load_results(results_path))


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cases", type=Path, required=True, help="routing case fixture JSON")
    parser.add_argument("--results", type=Path, required=True, help="agent result JSON")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    try:
        report = score_files(args.cases, args.results)
    except ValueError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
