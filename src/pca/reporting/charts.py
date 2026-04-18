"""Chart rendering for reports.

Returns matplotlib-generated PNGs as either a file path or a base64 data URL
that can be embedded directly inside the HTML template so reports stay
self-contained. ``matplotlib`` is an optional (``reporting``-extra) dependency;
when missing, we emit a tiny deterministic placeholder PNG so golden tests
still pass on minimal installs.
"""

from __future__ import annotations

import base64
import io
from collections.abc import Iterable, Mapping
from pathlib import Path

from pca.core.models import (
    ComponentKind,
    SystemSnapshot,
    UpgradePlan,
    Workload,
)
from pca.gap_analysis.normalize import current_score, market_item_score, workload_weights


# 1x1 transparent PNG used when matplotlib is unavailable. Deterministic bytes.
_PLACEHOLDER_PNG: bytes = base64.b64decode(
    b"iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNkYAAAAAYAAjCB0C8AAAAASUVORK5CYII="
)


def _matplotlib_available() -> bool:
    try:
        import matplotlib  # noqa: F401  (import-time check)

        return True
    except ImportError:
        return False


def _render_bar_png(labels: list[str], values: list[float], title: str) -> bytes:
    """Render a horizontal bar chart to PNG bytes, with a graceful fallback."""
    if not _matplotlib_available():  # pragma: no cover - exercised when extra missing
        return _PLACEHOLDER_PNG

    import matplotlib

    matplotlib.use("Agg")  # headless backend; safe in tests and CI
    import matplotlib.pyplot as plt

    fig, ax = plt.subplots(figsize=(5.5, max(2.0, 0.45 * max(1, len(labels)))))
    ax.barh(labels, values)
    ax.set_title(title)
    ax.set_xlabel("perf score")
    ax.invert_yaxis()
    fig.tight_layout()
    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=120)
    plt.close(fig)
    return buf.getvalue()


def _data_url(png: bytes) -> str:
    return "data:image/png;base64," + base64.b64encode(png).decode("ascii")


def snapshot_scores_png(snapshot: SystemSnapshot) -> bytes:
    """Chart current component scores - useful in the report header."""
    kinds: Iterable[ComponentKind] = (
        ComponentKind.CPU,
        ComponentKind.GPU,
        ComponentKind.RAM,
        ComponentKind.STORAGE,
    )
    labels: list[str] = []
    values: list[float] = []
    for k in kinds:
        comps = snapshot.components_of(k)
        if not comps:
            continue
        labels.append(f"{k.value}: {comps[0].model}")
        values.append(round(current_score(snapshot, k), 1))
    return _render_bar_png(labels, values, f"Current rig - {snapshot.id}")


def plan_uplift_png(
    plan: UpgradePlan,
    snapshot: SystemSnapshot,
    workload: Workload = Workload.GAMING_1440P,
) -> bytes:
    """Chart the per-kind perf uplift implied by the plan."""
    weights: Mapping[ComponentKind, float] = workload_weights(workload)
    labels: list[str] = []
    values: list[float] = []
    for item in plan.items:
        if item.kind not in weights:
            continue
        labels.append(f"{item.kind.value}: +{item.perf_uplift_pct:.0f}%")
        before = current_score(snapshot, item.kind)
        after = market_item_score(item.market_item)
        values.append(round(max(after - before, 0.0), 1))
    return _render_bar_png(
        labels, values, f"Plan uplift ({plan.strategy}, workload: {workload.value})"
    )


def write_chart(png: bytes, path: Path) -> Path:
    """Write ``png`` bytes to ``path`` (creating parents) and return the path."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(png)
    return path


def png_as_data_url(png: bytes) -> str:
    """Expose the data-URL helper so the Jinja env can inline charts."""
    return _data_url(png)
