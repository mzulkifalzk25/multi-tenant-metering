"""LLM integration used by the document processor to analyze a work unit.

Kept as a narrow Protocol + swappable implementations so ``DocumentProcessor``
never depends on a specific provider. ``NullLLMService`` is the default and
is what unit/integration tests use; ``OpenRouterLLMService`` is the real
network-calling implementation wired in when ``LLM_API_KEY`` is configured.
"""

from __future__ import annotations

import asyncio
import json
import urllib.request
from typing import Protocol

from src.entities.job import Job
from src.entities.work_unit import WorkUnit
from src.shared.errors import DocumentProcessingError

_OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"


class LLMServiceProtocol(Protocol):
    async def analyze(self, job: Job, work_unit: WorkUnit) -> str:
        ...


class NullLLMService:
    """No-op implementation: returns a deterministic placeholder without
    making any network call. Used whenever no LLM API key is configured."""

    async def analyze(self, job: Job, work_unit: WorkUnit) -> str:
        unit = f"{work_unit.unit_type.value} #{work_unit.unit_number}"
        return f"skipped: no LLM configured for {unit}"


class OpenRouterLLMService:
    def __init__(self, api_key: str, model: str) -> None:
        self._api_key = api_key
        self._model = model

    async def analyze(self, job: Job, work_unit: WorkUnit) -> str:
        prompt = (
            f"Summarize {work_unit.unit_type.value} #{work_unit.unit_number} "
            f"of document at {job.file_path}."
        )
        return await asyncio.to_thread(self._call_openrouter, prompt)

    def _call_openrouter(self, prompt: str) -> str:
        body = json.dumps(
            {
                "model": self._model,
                "messages": [{"role": "user", "content": prompt}],
            }
        ).encode("utf-8")
        request = urllib.request.Request(
            _OPENROUTER_URL,
            data=body,
            method="POST",
            headers={
                "Authorization": f"Bearer {self._api_key}",
                "Content-Type": "application/json",
            },
        )
        try:
            with urllib.request.urlopen(request, timeout=30) as response:
                payload = json.loads(response.read().decode("utf-8"))
        except OSError as exc:
            raise DocumentProcessingError(f"LLM call failed: {exc}") from exc
        choices = payload.get("choices", [])
        if not choices:
            raise DocumentProcessingError("LLM response contained no choices")
        content = choices[0].get("message", {}).get("content", "")
        return str(content)
