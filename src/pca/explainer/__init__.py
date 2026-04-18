"""Natural-language explainer for upgrade plans.

Default backend is **local Ollama** so no data leaves the host. A remote
backend (OpenAI) is available opt-in and off by default; it sends only the
structured plan summary - never component serial numbers, OS build strings,
or other identifying fields.

The top-level API is :func:`explain_plan`. Callers pass an ``UpgradePlan``
and a snapshot ID; we return a short paragraph suitable for inclusion in
the HTML report. When no LLM backend is configured, we fall back to a
deterministic template so the CLI never blocks on a missing LLM.
"""

from __future__ import annotations

from pca.explainer.protocol import (
    LLMExplainer,
    ExplainPrompt,
    ExplainResponse,
    DeterministicExplainer,
    explain_plan,
)

__all__ = [
    "DeterministicExplainer",
    "ExplainPrompt",
    "ExplainResponse",
    "LLMExplainer",
    "explain_plan",
]
