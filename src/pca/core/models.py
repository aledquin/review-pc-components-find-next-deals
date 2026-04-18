"""Pydantic v2 domain models for PC Upgrade Advisor.

All public entities live here so the schema is a single source of truth.
JSON schemas are exported to ``resources/schemas/`` by :func:`export_schemas`.
"""

from __future__ import annotations

import json
from datetime import date, datetime
from decimal import Decimal
from enum import StrEnum
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------


class ComponentKind(StrEnum):
    """Canonical component categories. Stable string values: used in golden files."""

    CPU = "cpu"
    GPU = "gpu"
    RAM = "ram"
    MOTHERBOARD = "motherboard"
    STORAGE = "storage"
    PSU = "psu"
    COOLER = "cooler"
    CASE = "case"
    PERIPHERAL = "peripheral"
    OS = "os"


class StockStatus(StrEnum):
    IN_STOCK = "in_stock"
    LOW_STOCK = "low_stock"
    OUT_OF_STOCK = "out_of_stock"
    UNKNOWN = "unknown"


class Workload(StrEnum):
    """Target workloads that drive the perf-score weighting."""

    GAMING_1080P = "gaming_1080p"
    GAMING_1440P = "gaming_1440p"
    GAMING_4K = "gaming_4k"
    PRODUCTIVITY = "productivity"
    CONTENT_CREATION = "content_creation"
    ML_WORKSTATION = "ml_workstation"


class BudgetTier(StrEnum):
    MIN_VIABLE = "min_viable"
    SWEET_SPOT = "sweet_spot"
    NO_COMPROMISE = "no_compromise"


# ---------------------------------------------------------------------------
# Base
# ---------------------------------------------------------------------------


class _Base(BaseModel):
    """Shared model config. Frozen for hashability + deterministic golden tests."""

    model_config = ConfigDict(
        extra="forbid",
        frozen=True,
        populate_by_name=True,
        str_strip_whitespace=True,
        use_enum_values=False,
    )


# ---------------------------------------------------------------------------
# Inventory entities
# ---------------------------------------------------------------------------


class Component(_Base):
    id: str = Field(min_length=1, description="Stable local identifier (UUID or slug).")
    kind: ComponentKind
    vendor: str = Field(min_length=1)
    model: str = Field(min_length=1)
    specs: dict[str, Any] = Field(default_factory=dict)
    acquired_at: date | None = None

    @field_validator("specs")
    @classmethod
    def _specs_must_be_jsonable(cls, v: dict[str, Any]) -> dict[str, Any]:
        try:
            json.dumps(v)
        except (TypeError, ValueError) as exc:
            raise ValueError(f"specs must be JSON-serializable: {exc}") from exc
        return v


class Benchmark(_Base):
    id: str = Field(min_length=1)
    component_id: str = Field(min_length=1)
    metric: str = Field(min_length=1, description="e.g. 'cpu.sysbench.events_per_sec'.")
    value: float
    unit: str = Field(min_length=1)
    env_hash: str = Field(min_length=8, description="Hash of the benchmark environment.")
    ran_at: datetime

    @field_validator("value")
    @classmethod
    def _value_is_finite(cls, v: float) -> float:
        import math

        if not math.isfinite(v):
            raise ValueError("benchmark value must be finite")
        return v


class OsInfo(_Base):
    family: str = Field(min_length=1)
    version: str = Field(min_length=1)
    build: str | None = None
    arch: str | None = None


class SystemSnapshot(_Base):
    id: str = Field(min_length=1)
    components: tuple[Component, ...] = ()
    benchmarks: tuple[Benchmark, ...] = ()
    os_info: OsInfo
    captured_at: datetime

    def components_of(self, kind: ComponentKind) -> tuple[Component, ...]:
        return tuple(c for c in self.components if c.kind == kind)


# ---------------------------------------------------------------------------
# Market entities
# ---------------------------------------------------------------------------


class MarketItem(_Base):
    sku: str = Field(min_length=1, description="Retailer SKU or source-unique id.")
    kind: ComponentKind
    vendor: str = Field(min_length=1)
    model: str = Field(min_length=1)
    price_usd: Decimal = Field(ge=Decimal("0"))
    source: str = Field(min_length=1, description="Adapter name: 'bestbuy', 'amazon-paapi', ...")
    url: str = Field(min_length=1)
    stock: StockStatus = StockStatus.UNKNOWN
    fetched_at: datetime
    specs: dict[str, Any] = Field(default_factory=dict)
    perf_score: float | None = Field(
        default=None, description="Pre-computed normalized performance score."
    )


class Deal(_Base):
    market_item_sku: str = Field(min_length=1)
    source: str = Field(min_length=1)
    discount_pct: float = Field(ge=0.0, le=100.0)
    expires_at: datetime | None = None
    coupon_code: str | None = None
    original_price_usd: Decimal | None = None


# ---------------------------------------------------------------------------
# Budget, upgrade plan, quote
# ---------------------------------------------------------------------------


class BudgetConstraint(_Base):
    max_usd: Decimal = Field(gt=Decimal("0"))
    socket: str | None = None
    ram_type: str | None = None
    psu_watts_min: int | None = Field(default=None, ge=0)
    form_factor: str | None = None
    noise_dba_max: float | None = Field(default=None, ge=0.0)
    preferred_brands: tuple[str, ...] = ()
    tier: BudgetTier = BudgetTier.SWEET_SPOT
    target_workload: Workload = Workload.GAMING_1440P


class UpgradeItem(_Base):
    """A single (replace X with Y) entry inside an UpgradePlan."""

    replaces_component_id: str | None = None
    kind: ComponentKind
    market_item: MarketItem
    perf_uplift_pct: float = Field(
        default=0.0, description="Estimated perf uplift vs. the replaced component."
    )
    rationale: str = ""


class UpgradePlan(_Base):
    items: tuple[UpgradeItem, ...]
    total_usd: Decimal = Field(ge=Decimal("0"))
    overall_perf_uplift_pct: float = Field(
        default=0.0, description="Weighted-workload uplift across the whole rig."
    )
    bottlenecks_resolved: tuple[str, ...] = ()
    rationale: str = ""
    strategy: str = Field(default="greedy", description="Optimizer used: greedy|ilp|multi.")


class Quote(_Base):
    plan: UpgradePlan
    tax_usd: Decimal = Field(ge=Decimal("0"))
    shipping_usd: Decimal = Field(ge=Decimal("0"))
    grand_total_usd: Decimal = Field(ge=Decimal("0"))
    generated_at: datetime
    deals: tuple[Deal, ...] = ()
    affiliate_disclosure: str = (
        "Some links may earn a small commission at no extra cost to you."
    )


class Report(_Base):
    snapshot_id: str
    html_path: str | None = None
    pdf_path: str | None = None
    json_path: str


# ---------------------------------------------------------------------------
# Schema export
# ---------------------------------------------------------------------------


_EXPORTED_MODELS: tuple[type[_Base], ...] = (
    Component,
    Benchmark,
    SystemSnapshot,
    MarketItem,
    Deal,
    BudgetConstraint,
    UpgradeItem,
    UpgradePlan,
    Quote,
    Report,
)


def export_schemas(out_dir: Path) -> list[Path]:
    """Write one JSON schema per public model into ``out_dir``. Returns written files."""
    out_dir.mkdir(parents=True, exist_ok=True)
    written: list[Path] = []
    for model in _EXPORTED_MODELS:
        path = out_dir / f"{model.__name__}.schema.json"
        path.write_text(
            json.dumps(model.model_json_schema(), indent=2, sort_keys=True),
            encoding="utf-8",
        )
        written.append(path)
    return written
