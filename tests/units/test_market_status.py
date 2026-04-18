"""Unit tests for :mod:`pca.market.status` - the adapter status/doctor logic.

All offline (``pytest-socket``). The status module never makes a network
request; it only inspects settings and introspects the registry.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from pca.core.config import Settings


def _settings(**kwargs: Any) -> Settings:
    defaults: dict[str, Any] = {
        "bestbuy_api_key": None,
        "ebay_client_id": None,
        "ebay_client_secret": None,
        "amazon_access_key": None,
        "amazon_secret_key": None,
        "amazon_assoc_tag": None,
        "newegg_feed_path": None,
        "enable_adapters": "",
        "allow_plugins": False,
    }
    defaults.update(kwargs)
    return Settings.model_construct(**defaults)


def test_status_all_missing_reports_every_adapter_inactive() -> None:
    from pca.market.status import AdapterStatus, describe_adapter_status

    report = describe_adapter_status(_settings())
    assert len(report) >= 5  # bestbuy, ebay, ebay-sold, amazon-paapi, newegg
    names = {e.name for e in report}
    assert {"bestbuy", "ebay", "ebay-sold", "amazon-paapi", "newegg"} <= names

    for entry in report:
        assert isinstance(entry, AdapterStatus)
        assert entry.active is False
        # Each inactive entry must point at the env var(s) needed.
        assert "PCA_" in entry.reason


def test_status_bestbuy_active_with_key() -> None:
    from pca.market.status import describe_adapter_status

    report = describe_adapter_status(_settings(bestbuy_api_key="bb"))
    bb = next(e for e in report if e.name == "bestbuy")
    assert bb.active is True
    assert "PCA_BESTBUY_API_KEY" in bb.reason or "configured" in bb.reason.lower()


def test_status_ebay_partial_creds_are_inactive() -> None:
    from pca.market.status import describe_adapter_status

    report = describe_adapter_status(_settings(ebay_client_id="id"))
    eb = next(e for e in report if e.name == "ebay")
    assert eb.active is False
    assert "CLIENT_SECRET" in eb.reason


def test_status_respects_explicit_allow_list() -> None:
    from pca.market.status import describe_adapter_status

    report = describe_adapter_status(
        _settings(
            bestbuy_api_key="bb",
            ebay_client_id="id",
            ebay_client_secret="sec",
            enable_adapters="bestbuy",
        )
    )
    bb = next(e for e in report if e.name == "bestbuy")
    eb = next(e for e in report if e.name == "ebay")
    assert bb.active is True
    # eBay has creds but is excluded by the allow-list.
    assert eb.active is False
    assert "allow-list" in eb.reason.lower() or "enable_adapters" in eb.reason.lower()


def test_status_newegg_requires_existing_file(tmp_path: Path) -> None:
    from pca.market.status import describe_adapter_status

    missing = tmp_path / "does_not_exist.tsv"
    rpt_missing = describe_adapter_status(_settings(newegg_feed_path=missing))
    ne_missing = next(e for e in rpt_missing if e.name == "newegg")
    assert ne_missing.active is False

    existing = tmp_path / "feed.tsv"
    existing.write_text("", encoding="utf-8")
    rpt_ok = describe_adapter_status(_settings(newegg_feed_path=existing))
    ne_ok = next(e for e in rpt_ok if e.name == "newegg")
    assert ne_ok.active is True


def test_status_format_table_has_every_adapter(capsys: pytest.CaptureFixture[str]) -> None:
    """format_status_table must render an entry per adapter with a clear state."""
    from pca.market.status import (
        describe_adapter_status,
        format_status_table,
    )

    report = describe_adapter_status(_settings(bestbuy_api_key="bb"))
    text = format_status_table(report)
    # Table text should mention each adapter name once.
    for name in ("bestbuy", "ebay", "ebay-sold", "amazon-paapi", "newegg"):
        assert name in text
    # Active/inactive markers must be visible.
    assert "active" in text.lower()
