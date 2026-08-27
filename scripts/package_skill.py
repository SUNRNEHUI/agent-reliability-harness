#!/usr/bin/env python3
"""Verify, copy, and compare the canonical open-layout skill package."""

from __future__ import annotations

import argparse
import filecmp
import shutil
import tempfile
from pathlib import Path


SKILL_NAME = "agent-reliability-harness"
REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SOURCE = REPOSITORY_ROOT / "skills" / SKILL_NAME
REQUIRED_FILES = (
    "VERSION",
    "SKILL.md",
    "agents/openai.yaml",
    "adapters/claude-code.md",
    "adapters/codex.md",
    "adapters/grok.md",
    "adapters/universal.md",
    "references/portable-contract.md",
    "scripts/harnessctl.py",
    "templates/worker_result.json",
)
IGNORED_NAMES = {
    ".DS_Store",
    "__pycache__",
}
FORBIDDEN_NAMES = {
    ".harness",
    "workspace",
}
FORBIDDEN_FILES = {
    "package_skill.py",
    "protocol_regression_harness.py",
    "sync_version.py",
    "test_runtime_behavior.py",
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Verify or copy the canonical skills/ package."
    )
    parser.add_argument(
        "--source",
        type=Path,
        default=DEFAULT_SOURCE,
        help=f"Skill package root. Defaults to skills/{SKILL_NAME}/.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        help="Destination directory for a clean package copy.",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Replace the output directory if it already exists.",
    )
    parser.add_argument(
        "--check",
        type=Path,
        help="Compare the canonical package with an installed skill directory.",
    )
    parser.add_argument(
        "--verify-source",
        action="store_true",
        help="Validate the canonical package without writing files.",
    )
    return parser.parse_args()


def package_files(source: Path) -> list[Path]:
    return sorted(
        path
        for path in source.rglob("*")
        if path.is_file()
        and not any(part in IGNORED_NAMES for part in path.relative_to(source).parts)
    )


def validate_source(source: Path) -> Path:
    source = source.expanduser().resolve()
    missing = [relative for relative in REQUIRED_FILES if not (source / relative).is_file()]
    if missing:
        raise SystemExit(
            f"source does not contain the complete {SKILL_NAME} package: {source}\n"
            + "missing:\n- "
            + "\n- ".join(missing)
        )

    forbidden = [
        path.relative_to(source)
        for path in source.rglob("*")
        if path.name in FORBIDDEN_NAMES or path.name in FORBIDDEN_FILES
    ]
    if forbidden:
        raise SystemExit(
            "repository-only or generated files found in canonical package:\n- "
            + "\n- ".join(str(path) for path in sorted(forbidden))
        )
    return source


def validate_paths(source: Path, output: Path) -> tuple[Path, Path]:
    source = validate_source(source)
    output = output.expanduser().resolve()
    if source == output or source in output.parents:
        raise SystemExit("output must not be the source directory or inside it")
    return source, output


def prepare_output(output: Path, force: bool) -> None:
    if output.exists():
        if not force:
            raise SystemExit(f"output exists; pass --force to replace it: {output}")
        if output.parent == output or str(output) in {"/", str(Path.home())}:
            raise SystemExit(f"refusing to remove unsafe output path: {output}")
        shutil.rmtree(output)
    output.mkdir(parents=True)


def copy_package(source: Path, output: Path) -> None:
    for path in package_files(source):
        relative = path.relative_to(source)
        destination = output / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(path, destination)


def compare_dirs(expected: Path, actual: Path) -> list[str]:
    differences: list[str] = []

    def walk(left: Path, right: Path, relative: Path = Path("")) -> None:
        comparison = filecmp.dircmp(left, right)
        for name in comparison.left_only:
            differences.append(f"missing in install: {relative / name}")
        ignored_generated = {"__pycache__"}
        if relative == Path(""):
            ignored_generated.update({"workspace", ".harness"})
        for name in comparison.right_only:
            if name not in ignored_generated:
                differences.append(f"extra in install: {relative / name}")
        for name in comparison.diff_files:
            differences.append(f"modified in install: {relative / name}")
        for name in comparison.funny_files:
            differences.append(f"unreadable or incompatible: {relative / name}")
        for name in comparison.common_dirs:
            if name != "__pycache__":
                walk(left / name, right / name, relative / name)

    walk(expected, actual)
    return sorted(differences)


def check_install(source: Path, install_dir: Path) -> int:
    source = validate_source(source)
    install_dir = install_dir.expanduser().resolve()
    if not install_dir.is_dir():
        raise SystemExit(f"install directory does not exist: {install_dir}")

    with tempfile.TemporaryDirectory(
        prefix="agent-reliability-harness-package-check-"
    ) as temporary:
        expected = Path(temporary)
        copy_package(source, expected)
        differences = compare_dirs(expected, install_dir)
    if differences:
        print(f"FAIL runtime install differs from canonical package: {install_dir}")
        for difference in differences:
            print(f"- {difference}")
        return 1
    print(f"runtime_install=verified {install_dir}")
    return 0


def main() -> None:
    args = parse_args()
    if args.verify_source:
        source = validate_source(args.source)
        print(f"skill_package=verified {source}")
        return
    if args.check:
        raise SystemExit(check_install(args.source, args.check))
    if args.output is None:
        raise SystemExit("--output is required unless --check or --verify-source is used")

    source, output = validate_paths(args.source, args.output)
    prepare_output(output, args.force)
    copy_package(source, output)
    print(f"skill_package={output}")
    print("created:")
    for path in package_files(source):
        print(f"- {path.relative_to(source)}")


if __name__ == "__main__":
    main()
