"""Orchestrate explicit artifact handoffs between agents."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from .agents import DeveloperAgent, ResearcherAgent, ReviewerAgent
from .ollama_client import ChatClient


@dataclass(frozen=True)
class RunResult:
    run_directory: Path
    research: str
    implementation: str
    review: str
    final_implementation: str
    revision_requested: bool


class Orchestrator:
    def __init__(self, client: ChatClient, output_dir: Path, max_review_cycles: int = 1) -> None:
        if max_review_cycles < 0:
            raise ValueError("max_review_cycles cannot be negative")
        self.client = client
        self.output_dir = output_dir
        self.max_review_cycles = max_review_cycles
        self.researcher = ResearcherAgent()
        self.developer = DeveloperAgent()
        self.reviewer = ReviewerAgent()

    def run(self, request: str) -> RunResult:
        if not request.strip():
            raise ValueError("The request cannot be empty")

        run_dir = self._create_run_directory()
        research = self.researcher.run(request, self.client).content
        self._write(run_dir, "research.md", research)

        implementation = self.developer.run(request, research, self.client).content
        self._write(run_dir, "implementation.md", implementation)

        review = self.reviewer.run(request, research, implementation, self.client).content
        self._write(run_dir, "review.md", review)

        revision_requested = "DECISION: CHANGES_REQUESTED" in review.upper()
        final_implementation = implementation
        if revision_requested and self.max_review_cycles:
            final_implementation = self.developer.revise(
                request, research, implementation, review, self.client
            ).content
            self._write(run_dir, "revised_implementation.md", final_implementation)

        summary = {
            "request": request,
            "revision_requested": revision_requested,
            "revision_performed": revision_requested and bool(self.max_review_cycles),
        }
        self._write(run_dir, "run_summary.json", json.dumps(summary, ensure_ascii=False, indent=2))
        return RunResult(run_dir, research, implementation, review, final_implementation, revision_requested)

    def _create_run_directory(self) -> Path:
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        run_dir = self.output_dir / timestamp
        counter = 1
        while run_dir.exists():
            run_dir = self.output_dir / f"{timestamp}-{counter}"
            counter += 1
        run_dir.mkdir(parents=True)
        return run_dir

    @staticmethod
    def _write(directory: Path, name: str, content: str) -> None:
        (directory / name).write_text(content, encoding="utf-8")
