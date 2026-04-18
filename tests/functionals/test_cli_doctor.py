"""Functional tests for ``pca doctor``."""

from __future__ import annotations

import pytest
from typer.testing import CliRunner

from pca.ui.cli.app import app


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch: pytest.MonkeyPatch) -> None:
    for var in (
        "PCA_BESTBUY_API_KEY",
        "PCA_EBAY_CLIENT_ID",
        "PCA_EBAY_CLIENT_SECRET",
        "PCA_AMAZON_ACCESS_KEY",
        "PCA_AMAZON_SECRET_KEY",
        "PCA_AMAZON_ASSOC_TAG",
        "PCA_NEWEGG_FEED_PATH",
        "PCA_ENABLE_ADAPTERS",
        "PCA_ALLOW_PLUGINS",
    ):
        monkeypatch.delenv(var, raising=False)
    from pca.core.config import reset_settings_cache

    reset_settings_cache()


def test_doctor_no_creds_lists_every_adapter_as_inactive() -> None:
    runner = CliRunner()
    result = runner.invoke(app, ["doctor"])
    assert result.exit_code == 0, result.stdout
    out = result.stdout
    for name in ("bestbuy", "ebay", "ebay-sold", "amazon-paapi", "newegg"):
        assert name in out
    assert "inactive" in out
    # The table is discoverable without flags.
    assert "Adapter" in out
    assert "Summary:" in out


def test_doctor_reports_active_when_creds_set(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from pca.core.config import reset_settings_cache

    monkeypatch.setenv("PCA_BESTBUY_API_KEY", "bb")
    reset_settings_cache()

    runner = CliRunner()
    result = runner.invoke(app, ["doctor"])
    assert result.exit_code == 0
    assert "bestbuy" in result.stdout
    assert "active" in result.stdout
