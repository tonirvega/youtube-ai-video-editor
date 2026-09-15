import tempfile
import unittest
from pathlib import Path

from multi_agent_ollama.repo_improver import RepositoryImprover


PATCH = """diff --git a/README.md b/README.md
index 1111111..2222222 100644
--- a/README.md
+++ b/README.md
@@ -1 +1 @@
-Old
+New
"""


class FakeClient:
    def __init__(self, responses=None):
        self.responses = iter(responses or ["Research", f"```diff\n{PATCH}```", "DECISION: APPROVED\nLooks good."])

    def chat(self, *, system, user):
        return next(self.responses)


class RepositoryImproverTests(unittest.TestCase):
    def test_read_only_run_saves_auditable_artifacts(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / ".git").mkdir()
            (root / "README.md").write_text("Old", encoding="utf-8")
            workflow = RepositoryImprover(FakeClient(), root, root / "runs")
            result = workflow.run("Improve documentation")

            self.assertFalse(result.applied)
            self.assertEqual(result.patch, PATCH)
            self.assertTrue((result.run_directory / "research.md").exists())

    def test_disallowed_patch_path_is_rejected(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            workflow = RepositoryImprover(FakeClient(), root, root / "runs")
            with self.assertRaises(ValueError):
                workflow._validate_patch(PATCH.replace("README.md", ".github/workflows/ci.yml"))

    def test_invalid_patch_is_repaired_once(self):
        client = FakeClient(["Research", "Here is a suggestion.", PATCH, "DECISION: APPROVED"])
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / ".git").mkdir()
            (root / "README.md").write_text("Old", encoding="utf-8")
            result = RepositoryImprover(client, root, root / "runs").run("Improve documentation")

            self.assertEqual(result.patch, PATCH)
            self.assertTrue((result.run_directory / "developer_response.txt").exists())
