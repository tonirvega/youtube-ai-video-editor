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
