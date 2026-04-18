"""Wave 3 local web dashboard.

FastAPI + HTMX + Alpine.js. Binds to 127.0.0.1 by default; LAN exposure is
opt-in via ``pca serve --bind 0.0.0.0 --token <shared-secret>``.
"""

from __future__ import annotations

__all__ = ["create_app"]


def create_app(*args, **kwargs):  # type: ignore[no-untyped-def]
    """Lazy re-export that keeps FastAPI optional at import time."""
    from pca.ui.web.app import create_app as _impl

    return _impl(*args, **kwargs)
