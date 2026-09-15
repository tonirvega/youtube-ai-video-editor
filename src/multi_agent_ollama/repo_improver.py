"""A guarded agent workflow for improving this repository.

The default is read-only: agents research the checked-out code and produce an
auditable patch. Applying, committing, and pushing each require explicit flags.
"""

from __future__ import annotations

import argparse
import re
import subprocess
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

from .ollama_client import ChatClient, OllamaClient

ALLOWED_PATHS = ("src/", "tests/", "README.md", "pyproject.toml")


@dataclass(frozen=True)
class ImprovementResult:
    run_directory: Path
    research: str
    patch: str
    review: str
    applied: bool
    committed: bool
    pushed: bool


class RepositoryImprover:
    """Research -> patch -> review -> optional guarded Git publication."""

    def __init__(
        self,
        client: ChatClient,
        repository: Path,
        output_dir: Path,
        progress: Callable[[str], None] | None = None,
    ) -> None:
        self.client = client
        self.repository = repository.resolve()
        self.output_dir = output_dir
        self.progress = progress or (lambda _: None)

    def run(
        self,
        goal: str,
        *,
        apply: bool = False,
        commit: bool = False,
        push: bool = False,
        test_command: str = "python -m unittest discover -s tests -v",
    ) -> ImprovementResult:
        if push and not commit:
            raise ValueError("--push requires --commit")
        if (apply or commit or push) and self._git("status", "--porcelain").stdout.strip():
            raise RuntimeError("The repository has uncommitted changes. Commit or stash them first.")

        run_dir = self._create_run_directory()
        inventory = self._inventory()
        self.progress("1/3 Researching the repository...")
        research = self.client.chat(
            system=(
                "You are a software architecture researcher. Inspect the repository inventory "
                "and identify the single highest-value, low-risk improvement for the stated goal. "
                "Return Markdown covering evidence, proposed change, risks, and acceptance tests. "
                "Do not claim you ran code or accessed the internet."
            ),
            user=f"Goal: {goal}\n\nRepository inventory:\n{inventory}",
        )
        self._write(run_dir, "research.md", research)

        self.progress("2/3 Generating a minimal patch...")
        patch = self._create_patch(goal, inventory, research)
        self._write(run_dir, "developer_response.txt", patch)
        try:
            self._validate_patch(patch)
        except ValueError:
            self.progress("Repairing the patch format...")
            patch = self._repair_patch(goal, research, patch)
            self._validate_patch(patch)
        self._write(run_dir, "proposed.patch", patch)

        self.progress("3/3 Reviewing the proposed patch...")
        review = self.client.chat(
            system=(
                "You are a strict code reviewer. Review the proposed unified diff against the "
                "goal and research. Begin exactly with `DECISION: APPROVED` or "
                "`DECISION: CHANGES_REQUESTED`. Check correctness, tests, scope, and security."
            ),
            user=f"Goal: {goal}\n\nResearch:\n{research}\n\nProposed patch:\n{patch}",
        )
        self._write(run_dir, "review.md", review)
        if "DECISION: APPROVED" not in review.upper():
            raise RuntimeError("Reviewer did not approve the patch; no repository changes were made.")

        applied = committed = pushed = False
        if apply:
            self._git("apply", "--check", input_text=patch)
            self._git("apply", input_text=patch)
            applied = True
        if commit:
            self._run_shell(test_command)
            self._git("add", *ALLOWED_PATHS)
            message = f"Improve MVP: {goal.strip()}"[:72]
            self._git("commit", "-m", message)
            committed = True
        if push:
            self._git("push")
            pushed = True
        return ImprovementResult(run_dir, research, patch, review, applied, committed, pushed)

    def _create_patch(self, goal: str, inventory: str, research: str) -> str:
        response = self.client.chat(
            system=(
                "You are a careful software developer. Produce ONE minimal unified diff that "
                "implements the research recommendation. You may modify only src/, tests/, "
                "README.md, and pyproject.toml. Never alter CI, Docker, credentials, dependencies, "
                "or Git configuration. Include tests when behavior changes. Return only the diff, "
                "optionally inside a ```diff fence."
            ),
            user=f"Goal: {goal}\n\nInventory:\n{inventory}\n\nResearch:\n{research}",
        )
        match = re.search(r"```(?:diff|patch)?\s*(.*?)```", response, re.DOTALL)
        return (match.group(1) if match else response).strip() + "\n"

    def _repair_patch(self, goal: str, research: str, invalid_response: str) -> str:
        response = self.client.chat(
            system=(
                "You are a patch-format repairer. Convert the developer response into ONE complete "
                "unified Git diff. Return only the diff: its first line MUST begin `diff --git a/`. "
                "You may modify only src/, tests/, README.md, and pyproject.toml. Do not explain "
                "your answer and do not use Markdown fences."
            ),
            user=(f"Goal: {goal}\n\nResearch:\n{research}\n\n"
                  f"Developer response to repair:\n{invalid_response}"),
        )
        match = re.search(r"```(?:diff|patch)?\s*(.*?)```", response, re.DOTALL)
        return (match.group(1) if match else response).strip() + "\n"

    def _validate_patch(self, patch: str) -> None:
        if not patch.startswith("diff --git "):
            raise ValueError("Developer output is not a unified Git diff.")
        paths = re.findall(r"^diff --git a/(.+?) b/(.+)$", patch, re.MULTILINE)
        if not paths:
            raise ValueError("Patch does not contain file paths.")
        for old, new in paths:
            for path in (old, new):
                if path == "/dev/null":
                    continue
                if not any(path == allowed or path.startswith(allowed) for allowed in ALLOWED_PATHS):
                    raise ValueError(f"Patch path is not allowed: {path}")

    def _inventory(self) -> str:
        entries: list[str] = []
        for path in sorted(self.repository.rglob("*")):
            if not path.is_file() or ".git" in path.parts or path.suffix in {".pyc", ".mp4"}:
                continue
            relative = path.relative_to(self.repository).as_posix()
            if not any(relative == allowed or relative.startswith(allowed) for allowed in ALLOWED_PATHS):
                continue
            content = path.read_text(encoding="utf-8")[:12000]
            entries.append(f"\n--- {relative} ---\n{content}")
        return "".join(entries)

    def _create_run_directory(self) -> Path:
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        directory = self.output_dir / stamp
        directory.mkdir(parents=True, exist_ok=False)
        return directory

    @staticmethod
    def _write(directory: Path, name: str, content: str) -> None:
        (directory / name).write_text(content, encoding="utf-8")

    def _git(self, *args: str, input_text: str | None = None) -> subprocess.CompletedProcess[str]:
        return subprocess.run(["git", *args], cwd=self.repository, input=input_text, text=True,
                              capture_output=True, check=True)

    def _run_shell(self, command: str) -> None:
        subprocess.run(command, cwd=self.repository, shell=True, check=True)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Research, review, and optionally publish one repository improvement.")
    parser.add_argument("goal", help="Concrete improvement goal for this run")
    parser.add_argument("--repo", type=Path, default=Path.cwd(), help="Repository to inspect")
    parser.add_argument("--runs-dir", type=Path, default=Path("runs/improvements"), help="Audit artifact directory")
    parser.add_argument("--model", default="qwen3:8b", help="Installed Ollama model")
    parser.add_argument("--apply", action="store_true", help="Apply the approved patch to the working tree")
    parser.add_argument("--commit", action="store_true", help="Run tests and commit the applied patch")
    parser.add_argument("--push", action="store_true", help="Push the new commit; requires --commit")
    parser.add_argument("--test-command", default="python -m unittest discover -s tests -v", help="Command run before committing")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    result = RepositoryImprover(OllamaClient(args.model), args.repo, args.runs_dir, print).run(
        args.goal, apply=args.apply, commit=args.commit, push=args.push, test_command=args.test_command
    )
    print(f"Audit artifacts: {result.run_directory}")
    print(f"Applied: {result.applied}; committed: {result.committed}; pushed: {result.pushed}")


if __name__ == "__main__":
    main()
