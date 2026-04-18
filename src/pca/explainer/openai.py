"""OpenAI backend - explicit opt-in only.

This adapter is **disabled unless** ``PCA_ALLOW_CLOUD_LLM=true`` is set AND an
API key is provided. Only structured plan fields are transmitted.
"""

from __future__ import annotations

import os
from collections.abc import Callable
from typing import Any

from pca.explainer.protocol import ExplainPrompt, ExplainResponse

Transport = Callable[[dict[str, Any]], dict[str, Any]]


def _default_transport(body: dict[str, Any]) -> dict[str, Any]:  # pragma: no cover
    import httpx

    api_key = body.pop("_api_key")
    endpoint = body.pop("_endpoint", "https://api.openai.com/v1/chat/completions")
    with httpx.Client(timeout=30) as client:
        r = client.post(
            endpoint,
            json=body,
            headers={"Authorization": f"Bearer {api_key}"},
        )
        r.raise_for_status()
        return r.json()


class OpenAIExplainer:
    """OpenAI Chat Completions adapter. Requires explicit cloud opt-in."""

    name = "openai"

    def __init__(
        self,
        api_key: str | None = None,
        *,
        model: str = "gpt-4o-mini",
        endpoint: str = "https://api.openai.com/v1/chat/completions",
        transport: Transport | None = None,
        cloud_opt_in: bool | None = None,
    ) -> None:
        self._api_key = api_key or os.getenv("OPENAI_API_KEY") or None
        self._model = model
        self._endpoint = endpoint
        self._transport = transport or _default_transport
        env_opt_in = os.getenv("PCA_ALLOW_CLOUD_LLM", "").lower() == "true"
        self._opt_in = env_opt_in if cloud_opt_in is None else bool(cloud_opt_in)

    def is_available(self) -> bool:
        return bool(self._api_key) and self._opt_in

    def explain(self, prompt: ExplainPrompt) -> ExplainResponse:
        if not self.is_available():
            raise RuntimeError(
                "OpenAI backend is disabled. Set PCA_ALLOW_CLOUD_LLM=true and "
                "OPENAI_API_KEY to enable."
            )
        body = {
            "_api_key": self._api_key,
            "_endpoint": self._endpoint,
            "model": self._model,
            "temperature": 0.2,
            "messages": [
                {
                    "role": "system",
                    "content": (
                        "You explain PC upgrade plans in 3-4 sentences. "
                        "Be concise; never invent numbers."
                    ),
                },
                {"role": "user", "content": _render(prompt)},
            ],
        }
        raw = self._transport(body)
        text = str(raw["choices"][0]["message"]["content"]).strip()
        usage = raw.get("usage") or {}
        return ExplainResponse(
            text=text,
            source=self.name,
            tokens_used=int(usage.get("total_tokens", 0) or 0),
        )


def _render(prompt: ExplainPrompt) -> str:
    plan = prompt.plan
    upgrades = "\n".join(
        f"- {i.kind.value}: {i.market_item.vendor} {i.market_item.model} "
        f"(${i.market_item.price_usd:.2f}, +{i.perf_uplift_pct:.1f}%)"
        for i in plan.items
    )
    lines = [
        f"snapshot: {prompt.snapshot_id}",
        f"workload: {prompt.workload.value}",
        f"budget: ${prompt.budget_usd:.2f}",
        f"plan total: ${plan.total_usd:.2f}",
        f"overall uplift: {plan.overall_perf_uplift_pct:.1f}%",
        f"strategy: {plan.strategy}",
        "upgrades:",
        upgrades or "(none)",
    ]
    if prompt.deprecations:
        lines.append("deprecations:\n" + "\n".join(f"- {d}" for d in prompt.deprecations))
    return "\n".join(lines)
