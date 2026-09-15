"""Command-line entry point."""

from __future__ import annotations

import argparse
from pathlib import Path

from .ollama_client import OllamaClient
from .orchestrator import Orchestrator


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Local three-agent MVP using Ollama")
    parser.add_argument("request", help="Work that the agents must solve")
    parser.add_argument("--model", default="qwen3:8b", help="Model installed in Ollama")
    parser.add_argument("--output-dir", type=Path, default=Path("runs"), help="Artifact directory")
    parser.add_argument("--max-review-cycles", type=int, default=1, help="Maximum Developer revision cycles")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    client = OllamaClient(args.model)
    result = Orchestrator(client, args.output_dir, args.max_review_cycles).run(args.request)
    print(f"Run completed: {result.run_directory}")
    print("\n--- Review ---")
    print(result.review)
    print("\n--- Final delivery ---")
    print(result.final_implementation)


if __name__ == "__main__":
    main()
