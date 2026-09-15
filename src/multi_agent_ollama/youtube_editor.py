"""YouTube-oriented multi-agent video editing workflow.

The workflow turns a transcript and a source video into an auditable edit plan.
When FFmpeg is available, it can render the approved cuts locally.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import tempfile
import urllib.parse
import urllib.request
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Protocol

from .ollama_client import ChatClient, OllamaClient


class KeywordProvider(Protocol):
    def search(self, topic: str) -> list[dict[str, str]]:
        """Return public YouTube search results relevant to a topic."""


class YouTubeDataApiProvider:
    """Small optional adapter for the official YouTube Data API v3."""

    endpoint = "https://www.googleapis.com/youtube/v3/search"

    def __init__(self, api_key: str) -> None:
        self.api_key = api_key

    def search(self, topic: str) -> list[dict[str, str]]:
        params = urllib.parse.urlencode(
            {
                "part": "snippet",
                "type": "video",
                "q": topic,
                "maxResults": 10,
                "order": "relevance",
                "key": self.api_key,
            }
        )
        with urllib.request.urlopen(f"{self.endpoint}?{params}", timeout=15) as response:
            payload = json.load(response)
        return [
            {
                "title": item["snippet"].get("title", ""),
                "description": item["snippet"].get("description", ""),
                "channel": item["snippet"].get("channelTitle", ""),
            }
            for item in payload.get("items", [])
        ]


class OfflineKeywordProvider:
    """Safe fallback that does not claim to provide current keyword data."""

    def search(self, topic: str) -> list[dict[str, str]]:
        return [{"title": topic, "description": "No live keyword data available.", "channel": "offline"}]


@dataclass(frozen=True)
class VideoPlan:
    title: str
    description: str
    tags: list[str]
    chapters: list[dict[str, str]]
    segments: list[dict[str, Any]]

    @classmethod
    def from_json(cls, content: str, duration: float) -> "VideoPlan":
        match = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", content, re.DOTALL)
        raw = match.group(1) if match else content
        try:
            data = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise ValueError("The edit planner did not return valid JSON.") from exc

        required = {"title", "description", "tags", "chapters", "segments"}
        missing = required.difference(data)
        if missing:
            raise ValueError(f"The edit plan is missing: {', '.join(sorted(missing))}")
        if not isinstance(data["segments"], list) or not data["segments"]:
            raise ValueError("The edit plan must include at least one segment.")

        previous_end = 0.0
        for segment in data["segments"]:
            start, end = float(segment["start"]), float(segment["end"])
            if start < 0 or end <= start or end > duration or start < previous_end:
                raise ValueError("Segments must be ordered, non-overlapping, and within the video duration.")
            previous_end = end
        return cls(
            title=str(data["title"]),
            description=str(data["description"]),
            tags=[str(tag) for tag in data["tags"]],
            chapters=list(data["chapters"]),
            segments=list(data["segments"]),
        )

    def as_json(self) -> str:
        return json.dumps(self.__dict__, ensure_ascii=False, indent=2)


class FfmpegRenderer:
    """Render selected segments with predictable, local FFmpeg settings."""

    def __init__(self, ffmpeg: str = "ffmpeg", ffprobe: str = "ffprobe") -> None:
        self.ffmpeg = ffmpeg
        self.ffprobe = ffprobe

    def duration(self, source: Path) -> float:
        command = [
            self.ffprobe, "-v", "error", "-show_entries", "format=duration",
            "-of", "default=noprint_wrappers=1:nokey=1", str(source),
        ]
        result = subprocess.run(command, check=True, capture_output=True, text=True)
        return float(result.stdout.strip())

    def render(self, source: Path, plan: VideoPlan, output: Path, crf: int = 20) -> None:
        if shutil.which(self.ffmpeg) is None:
            raise RuntimeError("FFmpeg was not found. Install it and add it to PATH before rendering.")
        output.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(prefix="youtube-editor-") as temporary:
            temp_dir = Path(temporary)
            parts: list[Path] = []
            for index, segment in enumerate(plan.segments):
                part = temp_dir / f"part-{index:03}.mp4"
                command = [
                    self.ffmpeg, "-y", "-ss", str(segment["start"]), "-to", str(segment["end"]),
                    "-i", str(source), "-map", "0:v:0", "-map", "0:a?", "-c:v", "libx264",
                    "-crf", str(crf), "-preset", "medium", "-c:a", "aac", "-b:a", "192k", str(part),
                ]
                subprocess.run(command, check=True)
                parts.append(part)
            manifest = temp_dir / "concat.txt"
            manifest.write_text("".join(f"file '{part.as_posix()}'\n" for part in parts), encoding="utf-8")
            subprocess.run(
                [self.ffmpeg, "-y", "-f", "concat", "-safe", "0", "-i", str(manifest),
                 "-c", "copy", str(output)],
                check=True,
            )


class YouTubeEditorWorkflow:
    """Research -> edit plan -> review -> revision, with explicit handoffs."""

    def __init__(self, client: ChatClient, keywords: KeywordProvider, output_dir: Path) -> None:
        self.client = client
        self.keywords = keywords
        self.output_dir = output_dir

    def run(self, topic: str, transcript: str, duration: float) -> tuple[Path, VideoPlan, str]:
        if not topic.strip() or not transcript.strip() or duration <= 0:
            raise ValueError("Topic, transcript, and a positive video duration are required.")
        run_dir = self._create_run_directory()
        keyword_data = self.keywords.search(topic)
        research = self.client.chat(
            system=(
                "You are a YouTube Content Strategist. Analyse the supplied public search data "
                "without inventing performance claims. Produce a Markdown brief containing target "
                "audience, search intent, keyword clusters, title angles, and metadata guidance."
            ),
            user=f"Topic: {topic}\n\nPublic search data:\n{json.dumps(keyword_data, ensure_ascii=False)}",
        )
        self._write(run_dir, "keyword_research.json", json.dumps(keyword_data, ensure_ascii=False, indent=2))
        self._write(run_dir, "strategy.md", research)

        draft = self._plan(topic, transcript, duration, research)
        self._write(run_dir, "edit_plan_draft.json", draft.as_json())
        review = self.client.chat(
            system=(
                "You are a Video Editor Reviewer. Check whether the edit plan preserves a coherent "
                "narrative, uses legal time ranges, has accurate metadata, and avoids unsupported "
                "SEO claims. Begin exactly with `DECISION: APPROVED` or `DECISION: CHANGES_REQUESTED`."
            ),
            user=(f"Duration: {duration} seconds\n\nTranscript:\n{transcript}\n\n"
                  f"Strategy:\n{research}\n\nEdit plan:\n{draft.as_json()}"),
        )
        self._write(run_dir, "review.md", review)
        final_plan = draft
        if "DECISION: CHANGES_REQUESTED" in review.upper():
            final_plan = self._plan(topic, transcript, duration, research, draft.as_json(), review)
        self._write(run_dir, "edit_plan.json", final_plan.as_json())
        return run_dir, final_plan, review

    def _plan(self, topic: str, transcript: str, duration: float, research: str,
              previous_plan: str | None = None, review: str | None = None) -> VideoPlan:
        revision_context = ""
        if previous_plan and review:
            revision_context = f"\n\nPrevious plan:\n{previous_plan}\n\nReviewer feedback:\n{review}"
        response = self.client.chat(
            system=(
                "You are a YouTube Video Editor. Build an edit plan that keeps the strongest "
                "narrative beats from the timestamped transcript. Return ONLY valid JSON with keys "
                "title, description, tags, chapters, and segments. Each segment must have numeric "
                "start and end fields plus a reason. Use only timestamps that appear in or are "
                "supported by the transcript. Chapters use timestamp and title fields."
            ),
            user=(f"Topic: {topic}\nVideo duration: {duration} seconds\n\nStrategy:\n{research}"
                  f"\n\nTimestamped transcript:\n{transcript}{revision_context}"),
        )
        return VideoPlan.from_json(response, duration)

    def _create_run_directory(self) -> Path:
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        directory = self.output_dir / stamp
        directory.mkdir(parents=True, exist_ok=False)
        return directory

    @staticmethod
    def _write(directory: Path, name: str, content: str) -> None:
        (directory / name).write_text(content, encoding="utf-8")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Plan and render a YouTube video through a local agent workflow.")
    parser.add_argument("--video", type=Path, required=True, help="Source video file")
    parser.add_argument("--transcript", type=Path, required=True, help="Timestamped transcript in plain text")
    parser.add_argument("--topic", required=True, help="Video topic or initial keyword")
    parser.add_argument("--output", type=Path, default=Path("output/edited-video.mp4"), help="Rendered video path")
    parser.add_argument("--runs-dir", type=Path, default=Path("runs/youtube"), help="Run artifacts directory")
    parser.add_argument("--model", default="qwen3:8b", help="Installed Ollama model")
    parser.add_argument("--youtube-api-key", default=os.getenv("YOUTUBE_API_KEY"), help="YouTube Data API key; defaults to YOUTUBE_API_KEY")
    parser.add_argument("--dry-run", action="store_true", help="Generate and review the plan without rendering video")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    if not args.video.is_file() or not args.transcript.is_file():
        raise SystemExit("Both --video and --transcript must point to existing files.")
    renderer = FfmpegRenderer()
    duration = renderer.duration(args.video)
    provider: KeywordProvider = YouTubeDataApiProvider(args.youtube_api_key) if args.youtube_api_key else OfflineKeywordProvider()
    run_dir, plan, review = YouTubeEditorWorkflow(
        OllamaClient(args.model), provider, args.runs_dir
    ).run(args.topic, args.transcript.read_text(encoding="utf-8"), duration)
    print(f"Plan and metadata saved to: {run_dir}")
    print(f"Review:\n{review}\n\nSuggested title: {plan.title}")
    if not args.dry_run:
        renderer.render(args.video, plan, args.output)
        print(f"Rendered video: {args.output}")


if __name__ == "__main__":
    main()
