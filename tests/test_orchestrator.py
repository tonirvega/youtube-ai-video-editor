import tempfile
import unittest
from pathlib import Path

from multi_agent_ollama.orchestrator import Orchestrator


class FakeClient:
    def __init__(self, responses: list[str]) -> None:
        self.responses = iter(responses)
        self.calls: list[dict[str, str]] = []

    def chat(self, *, system: str, user: str) -> str:
        self.calls.append({"system": system, "user": user})
        return next(self.responses)


class OrchestratorTests(unittest.TestCase):
    def test_handoff_and_revision_are_persisted(self) -> None:
        client = FakeClient([
            "Research report",
            "Initial implementation",
            "DECISION: CHANGES_REQUESTED\nAdd tests.",
            "Revised implementation with tests",
        ])
        with tempfile.TemporaryDirectory() as temp_dir:
            result = Orchestrator(client, Path(temp_dir)).run("Build a notes API")

            self.assertTrue(result.revision_requested)
            self.assertEqual(result.final_implementation, "Revised implementation with tests")
            self.assertIn("Research report", client.calls[1]["user"])
            self.assertIn("Initial implementation", client.calls[2]["user"])
            self.assertIn("Add tests.", client.calls[3]["user"])
            self.assertTrue((result.run_directory / "revised_implementation.md").exists())

    def test_approved_delivery_does_not_trigger_revision(self) -> None:
        client = FakeClient([
            "Research report",
            "Initial implementation",
            "DECISION: APPROVED\nLooks good.",
        ])
        with tempfile.TemporaryDirectory() as temp_dir:
            result = Orchestrator(client, Path(temp_dir)).run("Build a notes API")

            self.assertFalse(result.revision_requested)
            self.assertEqual(len(client.calls), 3)
            self.assertEqual(result.final_implementation, "Initial implementation")
