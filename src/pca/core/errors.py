"""Typed exception hierarchy for PC Upgrade Advisor."""

from __future__ import annotations


class PcaError(Exception):
    """Root of the PCA exception hierarchy."""


class InventoryError(PcaError):
    """Raised when hardware inventory detection fails."""


class BenchmarkError(PcaError):
    """Raised when a benchmark run cannot be completed."""


class MarketError(PcaError):
    """Raised for retailer adapter failures (HTTP, auth, quota)."""


class RateLimitedError(MarketError):
    """Raised when a retailer adapter hits its rate limit or quota."""


class AdapterUnavailableError(MarketError):
    """Raised when a retailer adapter is disabled or not configured."""


class BudgetInfeasibleError(PcaError):
    """Raised when no upgrade plan fits within the given constraints."""


class IncompatibleUpgradeError(PcaError):
    """Raised when candidate components fail the compatibility graph."""


class ConfigError(PcaError):
    """Raised when configuration is missing or invalid."""
