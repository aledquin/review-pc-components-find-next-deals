"""Unit-test fixtures. Strict isolation: no network, no real app DB."""

from __future__ import annotations

import os

import pytest


@pytest.fixture(autouse=True)
def _no_network() -> None:
    """Ban real sockets in unit tests.

    Uses ``pytest-socket`` if available; otherwise skips this guard so the
    suite still runs in minimal environments. Never ``yield`` required here
    because ``pytest-socket`` restores state automatically per test.
    """
    try:
        import pytest_socket  # type: ignore[import-not-found]
    except ImportError:  # pragma: no cover
        return
    pytest_socket.disable_socket(allow_unix_socket=True)


@pytest.fixture(autouse=True)
def _isolated_pca_dirs(tmp_path, monkeypatch) -> None:
    """Force the app to use ``tmp_path`` for cache + reports so we never touch %APPDATA%."""
    monkeypatch.setenv("PCA_CACHE_DIR", str(tmp_path / "cache"))
    monkeypatch.setenv("PCA_REPORT_DIR", str(tmp_path / "reports"))
    os.makedirs(tmp_path / "cache", exist_ok=True)
    os.makedirs(tmp_path / "reports", exist_ok=True)

    from pca.core.config import reset_settings_cache

    reset_settings_cache()
