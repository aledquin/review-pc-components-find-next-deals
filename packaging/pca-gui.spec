# PyInstaller spec for the native PyQt6 GUI (`pca-gui.exe`).
#
# Invocation (from the repo root):
#
#     pyinstaller packaging/pca-gui.spec --clean --noconfirm
#
# Output: dist/pca-gui.exe (Windows) - a windowed (no console) binary.
#
# The companion `packaging/pca.spec` builds the headless CLI exe. Both
# specs share the same `resources/` bundle and hidden-import set; the GUI
# version additionally pulls in PyQt6.

from __future__ import annotations

import sys
from pathlib import Path

from PyInstaller.utils.hooks import collect_data_files, collect_submodules

block_cipher = None

repo_root = Path.cwd().resolve()
entrypoint = repo_root / "src" / "pca" / "ui" / "gui" / "__main__.py"

datas = [(str(repo_root / "resources"), "resources")]
datas += collect_data_files("pulp", include_py_files=False)
datas += collect_data_files("jinja2", include_py_files=False)

hidden_imports: list[str] = []
hidden_imports += collect_submodules("pulp")
hidden_imports += collect_submodules("pydantic")
hidden_imports += [
    "pca",
    "pca.ui.gui",
    "pca.ui.gui.app",
    "pca.ui.gui.main_window",
    "pca.ui.gui.controller",
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
    name="pca-gui",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,              # windowed app - no console window.
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=str(repo_root / "desktop" / "src-tauri" / "icons" / "icon.ico")
         if (repo_root / "desktop" / "src-tauri" / "icons" / "icon.ico").is_file()
         else None,
)
