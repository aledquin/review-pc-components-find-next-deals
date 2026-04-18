"""Locate the shipped ``resources/`` tree across dev/wheel/frozen modes.

PyInstaller copies bundled data files into ``sys._MEIPASS`` at runtime
(one-file builds) or alongside the executable (one-folder builds). Dev
installs use the repo layout. Wheel installs (future work) will fall back
to package data under ``pca/_resources``. All three are normalized here
so the rest of the code does not need to care.
"""

from __future__ import annotations

import sys
from functools import lru_cache
from pathlib import Path


@lru_cache(maxsize=1)
def resource_root() -> Path:
    """Return the directory that contains ``templates/``, ``catalogs/`` etc."""
    # 1. PyInstaller bundle. Works for both one-file (_MEIPASS is a temp dir)
    #    and one-folder (_MEIPASS is the extracted folder next to the exe).
    if getattr(sys, "frozen", False):
        meipass = getattr(sys, "_MEIPASS", None)
        base = Path(meipass) if meipass else Path(sys.executable).resolve().parent
        candidate = base / "resources"
        if candidate.is_dir():
            return candidate

    # 2. Editable / repo layout: walk up from this file looking for a
    #    ``resources/`` sibling of ``pyproject.toml``.
    here = Path(__file__).resolve()
    for parent in here.parents:
        if (parent / "resources").is_dir() and (parent / "pyproject.toml").is_file():
            return parent / "resources"

    # 3. Wheel install: resources bundled as package data.
    pkg_data = Path(__file__).resolve().parent.parent / "_resources"
    if pkg_data.is_dir():
        return pkg_data

    # 4. Last resort - legacy relative walk, kept for parity with the
    #    pre-helper call sites.
    return Path(__file__).resolve().parents[2] / "resources"


def resource_path(*parts: str) -> Path:
    """Return a path under the resource root. Does not check existence."""
    return resource_root().joinpath(*parts)
