# -*- mode: python ; coding: utf-8 -*-
"""
PyInstaller spec for AutoJobApplier desktop build.

Produces a single windowed executable that bundles:
  - FastAPI + Uvicorn backend
  - SQLite (via aiosqlite, stdlib-backed)
  - Alembic migration scripts (data_files)
  - The Next.js static export under ``frontend_dist/``
  - System-tray launcher entry point

Invoke from the ``backend/`` directory with:

    pyinstaller autojobapplier.spec --noconfirm --clean
"""
from __future__ import annotations

import os
from pathlib import Path

from PyInstaller.utils.hooks import collect_data_files, collect_submodules

BACKEND_DIR = Path(os.getcwd()).resolve()
ROOT_DIR = BACKEND_DIR.parent
FRONTEND_DIST = ROOT_DIR / "frontend" / "out"

datas: list[tuple[str, str]] = []

# Alembic migration files & config — needed at runtime for `alembic upgrade head`.
datas.append((str(BACKEND_DIR / "alembic"), "alembic"))
if (BACKEND_DIR / "alembic.ini").exists():
    datas.append((str(BACKEND_DIR / "alembic.ini"), "."))

# Frontend static export (only present after `npm run build` ran).
if FRONTEND_DIST.is_dir():
    datas.append((str(FRONTEND_DIST), "frontend_dist"))

# sklearn / scipy and FastAPI's optional extras ship tons of data + plugin
# modules that PyInstaller's static analysis misses.
for pkg in (
    "sklearn",
    "scipy",
    "uvicorn",
    "fastapi",
    "pydantic",
    "passlib",
    "structlog",
    "email_validator",
    "playwright",
    "cryptography",
):
    try:
        datas += collect_data_files(pkg)
    except Exception:
        pass

hiddenimports: list[str] = []
for pkg in (
    "uvicorn.logging",
    "uvicorn.loops",
    "uvicorn.loops.auto",
    "uvicorn.protocols",
    "uvicorn.protocols.http",
    "uvicorn.protocols.http.auto",
    "uvicorn.protocols.websockets",
    "uvicorn.protocols.websockets.auto",
    "uvicorn.lifespan",
    "uvicorn.lifespan.on",
    "aiosqlite",
    "sqlalchemy.dialects.sqlite",
    "sqlalchemy.dialects.sqlite.aiosqlite",
    "email_validator",
    "passlib.handlers.bcrypt",
    "bcrypt",
    "pystray._win32",
    "pystray._darwin",
    "pystray._gtk",
    "pystray._xorg",
    "PIL._tkinter_finder",
):
    hiddenimports.append(pkg)

hiddenimports += collect_submodules("sklearn")
hiddenimports += collect_submodules("scipy")
hiddenimports += collect_submodules("app")


block_cipher = None

a = Analysis(
    ["launcher.py"],
    pathex=[str(BACKEND_DIR)],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    runtime_hooks=[],
    excludes=[
        "tkinter",
        "matplotlib",
        "IPython",
        "jupyter",
        "notebook",
        "pytest",
        "celery",
        "redis",
        "kombu",
        "asyncpg",
        "psycopg2",
        "psycopg2-binary",
    ],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="AutoJobApplier",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name="AutoJobApplier",
)
