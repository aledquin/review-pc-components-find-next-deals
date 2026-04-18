"""Functional: ``StubProbe`` must return the exact snapshot it was given.

This guarantees the probe interface is a pure transport and the inventory
pipeline can be exercised end-to-end on any OS using golden rigs.
"""

from __future__ import annotations

import pytest

from pca.inventory.windows import StubProbe
from tests.fixtures import RIG_IDS, load_rig


@pytest.mark.parametrize("rig_id", RIG_IDS)
def test_stub_probe_returns_fixture(rig_id: str) -> None:
    fixture = load_rig(rig_id)
    probe = StubProbe(fixture)
    got = probe.collect()
    assert got == fixture
    assert got.os_info.family == "Windows"
    assert len(got.components) >= 6
