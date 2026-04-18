"""Unit tests for the LLM explainer plumbing."""

from __future__ import annotations

from decimal import Decimal
from typing import Any

import pytest

from pca.budget.optimizer_greedy import optimize_greedy
from pca.core.models import BudgetConstraint, Workload
from pca.explainer import (
    DeterministicExplainer,
    ExplainPrompt,
    LLMExplainer,
    explain_plan,
)
from pca.explainer.ollama import OllamaExplainer
from pca.explainer.openai import OpenAIExplainer
from tests.fixtures import load_market_snapshot, load_rig


@pytest.fixture
def prompt() -> ExplainPrompt:
    snap = load_rig("rig_budget")
    items, _ = load_market_snapshot("snapshot_normal")
    constraint = BudgetConstraint(
        max_usd=Decimal("1000"),
        target_workload=Workload.GAMING_1440P,
    )
    plan = optimize_greedy(snap, constraint, items)
    return ExplainPrompt(
        plan=plan,
        snapshot_id=snap.id,
        workload=Workload.GAMING_1440P,
        deprecations=("LGA1151 socket is end-of-life",),
        budget_usd=float(constraint.max_usd),
    )


def test_deterministic_is_always_available() -> None:
    exp = DeterministicExplainer()
    assert exp.is_available() is True


def test_deterministic_mentions_strategy_and_budget(prompt: ExplainPrompt) -> None:
    resp = DeterministicExplainer().explain(prompt)
    assert resp.source == "deterministic"
    assert prompt.plan.strategy in resp.text
    assert str(int(prompt.plan.total_usd)) in resp.text


def test_explain_plan_falls_back_to_deterministic(prompt: ExplainPrompt) -> None:
    resp = explain_plan(prompt, backend=None)
    assert resp.source == "deterministic"


def test_explain_plan_uses_backend_when_available(prompt: ExplainPrompt) -> None:
    class Fake:
        name = "fake-llm"

        def is_available(self) -> bool:
            return True

        def explain(self, p: ExplainPrompt):
            from pca.explainer.protocol import ExplainResponse

            return ExplainResponse(text="FAKE OUTPUT", source=self.name, tokens_used=42)

    resp = explain_plan(prompt, backend=Fake())
    assert resp.text == "FAKE OUTPUT"
    assert resp.source == "fake-llm"


def test_explain_plan_falls_back_on_backend_error(prompt: ExplainPrompt) -> None:
    class Broken:
        name = "broken"

        def is_available(self) -> bool:
            return True

        def explain(self, _: ExplainPrompt):
            raise RuntimeError("503")

    resp = explain_plan(prompt, backend=Broken())
    assert resp.source == "deterministic"


def test_ollama_uses_injected_transport(prompt: ExplainPrompt) -> None:
    def fake(body: dict[str, Any]) -> dict[str, Any]:
        assert body["model"].startswith("llama")
        assert body["stream"] is False
        return {"response": "From llama.", "eval_count": 123}

    backend = OllamaExplainer(transport=fake)
    resp = backend.explain(prompt)
    assert resp.text == "From llama."
    assert resp.source == "ollama"
    assert resp.tokens_used == 123


def test_openai_disabled_by_default(monkeypatch, prompt: ExplainPrompt) -> None:
    monkeypatch.delenv("PCA_ALLOW_CLOUD_LLM", raising=False)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    backend = OpenAIExplainer()
    assert backend.is_available() is False


def test_openai_requires_both_flag_and_key(monkeypatch, prompt: ExplainPrompt) -> None:
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    backend_no_key = OpenAIExplainer(cloud_opt_in=True)
    assert backend_no_key.is_available() is False
    backend_ok = OpenAIExplainer(api_key="sk-test", cloud_opt_in=True)
    assert backend_ok.is_available() is True


def test_openai_sends_redacted_content_only(prompt: ExplainPrompt) -> None:
    captured: dict[str, Any] = {}

    def fake(body: dict[str, Any]) -> dict[str, Any]:
        captured.update(body)
        return {
            "choices": [{"message": {"content": "explained."}}],
            "usage": {"total_tokens": 50},
        }

    backend = OpenAIExplainer(
        api_key="sk-test",
        cloud_opt_in=True,
        transport=fake,
    )
    resp = backend.explain(prompt)
    assert resp.source == "openai"
    payload = "\n".join(m["content"] for m in captured["messages"])
    assert "snapshot:" in payload
    # Verify we didn't leak any serial-ish field the way our prompt renders it.
    for forbidden in ("SerialNumber", "MachineGuid", "BuildNumber"):
        assert forbidden not in payload


def test_protocol_is_structural(prompt: ExplainPrompt) -> None:
    # Any duck-typed object implementing the three members should satisfy.
    class DuckExplainer:
        name = "duck"

        def is_available(self) -> bool:
            return False

        def explain(self, _: ExplainPrompt):
            raise NotImplementedError

    backend: LLMExplainer = DuckExplainer()  # type: ignore[assignment]
    assert backend.name == "duck"
