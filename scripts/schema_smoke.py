#!/usr/bin/env python3
"""Run dependency-free structural smoke checks for the published JSON Schemas."""

from __future__ import annotations

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCHEMA_ROOT = ROOT / "skills" / "agent-harness" / "schemas"
SCHEMA_DRAFT = "https://json-schema.org/draft/2020-12/schema"


def local_ref_errors(value: object, schema: dict[str, object], path: str = "$") -> list[str]:
    errors: list[str] = []
    if isinstance(value, dict):
        ref = value.get("$ref")
        if isinstance(ref, str):
            prefix = "#/$defs/"
            if not ref.startswith(prefix) or ref[len(prefix) :] not in schema.get("$defs", {}):
                errors.append(f"{path}: unresolved local $ref {ref!r}")
        for key, child in value.items():
            errors.extend(local_ref_errors(child, schema, f"{path}.{key}"))
    elif isinstance(value, list):
        for index, child in enumerate(value):
            errors.extend(local_ref_errors(child, schema, f"{path}[{index}]"))
    return errors


def main() -> int:
    if not SCHEMA_ROOT.is_dir():
        print(f"FAIL missing schema directory: {SCHEMA_ROOT}")
        return 1

    paths = sorted(SCHEMA_ROOT.glob("*.schema.json"))
    if not paths:
        print(f"FAIL no versioned schemas found: {SCHEMA_ROOT}")
        return 1

    errors: list[str] = []
    for path in paths:
        try:
            schema = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            errors.append(f"{path.name}: cannot load JSON: {exc}")
            continue
        if not isinstance(schema, dict):
            errors.append(f"{path.name}: root must be an object")
            continue
        if schema.get("$schema") != SCHEMA_DRAFT:
            errors.append(f"{path.name}: must declare JSON Schema Draft 2020-12")
        if not isinstance(schema.get("$id"), str) or not schema["$id"].strip():
            errors.append(f"{path.name}: missing non-empty $id")
        if schema.get("type") != "object":
            errors.append(f"{path.name}: root type must be object")
        required = schema.get("required")
        if not isinstance(required, list) or not required:
            errors.append(f"{path.name}: root required must be a non-empty list")
        properties = schema.get("properties")
        if not isinstance(properties, dict):
            errors.append(f"{path.name}: root properties must be an object")
        elif isinstance(required, list):
            missing = [item for item in required if item not in properties]
            if missing:
                errors.append(f"{path.name}: required fields missing from properties: {missing}")
        errors.extend(local_ref_errors(schema, schema, path.name))

    if errors:
        print("FAIL schema smoke")
        for error in errors:
            print(f"- {error}")
        return 1
    print(f"schema_smoke=verified count={len(paths)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
