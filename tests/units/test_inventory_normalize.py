"""Unit tests for the vendor/model string normalizer."""

from __future__ import annotations

import pytest

from pca.inventory.normalize import normalize_model, normalize_vendor


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("AuthenticAMD", "AMD"),
        ("GenuineIntel", "Intel"),
        ("NVIDIA Corporation", "NVIDIA"),
        ("Advanced Micro Devices, Inc.", "AMD"),
        ("Intel(R) Corporation", "Intel"),
        ("ASUSTeK Computer Inc.", "ASUS"),
        ("Unknown", "Unknown"),
        ("", ""),
    ],
)
def test_normalize_vendor(raw: str, expected: str) -> None:
    assert normalize_vendor(raw) == expected


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("Intel(R) Core(TM) i5-8400 CPU @ 2.80GHz", "Intel Core i5-8400 @ 2.80GHz"),
        ("NVIDIA GeForce RTX 4080", "NVIDIA GeForce RTX 4080"),
        ("AMD Ryzen 7 7800X3D 8-Core Processor", "AMD Ryzen 7 7800X3D 8-Core"),
        ("Samsung SSD 990 Pro 2TB", "Samsung SSD 990 Pro 2TB"),
        ("   lots    of   whitespace   ", "lots of whitespace"),
        ("", ""),
    ],
)
def test_normalize_model(raw: str, expected: str) -> None:
    assert normalize_model(raw) == expected
