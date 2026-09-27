import re
import unittest
from pathlib import Path

WORKFLOWS = Path(__file__).resolve().parents[1] / ".github" / "workflows"


def workflow_files():
    return sorted(WORKFLOWS.glob("*.yml"))


class WorkflowTests(unittest.TestCase):
    def test_every_action_is_pinned_to_a_full_sha(self):
        for path in workflow_files():
            for line in path.read_text(encoding="utf-8").splitlines():
                if "uses:" in line:
                    self.assertRegex(line, r"uses: [\w./-]+@[0-9a-f]{40} # v", f"{path.name}: {line.strip()}")

    def test_only_github_owned_actions(self):
        for path in workflow_files():
            for owner in re.findall(r"uses: ([\w-]+)/", path.read_text(encoding="utf-8")):
                self.assertIn(owner, {"actions", "github"}, path.name)

    def test_expressions_never_appear_inside_run_scripts(self):
        for path in workflow_files():
            run_indent = None
            for line in path.read_text(encoding="utf-8").splitlines():
                stripped = line.lstrip()
                depth = len(line) - len(stripped)
                if run_indent is not None and stripped and depth <= run_indent:
                    run_indent = None
                if stripped.startswith(("run:", "- run:")):
                    self.assertNotIn("${{", line, f"{path.name}: {stripped}")
                    run_indent = depth
                elif run_indent is not None:
                    self.assertNotIn("${{", line, f"{path.name}: {stripped}")


if __name__ == "__main__":
    unittest.main()
