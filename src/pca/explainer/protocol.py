"""LLM explainer protocol + a deterministic fallback."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from pca.core.models import UpgradePlan, Workload


@dataclass(frozen=True)
class ExplainPrompt:
    """Structured prompt. We never include raw hardware serial numbers."""

    plan: UpgradePlan
    snapshot_id: str
    workload: Workload
    deprecations: tuple[str, ...] = ()
    budget_usd: float = 0.0


@dataclass(frozen=True)
class ExplainResponse:
    """Response from an explainer. ``source`` identifies the backend."""

    text: str
    source: str
    tokens_used: int = 0


class LLMExplainer(Protocol):
    """Backends implement this protocol."""

    @property
    def name(self) -> str: ...

    def is_available(self) -> bool: ...

    def explain(self, prompt: ExplainPrompt) -> ExplainResponse: ...


# ---------------------------------------------------------------------------
# Deterministic fallback - always available, no network
# ---------------------------------------------------------------------------


class DeterministicExplainer:
    """Template-based explainer. Used as the floor when no LLM is configured."""

    name = "deterministic"

    def is_available(self) -> bool:
        return True

    def explain(self, prompt: ExplainPrompt) -> ExplainResponse:
        if not prompt.plan.items:
            text = (
                f"No upgrade bundle fit within ${prompt.budget_usd:.0f}. "
                f"Either raise the budget or consider a used-market search."
            )
            return ExplainResponse(text=text, source=self.name)

        upgrades = ", ".join(
            f"{i.kind.value} -> {i.market_item.vendor} {i.market_item.model}"
            for i in prompt.plan.items
        )
        uplift = prompt.plan.overall_perf_uplift_pct
        workload = prompt.workload.value.replace("_", " ")
        deprecations = (
            " Deprecation flags: " + "; ".join(prompt.deprecations)
            if prompt.deprecations
            else ""
        )
        text = (
            f"For {workload} on {prompt.snapshot_id}, the {prompt.plan.strategy} plan "
            f"spends ${prompt.plan.total_usd:.2f} on: {upgrades}. "
            f"Expected overall uplift is {uplift:.1f}%." + deprecations
        )
        return ExplainResponse(text=text, source=self.name)


# ---------------------------------------------------------------------------
# Orchestration
# ---------------------------------------------------------------------------


def explain_plan(
    prompt: ExplainPrompt,
    *,
    backend: LLMExplainer | None = None,
    deterministic_only: bool = False,
) -> ExplainResponse:
    """Return a short paragraph describing ``prompt.plan``.

    Preference order:
      1. ``backend`` if provided and available
      2. ``DeterministicExplainer`` fallback (always)
    """
    if deterministic_only or backend is None or not backend.is_available():
        return DeterministicExplainer().explain(prompt)
    try:
        return backend.explain(prompt)
    except Exception:  # noqa: BLE001 - fall back gracefully on any backend error
        return DeterministicExplainer().explain(prompt)
