#!/usr/bin/env python3
"""Check or update current-version references from VERSION."""

from __future__ import annotations

import argparse
import re
from pathlib import Path


SKILL_NAME = "agent-harness"
SKILL_ROOT = Path("skills") / SKILL_NAME

VERSION_PATTERNS = {
    "README.md": (
        (
            re.compile(
                r"^Current version: \*\*v[^*]+\*\* · (?P<date>.*)$",
                re.MULTILINE,
            ),
            "Current version: **v{version}** · {date}",
        ),
    ),
    "README.zh-CN.md": (
        (
            re.compile(
                r"^当前版本：\*\*v[^*]+\*\* · (?P<date>.*)$",
                re.MULTILINE,
            ),
            "当前版本：**v{version}** · {date}",
        ),
    ),
    str(SKILL_ROOT / "SKILL.md"): (
        (
            re.compile(
                r"^\*Agent Harness v[^|]+ \| (?P<date>[^*]+)\*$",
                re.MULTILINE,
            ),
            "*Agent Harness v{version} | {date}*",
        ),
    ),
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Sync current version references from VERSION.")
    parser.add_argument(
        "--root",
        type=Path,
        default=Path(__file__).resolve().parents[1],
        help="Repository root. Defaults to the parent of scripts/.",
    )
    parser.add_argument(
        "--date",
        help="Release date to write with --fix. Existing dates are preserved when omitted.",
    )
    parser.add_argument("--fix", action="store_true", help="Rewrite current-version references.")
    return parser.parse_args()


def read_version(root: Path) -> str:
    path = root / SKILL_ROOT / "VERSION"
    if not path.is_file():
        raise SystemExit(f"missing VERSION file: {path}")
    version = path.read_text(encoding="utf-8").strip()
    if not re.fullmatch(r"\d+\.\d+\.\d+", version):
        raise SystemExit(f"VERSION must be MAJOR.MINOR.PATCH, got {version!r}")
    return version


def sync_file(
    path: Path,
    patterns: tuple[tuple[re.Pattern[str], str], ...],
    version: str,
    date: str | None,
    fix: bool,
) -> list[str]:
    content = path.read_text(encoding="utf-8")
    updated = content
    errors: list[str] = []

    for pattern, replacement in patterns:
        match = pattern.search(updated)
        if match is None:
            errors.append(f"{path.name}: missing current-version pattern {pattern.pattern!r}")
            continue
        expected = replacement.format(
            version=version,
            date=date if date is not None else match.group("date"),
        )
        updated = pattern.sub(expected, updated, count=1)

    if updated != content:
        if fix:
            path.write_text(updated, encoding="utf-8")
        else:
            errors.append(f"{path.name}: current version is not v{version}; run with --fix")
    return errors


def main() -> int:
    args = parse_args()
    root = args.root.expanduser().resolve()
    version = read_version(root)

    errors: list[str] = []
    for relative, patterns in VERSION_PATTERNS.items():
        path = root / relative
        if not path.is_file():
            errors.append(f"missing file: {path}")
            continue
        errors.extend(sync_file(path, patterns, version, args.date, args.fix))

    if errors:
        print("FAIL version sync")
        for error in errors:
            print(f"- {error}")
        return 1

    action = "updated" if args.fix else "verified"
    print(f"version_sync={action} v{version}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
