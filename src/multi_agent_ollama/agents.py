"""Agent roles and their collaboration contracts."""

from __future__ import annotations

from dataclasses import dataclass

from .ollama_client import ChatClient


@dataclass(frozen=True)
class AgentOutput:
    name: str
    content: str


class ResearcherAgent:
    def run(self, request: str, client: ChatClient) -> AgentOutput:
        content = client.chat(
            system=(
                "You are the Researcher. Investigate and structure the problem without "
                "inventing facts. Return a Markdown report covering: objective, requirements, "
                "assumptions, risks, and an implementation plan. Your text is the only "
                "research the Developer will receive."
            ),
            user=f"User request:\n{request}",
        )
        return AgentOutput("research", content)


class DeveloperAgent:
    def run(self, request: str, research: str, client: ChatClient) -> AgentOutput:
        content = client.chat(
            system=(
                "You are the Developer. Produce a concrete, practical, and verifiable "
                "technical proposal. Follow the provided report and identify uncertainty. "
                "Include design, steps, examples or pseudocode where useful, and "
                "acceptance tests."
            ),
            user=(
                f"Original request:\n{request}\n\n"
                f"Researcher report (you must use it):\n{research}"
            ),
        )
        return AgentOutput("implementation", content)

    def revise(
        self, request: str, research: str, implementation: str, review: str, client: ChatClient
    ) -> AgentOutput:
        content = client.chat(
            system=(
                "You are the Developer and must revise your delivery. Address every issue "
                "identified by the Reviewer. Return a complete revised implementation, "
                "not merely a list of changes."
            ),
            user=(
                f"Original request:\n{request}\n\nReport:\n{research}\n\n"
                f"Initial delivery:\n{implementation}\n\nReview received:\n{review}"
            ),
        )
        return AgentOutput("revised_implementation", content)


class ReviewerAgent:
    def run(self, request: str, research: str, implementation: str, client: ChatClient) -> AgentOutput:
        content = client.chat(
            system=(
                "You are the Reviewer. Rigorously assess the delivery against the request "
                "and report. Begin exactly with `DECISION: APPROVED` or "
                "`DECISION: CHANGES_REQUESTED`. Then explain prioritized findings and "
                "verifiable acceptance criteria."
            ),
            user=(
                f"Original request:\n{request}\n\nReport:\n{research}\n\n"
                f"Delivery to review:\n{implementation}"
            ),
        )
        return AgentOutput("review", content)
