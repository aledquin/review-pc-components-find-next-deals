"""Vendor-string and model-string cleanup used by all probes.

These helpers are pure and safe to unit-test in isolation.
"""

from __future__ import annotations

import re

_VENDOR_ALIASES: dict[str, str] = {
    "authenticamd": "AMD",
    "genuineintel": "Intel",
    "advanced micro devices, inc.": "AMD",
    "advanced micro devices": "AMD",
    "intel(r) corporation": "Intel",
    "intel corporation": "Intel",
    "nvidia corporation": "NVIDIA",
    "micro-star international co., ltd.": "MSI",
    "micro-star international": "MSI",
    "asustek computer inc.": "ASUS",
    "asustek computer": "ASUS",
    "asustek": "ASUS",
    "samsung electronics": "Samsung",
    "corsair memory": "Corsair",
}

_TM_MARKS = re.compile(r"\((?:r|tm|c)\)", re.IGNORECASE)
_TRAILING_NOISE = re.compile(
    r"\b(processor|cpu)\b\s*$",
    re.IGNORECASE,
)
_CPU_SUFFIX = re.compile(r"\s+CPU\s+@\s+", re.IGNORECASE)
_WS = re.compile(r"\s+")


def normalize_vendor(raw: str) -> str:
    key = (raw or "").strip().lower()
    if not key:
        return ""
    if key in _VENDOR_ALIASES:
        return _VENDOR_ALIASES[key]
    # Accept well-known vendor tokens case-correctly as a last resort.
    for alias, canonical in _VENDOR_ALIASES.items():
        if alias in key:
            return canonical
    return raw.strip()


def normalize_model(raw: str) -> str:
    if not raw:
        return ""
    s = _TM_MARKS.sub("", raw)
    s = _CPU_SUFFIX.sub(" @ ", s)
    s = _TRAILING_NOISE.sub("", s)
    s = _WS.sub(" ", s).strip(" -")
    return s
