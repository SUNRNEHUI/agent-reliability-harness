from __future__ import annotations

import re
import subprocess
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).parents[1]
SKILL_NAME = "agent-harness"
SKILL_ROOT = ROOT / "skills" / SKILL_NAME


class SkillPackageTests(unittest.TestCase):
    def test_open_skills_layout_is_the_single_canonical_package(self) -> None:
        self.assertTrue((SKILL_ROOT / "SKILL.md").is_file())
        self.assertEqual(list(ROOT.rglob("SKILL.md")), [SKILL_ROOT / "SKILL.md"])
        self.assertFalse((ROOT / "SKILL.md").exists())
        for former_runtime_root in ("adapters", "agents", "references", "templates"):
            with self.subTest(former_runtime_root=former_runtime_root):
                self.assertFalse((ROOT / former_runtime_root).exists())

    def test_skill_frontmatter_has_only_portable_keys(self) -> None:
        text = (SKILL_ROOT / "SKILL.md").read_text(encoding="utf-8")
        self.assertTrue(text.startswith("---\n"))
        _, frontmatter, _ = text.split("---", maxsplit=2)
        fields = {
            match.group(1): match.group(2).strip()
            for match in re.finditer(
                r"(?m)^([A-Za-z][A-Za-z0-9_-]*):\s*(.*)$", frontmatter
            )
        }
        self.assertEqual(set(fields), {"name", "description"})
        self.assertEqual(fields["name"], SKILL_NAME)
        self.assertTrue(fields["description"])

    def test_openai_metadata_invokes_the_canonical_skill(self) -> None:
        text = (SKILL_ROOT / "agents" / "openai.yaml").read_text(encoding="utf-8")
        self.assertIn(f"${SKILL_NAME}", text)
        self.assertIn('display_name: "Agent Harness"', text)

    def test_runtime_package_contains_required_entrypoints(self) -> None:
        required = (
            "VERSION",
            "SKILL.md",
            "agents/openai.yaml",
            "adapters/codex.md",
            "adapters/claude-code.md",
            "adapters/grok.md",
            "adapters/universal.md",
            "references/portable-contract.md",
            "scripts/harnessctl.py",
            "templates/worker_result.json",
        )
        for relative in required:
            with self.subTest(relative=relative):
                self.assertTrue((SKILL_ROOT / relative).is_file())

    def test_runtime_package_excludes_repository_only_assets(self) -> None:
        forbidden_names = {"workspace", ".harness"}
        forbidden_files = {
            "package_skill.py",
            "sync_version.py",
            "test_runtime_behavior.py",
            "protocol_regression_harness.py",
        }
        for path in SKILL_ROOT.rglob("*"):
            if "__pycache__" in path.parts or path.name == ".DS_Store":
                continue
            with self.subTest(path=path):
                self.assertNotIn(path.name, forbidden_names)
                self.assertNotIn(path.name, forbidden_files)

    def test_readmes_document_generic_skill_installation(self) -> None:
        command = (
            "npx skills add "
            "https://github.com/SUNRNEHUI/agent-harness"
        )
        named_command = f'{command} --skill "{SKILL_NAME}"'
        for filename in ("README.md", "README.zh-CN.md"):
            with self.subTest(filename=filename):
                text = (ROOT / filename).read_text(encoding="utf-8")
                self.assertIn(command, text)
                self.assertIn(named_command, text)
                self.assertIn("`skills/`", text)

    def test_public_docs_keep_structural_parity(self) -> None:
        english = (ROOT / "README.md").read_text(encoding="utf-8")
        chinese = (ROOT / "README.zh-CN.md").read_text(encoding="utf-8")
        english_h2 = re.findall(r"(?m)^## ", english)
        chinese_h2 = re.findall(r"(?m)^## ", chinese)
        self.assertEqual(len(english_h2), len(chinese_h2))

    def test_version_references_match_the_package_version(self) -> None:
        completed = subprocess.run(
            [sys.executable, str(ROOT / "scripts" / "sync_version.py")],
            cwd=ROOT,
            text=True,
            capture_output=True,
            check=False,
        )
        self.assertEqual(completed.returncode, 0, completed.stdout + completed.stderr)

    def test_repository_has_no_platform_specific_plugin_package(self) -> None:
        for directory in (".codex-plugin", ".claude-plugin", ".cursor-plugin"):
            with self.subTest(directory=directory):
                self.assertFalse((ROOT / directory).exists())


if __name__ == "__main__":
    unittest.main()
