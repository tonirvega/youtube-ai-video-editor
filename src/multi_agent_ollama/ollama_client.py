"""Small adapter that keeps agents independent from the Ollama SDK."""

from __future__ import annotations

from typing import Protocol


class ChatClient(Protocol):
    def chat(self, *, system: str, user: str) -> str:
        """Return the model response for a single-turn conversation."""


class OllamaClient:
    """Ollama chat client configured for a local model."""

    def __init__(self, model: str) -> None:
        self.model = model

    def chat(self, *, system: str, user: str) -> str:
        try:
            from ollama import chat
        except ImportError as exc:  # pragma: no cover - depende del entorno
            raise RuntimeError(
                "The 'ollama' dependency is missing. Run: pip install -e ."
            ) from exc

        try:
            response = chat(
                model=self.model,
                messages=[
                    {"role": "system", "content": system},
                    {"role": "user", "content": user},
                ],
                options={"temperature": 0.2},
            )
        except Exception as exc:  # pragma: no cover - depende del servicio local
            raise RuntimeError(
                f"Could not contact Ollama using '{self.model}'. "
                "Check that Ollama is running and the model is installed."
            ) from exc

        return response["message"]["content"].strip()
