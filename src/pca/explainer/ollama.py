"""Local Ollama backend for the LLM explainer.

Default endpoint is ``http://127.0.0.1:11434/api/generate``. Transport is
injected so tests can replay fixtures without a running Ollama instance.

Privacy posture:
- Only structured prompt fields are sent: kind, vendor, model, price, uplift,
  workload, deprecation flags, snapshot id (UUID). Hardware serials, OS build
  strings, and user account names are never included.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from typing import Any

from pca.explainer.protocol import ExplainPrompt, ExplainResponse

Transport = Callable[[dict[str, Any]], dict[str, Any]]


def _default_transport(body: dict[str, Any]) -> dict[str, Any]:
    import httpx

    endpoint = body.pop("_endpoint", "http://127.0.0.1:11434/api/generate")
    with httpx.Client(timeout=30) as client:
        r = client.post(endpoint, json=body)
        r.raise_for_status()
        return r.json()


class OllamaExplainer:
    """Calls a locally hosted Ollama model. Default: ``llama3.1:8b``."""

    name = "ollama"

    def __init__(
        self,
        *,
        model: str = "llama3.1:8b",
        endpoint: str = "http://127.0.0.1:11434/api/generate",
        transport: Transport | None = None,
    ) -> None:
        self._model = model
        self._endpoint = endpoint
        self._transport = transport or _default_transport

    def is_available(self) -> bool:
        # We can't probe the server in is_available() without a network call;
        # we trust the caller to have enabled ollama intentionally. If the
        # server is down the Transport raises and `explain_plan` falls back.
        return True

    def explain(self, prompt: ExplainPrompt) -> ExplainResponse:
        body = {
            "_endpoint": self._endpoint,
            "model": self._model,
            "stream": False,
            "options": {"temperature": 0.2},
            "prompt": _render(prompt),
        }
        raw = self._transport(body)
        text = str(raw.get("response", "")).strip()
        if not text:
            raise RuntimeError("ollama returned empty response")
        tokens = int(raw.get("eval_count", 0) or 0)
        return ExplainResponse(text=text, source=self.name, tokens_used=tokens)


def _render(prompt: ExplainPrompt) -> str:
    plan = prompt.plan
    upgrades = "\n".join(
        f"  - {i.kind.value}: {i.market_item.vendor} {i.market_item.model} "
        f"(${i.market_item.price_usd:.2f}, +{i.perf_uplift_pct:.1f}%)"
        for i in plan.items
    )
    dep = (
        "\nDeprecation flags:\n  - " + "\n  - ".join(prompt.deprecations)
        if prompt.deprecations
        else "\nNo deprecation warnings."
    )
    return json.dumps(
        {
            "instructions": (
                "Explain in 3-4 sentences why this upgrade bundle makes sense. "
                "Avoid marketing language. Quote only the data below."
            ),
            "snapshot": prompt.snapshot_id,
            "workload": prompt.workload.value,
            "budget_usd": prompt.budget_usd,
            "total_usd": float(plan.total_usd),
            "overall_uplift_pct": plan.overall_perf_uplift_pct,
            "strategy": plan.strategy,
            "upgrades": upgrades,
            "deprecations": dep,
        },
        indent=2,
    )
