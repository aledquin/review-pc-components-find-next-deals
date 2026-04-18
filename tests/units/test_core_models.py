"""Unit tests for ``src/pca/core/models.py``.

These tests are pure-logic and must not touch the network or a real FS
beyond ``tmp_path``. Enforced globally by ``tests/units/conftest.py``.
"""

from __future__ import annotations

import json
from datetime import UTC, date, datetime
from decimal import Decimal

import pytest
from pydantic import ValidationError

from pca.core.models import (
    Benchmark,
    BudgetConstraint,
    Component,
    ComponentKind,
    Deal,
    MarketItem,
    OsInfo,
    Quote,
    Report,
    StockStatus,
    SystemSnapshot,
    UpgradeItem,
    UpgradePlan,
    Workload,
    export_schemas,
)


def _cpu() -> Component:
    return Component(
        id="cpu-1",
        kind=ComponentKind.CPU,
        vendor="AMD",
        model="Ryzen 5 5600X",
        specs={"cores": 6, "threads": 12, "socket": "AM4"},
        acquired_at=date(2021, 3, 1),
    )


def _market_cpu() -> MarketItem:
    return MarketItem(
        sku="BB-5600X",
        kind=ComponentKind.CPU,
        vendor="AMD",
        model="Ryzen 5 5600X",
        price_usd=Decimal("149.99"),
        source="bestbuy",
        url="https://example.test/5600x",
        stock=StockStatus.IN_STOCK,
        fetched_at=datetime(2025, 1, 1, 12, 0, tzinfo=UTC),
        perf_score=820.0,
    )


class TestComponent:
    def test_minimal_component_is_valid(self):
        c = _cpu()
        assert c.kind is ComponentKind.CPU
        assert c.specs["cores"] == 6

    def test_component_is_frozen(self):
        c = _cpu()
        with pytest.raises(ValidationError):
            c.vendor = "Intel"  # type: ignore[misc]

    def test_component_rejects_unknown_fields(self):
        with pytest.raises(ValidationError):
            Component(  # type: ignore[call-arg]
                id="x",
                kind=ComponentKind.CPU,
                vendor="AMD",
                model="5600X",
                bogus="nope",
            )

    def test_specs_must_be_jsonable(self):
        with pytest.raises(ValidationError):
            Component(
                id="x",
                kind=ComponentKind.CPU,
                vendor="AMD",
                model="5600X",
                specs={"bad": object()},
            )


class TestBenchmark:
    def test_finite_values_only(self):
        with pytest.raises(ValidationError):
            Benchmark(
                id="b1",
                component_id="cpu-1",
                metric="cpu.sysbench.events_per_sec",
                value=float("inf"),
                unit="ev/s",
                env_hash="deadbeef",
                ran_at=datetime(2025, 1, 1, tzinfo=UTC),
            )

    def test_env_hash_min_length(self):
        with pytest.raises(ValidationError):
            Benchmark(
                id="b1",
                component_id="cpu-1",
                metric="m",
                value=1.0,
                unit="u",
                env_hash="abc",
                ran_at=datetime(2025, 1, 1, tzinfo=UTC),
            )


class TestSystemSnapshot:
    def test_components_of_filters_by_kind(self):
        snap = SystemSnapshot(
            id="s1",
            components=(_cpu(),),
            os_info=OsInfo(family="Windows", version="11", build="22631"),
            captured_at=datetime(2025, 1, 1, tzinfo=UTC),
        )
        assert len(snap.components_of(ComponentKind.CPU)) == 1
        assert snap.components_of(ComponentKind.GPU) == ()


class TestMarketItem:
    def test_price_must_be_non_negative(self):
        with pytest.raises(ValidationError):
            MarketItem(
                sku="x",
                kind=ComponentKind.CPU,
                vendor="v",
                model="m",
                price_usd=Decimal("-1.00"),
                source="s",
                url="u",
                fetched_at=datetime(2025, 1, 1, tzinfo=UTC),
            )


class TestBudgetConstraint:
    def test_positive_budget_required(self):
        with pytest.raises(ValidationError):
            BudgetConstraint(max_usd=Decimal("0"))

    def test_defaults_sweet_spot_and_1440p(self):
        b = BudgetConstraint(max_usd=Decimal("800"))
        assert b.tier.value == "sweet_spot"
        assert b.target_workload is Workload.GAMING_1440P


class TestUpgradePlanAndQuote:
    def test_quote_contains_plan_and_totals(self):
        item = UpgradeItem(
            kind=ComponentKind.CPU,
            market_item=_market_cpu(),
            perf_uplift_pct=35.0,
            rationale="eliminates CPU bottleneck",
        )
        plan = UpgradePlan(
            items=(item,),
            total_usd=Decimal("149.99"),
            overall_perf_uplift_pct=18.0,
            bottlenecks_resolved=("cpu",),
            rationale="greedy",
            strategy="greedy",
        )
        quote = Quote(
            plan=plan,
            tax_usd=Decimal("12.37"),
            shipping_usd=Decimal("0.00"),
            grand_total_usd=Decimal("162.36"),
            generated_at=datetime(2025, 1, 1, 12, 0, tzinfo=UTC),
            deals=(
                Deal(
                    market_item_sku="BB-5600X",
                    source="bestbuy",
                    discount_pct=10.0,
                ),
            ),
        )
        assert quote.plan.items[0].perf_uplift_pct == 35.0
        assert quote.grand_total_usd == Decimal("162.36")


class TestJsonRoundtrip:
    def test_snapshot_roundtrip(self):
        snap = SystemSnapshot(
            id="s1",
            components=(_cpu(),),
            os_info=OsInfo(family="Windows", version="11"),
            captured_at=datetime(2025, 1, 1, tzinfo=UTC),
        )
        blob = snap.model_dump_json()
        restored = SystemSnapshot.model_validate_json(blob)
        assert restored == snap


class TestSchemaExport:
    def test_export_writes_one_schema_per_entity(self, tmp_path):
        out = tmp_path / "schemas"
        written = export_schemas(out)
        names = {p.name for p in written}
        expected = {
            "Component.schema.json",
            "Benchmark.schema.json",
            "SystemSnapshot.schema.json",
            "MarketItem.schema.json",
            "Deal.schema.json",
            "BudgetConstraint.schema.json",
            "UpgradeItem.schema.json",
            "UpgradePlan.schema.json",
            "Quote.schema.json",
            "Report.schema.json",
        }
        assert expected <= names
        doc = json.loads((out / "Component.schema.json").read_text())
        assert doc["title"] == "Component"
        assert "properties" in doc

    def test_report_has_required_json_path(self):
        r = Report(snapshot_id="s1", json_path="/tmp/r.json")
        assert r.html_path is None
        assert r.pdf_path is None
