"""Shared UI helpers used by both the FastAPI dashboard and the PyQt GUI.

These helpers render small HTML snippets (spec lists, spec diffs, safe
anchor tags) that both the web templates and the Qt ``QLabel`` rich-text
renderer can display. Keeping them here guarantees the two UIs stay in
visual lockstep as we iterate.
"""

from __future__ import annotations

import html as _html
from typing import Any

__all__ = [
    "safe_external_url",
    "spec_label",
    "fmt_spec_value",
    "render_specs_list_html",
    "render_spec_diff_html",
]


def safe_external_url(url: str | None) -> str | None:
    """Return ``url`` unchanged if it is an ``http(s)`` URL, else ``None``.

    Defence in depth against ``javascript:`` / ``data:`` URLs that could
    be smuggled into ``MarketItem.url`` by a malformed adapter response.
    """

    if not url:
        return None
    lowered = url.strip().lower()
    if lowered.startswith(("http://", "https://")):
        return url.strip()
    return None


def spec_label(key: str) -> str:
    """Humanize a spec key. ``'base_clock_ghz'`` -> ``'Base clock ghz'``."""

    words = key.replace("-", "_").split("_")
    return " ".join(w.capitalize() if i == 0 else w for i, w in enumerate(words))


def fmt_spec_value(value: Any) -> str:
    """Render a spec value as a short human string."""

    if isinstance(value, bool):
        return "yes" if value else "no"
    if isinstance(value, float):
        if float(value).is_integer():
            return str(int(value))
        return f"{value:g}"
    return str(value)


def render_specs_list_html(
    specs: dict[str, Any],
    *,
    key_color: str = "#8a8f9a",
    mono_family: str = "Consolas, 'Cascadia Code', monospace",
) -> str:
    """Render ``specs`` as a vertical list of ``• key: value`` rows.

    Uses inline styles so the result drops into both Qt's ``QLabel`` (rich
    text) and plain browser contexts with no external CSS.
    """

    if not specs:
        return f"<span style='color:{key_color};'>no specs on record</span>"
    parts: list[str] = []
    for k, v in specs.items():
        parts.append(
            f"<div style='margin:0; padding:1px 0;'>"
            f"<span style='color:{key_color};'>&bull; "
            f"{_html.escape(spec_label(k))}:</span> "
            f"<span style='font-family:{mono_family};'>"
            f"{_html.escape(fmt_spec_value(v))}</span>"
            f"</div>"
        )
    return "".join(parts)


def render_spec_diff_html(
    current: dict[str, Any],
    new: dict[str, Any],
    *,
    key_color: str = "#8a8f9a",
    change_color: str = "#3a8a5a",
    mono_family: str = "Consolas, 'Cascadia Code', monospace",
) -> str:
    """Render a current-vs-new spec diff.

    Each row describes one of three states:

    - ``change`` - key exists in both, value differs
      (``old`` strikethrough + ``→`` + ``new`` in ``change_color``)
    - ``new``    - key only in ``new`` (``new`` with green badge)
    - ``same``   - key with same value in both (dimmed, ``unchanged`` tag)
    """

    if not new:
        return ""
    rows: list[str] = []
    for key, nv in new.items():
        new_val = fmt_spec_value(nv)
        label = _html.escape(spec_label(key))
        if key in current:
            cv = fmt_spec_value(current[key])
            if cv == new_val:
                rows.append(
                    f"<div style='margin:0; padding:1px 0; opacity:.6;'>"
                    f"<span style='color:{key_color};'>&bull; {label}:</span> "
                    f"<span style='font-family:{mono_family};'>"
                    f"{_html.escape(new_val)}</span> "
                    f"<span style='color:{key_color}; font-size:10px;'>"
                    f"(unchanged)</span>"
                    f"</div>"
                )
            else:
                rows.append(
                    f"<div style='margin:0; padding:1px 0;'>"
                    f"<span style='color:{key_color};'>&bull; {label}:</span> "
                    f"<span style='color:{key_color}; text-decoration:line-through;'>"
                    f"{_html.escape(cv)}</span> "
                    f"<span style='color:{key_color};'>&rarr;</span> "
                    f"<span style='color:{change_color}; font-weight:600; "
                    f"font-family:{mono_family};'>"
                    f"{_html.escape(new_val)}</span>"
                    f"</div>"
                )
        else:
            rows.append(
                f"<div style='margin:0; padding:1px 0;'>"
                f"<span style='color:{key_color};'>&bull; {label}:</span> "
                f"<span style='color:{change_color}; font-weight:600; "
                f"font-family:{mono_family};'>"
                f"{_html.escape(new_val)}</span> "
                f"<span style='color:{change_color}; font-size:10px;'>"
                f"(new)</span>"
                f"</div>"
            )
    return "".join(rows)
