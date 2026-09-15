import json
import tempfile
import unittest
from pathlib import Path

from multi_agent_ollama.youtube_editor import OfflineKeywordProvider, YouTubeEditorWorkflow


class FakeClient:
    def __init__(self, responses):
        self.responses = iter(responses)
        self.calls = []

    def chat(self, *, system, user):
        self.calls.append({"system": system, "user": user})
        return next(self.responses)


def plan(title="Draft title"):
    return json.dumps({
        "title": title,
        "description": "An accurate description.",
        "tags": ["video editing"],
        "chapters": [{"timestamp": "00:00", "title": "Introduction"}],
        "segments": [{"start": 0, "end": 10, "reason": "Strong hook"}],
    })


class YouTubeEditorWorkflowTests(unittest.TestCase):
    def test_reviewer_feedback_reaches_the_revised_plan(self):
        client = FakeClient([
            "# Strategy\nUse factual metadata.", plan(), "DECISION: CHANGES_REQUESTED\nImprove the title.", plan("Revised title"),
        ])
        with tempfile.TemporaryDirectory() as temporary:
            directory, result, _ = YouTubeEditorWorkflow(
                client, OfflineKeywordProvider(), Path(temporary)
            ).run("video editing", "[00:00] A strong hook", 30)

            self.assertEqual(result.title, "Revised title")
            self.assertIn("Improve the title.", client.calls[3]["user"])
            self.assertTrue((directory / "edit_plan.json").exists())

    def test_invalid_segment_is_rejected(self):
        client = FakeClient(["Strategy", plan(), "DECISION: APPROVED"])
        with tempfile.TemporaryDirectory() as temporary:
            with self.assertRaises(ValueError):
                YouTubeEditorWorkflow(client, OfflineKeywordProvider(), Path(temporary)).run(
                    "topic", "[00:00] words", 5
                )
