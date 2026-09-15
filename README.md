# Multi-Agent Ollama MVP

A local, explainable MVP where three agents genuinely hand work to one another:

```text
Request
  -> Researcher: structured report
  -> Developer: report-based solution
  -> Reviewer: review and decision
  -> Developer: revised solution when needed
  -> Result
```

There is no agent framework hiding the flow: the orchestrator retains every deliverable and explicitly passes it to the next role. This makes the system easy to inspect, debug, and evolve.

## What it does

- **Researcher** scopes the problem, lists assumptions, and proposes a plan.
- **Developer** turns the report into a practical, verifiable solution.
- **Reviewer** assesses the solution against objective criteria and returns `APPROVED` or `CHANGES_REQUESTED`.
- When changes are needed, the **Developer** receives the review and submits a revised version.

Generated artifacts are saved under `runs/<id>/`, so you can inspect exactly what each agent received and produced.

## YouTube video editor workflow

The repository now includes a practical specialization of the agent architecture: a local YouTube video-editor workflow. It takes a source video and a timestamped transcript, then moves work through three focused agents:

```text
YouTube search data -> Content Strategist -> keyword_research.json + strategy.md
Strategy + transcript -> Video Editor -> edit_plan_draft.json
Draft + transcript -> Editor Reviewer -> review.md
Review feedback -> Video Editor -> edit_plan.json
Approved edit plan -> FFmpeg -> edited-video.mp4
```

The planner produces a title, description, tags, chapters, and an ordered list of meaningful video segments. The reviewer can request a revised plan before any video is rendered. FFmpeg then renders the approved segments locally; it never uploads the source video.

### Requirements for video editing

In addition to the base requirements, install FFmpeg and make both `ffmpeg` and `ffprobe` available on `PATH`. Provide a plain-text, timestamped transcript, for example:

```text
[00:00] Today we compare three automatic video editors.
[00:18] First, here is the main problem creators face.
[01:05] This is the recommended workflow.
```

For live YouTube keyword research, create a YouTube Data API v3 key and supply it through `YOUTUBE_API_KEY`. The key is read only from the environment and is never written to a run artifact, log, or repository. Without a key, the workflow still plans and edits videos but clearly uses an offline research fallback rather than pretending to know current trends.

```powershell
$env:YOUTUBE_API_KEY = "your-key"
youtube-video-editor --video .\source.mp4 --transcript .\transcript.txt --topic "automatic video editing" --dry-run
youtube-video-editor --video .\source.mp4 --transcript .\transcript.txt --topic "automatic video editing" --output .\output\edited-video.mp4
```

Start with `--dry-run` to review `edit_plan.json`, the proposed title, description, tags, chapters, and the reviewer feedback. Remove it only when you approve the plan. The workflow makes time-based cuts and standardizes video and audio encoding; it does not yet generate subtitles, b-roll, thumbnails, or publish to YouTube.

## Requirements

