# PyInstaller spec for a single-file `pca` executable.
#
# Invocation (from the repo root):
#
#     pyinstaller packaging/pca.spec --clean --noconfirm
#
# Output: dist/pca  (Linux/macOS) or dist/pca.exe (Windows).
#
# Design notes:
# - Bundles the full `resources/` tree under the extracted bundle root so
#   `pca.core.resources.resource_root()` resolves via sys._MEIPASS.
# - Collects data files + submodules for libraries that use dynamic
#   imports (pulp, jinja2, pydantic) so the frozen exe starts cleanly.
# - Matplotlib and weasyprint are NOT included by default - they more than
#   triple the binary size and most users never emit a PDF. To include
#   them, pass `--add-data matplotlib` etc. at build time or edit the
#   `excludes` list below.

from __future__ import annotations

import sys
from pathlib import Path

from PyInstaller.utils.hooks import (
    collect_data_files,
    collect_submodules,
)

block_cipher = None

repo_root = Path.cwd().resolve()
entrypoint = repo_root / "src" / "pca" / "ui" / "cli" / "__main__.py"

# Bundle the whole resources/ tree.
resource_datas = [
    (str(repo_root / "resources"), "resources"),
]

# Dynamic imports that PyInstaller's static analysis tends to miss.
hidden_imports: list[str] = []
hidden_imports += collect_submodules("pulp")          # MILP solver plugins
hidden_imports += collect_submodules("pydantic")
if sys.platform == "win32":
    hidden_imports += collect_submodules("wmi")
    hidden_imports += [
        "win32com", "win32com.client", "pywintypes", "pythoncom",
        "pynvml",
    ]
hidden_imports += [
    "pca",
    "pca.ui.cli.__main__",
    "pca.inventory.windows",
    "pca.inventory.linux",
    "pca.inventory.macos",
    "pca.market.adapters.bestbuy",
    "pca.market.adapters.amazon",
    "pca.market.adapters.ebay",
    "pca.market.adapters.ebay_sold",
    "pca.market.adapters.newegg",
    "pca.budget.optimizer_greedy",
    "pca.budget.optimizer_ilp",
    "pca.budget.optimizer_multi",
]

# PuLP ships the CBC solver binary as package data; pull it in.
datas = list(resource_datas)
datas += collect_data_files("pulp", include_py_files=False)
datas += collect_data_files("jinja2", include_py_files=False)

# Libraries we deliberately exclude from the default bundle to keep it
# small. Users who need PDF install the `reporting` extra into a separate
# venv - or we ship a `pca-full` spec in a follow-up.
excludes = [
    "matplotlib",
    "weasyprint",
    "tkinter",
    "IPython",
    "notebook",
    "jupyter",
    "setuptools",
    "pip",
]

a = Analysis(
    [str(entrypoint)],
    pathex=[str(repo_root / "src")],
    binaries=[],
    datas=datas,
    hiddenimports=hidden_imports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=excludes,
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name="pca",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,                  # UPX trips some AV scanners on Windows.
    upx_exclude=[],
    runtime_tmpdir=None,
    console=True,               # CLI is console-based.
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)

# Sanity marker for the smoke test - the bundle contains a version string.
# (PyInstaller writes the exe name; we verify with `pca --help` in CI.)