- Windows, macOS, or Linux
- Python 3.10+
- [Ollama](https://ollama.com/) running locally
- An installed model, such as `qwen3:8b`

```powershell
ollama pull qwen3:8b
```

## Installation

```powershell
git clone <URL_DEL_REPOSITORIO>
cd multi-agent-ollama
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -e .
```

If PowerShell blocks activation, run the program with `.venv\Scripts\python.exe`.

## Usage

```powershell
python -m multi_agent_ollama "Design a small notes service with a REST API and tests."
```

Useful options:

```powershell
python -m multi_agent_ollama "Your request" --model qwen3:8b --output-dir runs
python -m multi_agent_ollama "Your request" --max-review-cycles 0
```

The summary is displayed in the console, and the full detail is saved in a new directory under `runs/`.

## Architecture

```text
main.py (CLI)
      |
      v
Orchestrator
  |-- ResearcherAgent  -> research.md
  |-- DeveloperAgent   -> implementation.md
  |-- ReviewerAgent    -> review.md
  `-- DeveloperAgent   -> revised_implementation.md (when required)
      |
      v
run_summary.json
```

Each agent is a function with a focused purpose and a clear input contract. `OllamaClient` is the sole infrastructure adapter, so it can be replaced without changing the agent-to-agent protocol.

## Test without Ollama

The tests use a fake client, so they neither download models nor contact the service:

```powershell
python -m unittest discover -s tests -v
```

To verify the command-line interface:

```powershell
python -m multi_agent_ollama --help
```

## Docker

The image includes Python, the project package, FFmpeg, and FFprobe. Build and run the test target locally:

```powershell
docker build --target test --tag youtube-ai-video-editor:test .
docker run --rm youtube-ai-video-editor:test
```

Build the runtime image to generate a plan or render a video. Mount a working directory containing the source video and timestamped transcript. Ollama is expected to be reachable from the container; set `OLLAMA_HOST` when it runs outside the container.

```powershell
docker build --target runtime --tag youtube-ai-video-editor:latest .
docker run --rm -it --mount type=bind,source="${PWD}",target=/work `
  --env OLLAMA_HOST="http://host.docker.internal:11434" `
  --env YOUTUBE_API_KEY `
  youtube-ai-video-editor:latest `
  --video /work/source.mp4 --transcript /work/transcript.txt `
  --topic "automatic video editing" --output /work/output/edited-video.mp4 --dry-run
```

`YOUTUBE_API_KEY` is optional. Do not build it into an image or commit it. The Docker target used in CI contains no credentials and runs only the offline test suite.

## Continuous integration

GitHub Actions runs on every push to `master`, pull request, or manual dispatch. It executes the unit tests twice: once using Python directly and once inside the Docker test image.

## Repository improvement agents

`repo-improver` is a separate, guarded workflow that uses the same three-agent pattern to improve this codebase:

```text
Repository inventory -> Architecture Researcher -> research.md
Research + inventory -> Developer -> proposed.patch
Patch + research -> Reviewer -> review.md
Approved patch -> optional git apply -> optional test + commit -> optional push
```

It is read-only by default. Every run stores the research, exact patch, and review under `runs/improvements/`. The developer is restricted to `src/`, `tests/`, `README.md`, and `pyproject.toml`; it cannot alter workflows, Docker configuration, dependencies, credentials, or Git configuration. A dirty working tree is rejected before any mutation.

First install the package and start Ollama with a local model:

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -e .
ollama pull qwen3:8b
ollama serve
```

In a second PowerShell window, change into the repository and begin with a read-only proposal:

```powershell
repo-improver "Improve the reliability of edit-plan validation"
```

Review `runs/improvements/<timestamp>/research.md`, `proposed.patch`, and `review.md`. When you approve the result, run one new improvement with explicit publication permissions:

```powershell
repo-improver "Improve the reliability of edit-plan validation" --apply --commit --push
```

This command runs the test suite before committing and uses the existing GitHub remote authentication to push. It does not expose or store credentials. The research is limited to the checked-out repository and the model's existing knowledge; add a reviewed web-search provider later if you need current external research.

### Run improvements overnight from Python

The loop is implemented by `repo-improver` itself; it does not require Codex automation or a task scheduler. This example runs seven guarded iterations, one per hour. Each iteration fast-forward pulls the branch, then applies, tests, commits, and pushes only an approved patch that passes `git apply --check`.

```powershell
.\.venv\Scripts\repo-improver.exe "Make one focused, low-risk reliability improvement to the YouTube editor MVP" `
  --model qwen2.5-coder:14b --apply --commit --push --pull `
  --loop --iterations 7 --interval-minutes 60
```

The loop continues after a rejected patch, failed test, or other guarded error, leaving the repository unchanged for that iteration. Stop it at any time with `Ctrl+C`.

## Project structure

```text
src/multi_agent_ollama/
  agents.py        # roles and prompt contracts
  orchestrator.py  # artifact handoff and review cycle
  ollama_client.py # Ollama SDK adapter
  main.py          # CLI
tests/             # workflow tests with a fake client
```

## Suggested evolution

1. Validate deliverables with JSON Schema for more reliable responses.
2. Add role-specific, constrained tools (web, repository, tests).
3. Persist state in SQLite and support resumed runs.
4. Replace the fixed cycle with a review-driven routing policy.
5. Add automated evaluation with reference cases and quality metrics.

## MVP limitations

Agents neither execute code nor browse the web: they reason about the request and exchange text artifacts. This is deliberate, keeping the demo local and safe while proving the work handoff. Review model output before using it in production.
