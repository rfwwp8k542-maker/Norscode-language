#!/usr/bin/env python3
"""Build a standalone Norscode binary from the projects/language workspace."""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path


WORKSPACE_DIR = Path(__file__).resolve().parent.parent
BUILD_DIR = WORKSPACE_DIR / "build"
DIST_DIR = WORKSPACE_DIR / "dist"
PYINSTALLER_CONFIG_DIR = Path(
    os.environ.get("PYINSTALLER_CONFIG_DIR", str(BUILD_DIR / "pyinstaller" / "config"))
)


def _remove_path(path: Path) -> None:
    if path.is_dir():
        shutil.rmtree(path)
    elif path.exists():
        path.unlink()


def _output_path() -> Path:
    return DIST_DIR / ("norscode.exe" if os.name == "nt" else "norscode")


def main() -> int:
    os.environ["PYINSTALLER_CONFIG_DIR"] = str(PYINSTALLER_CONFIG_DIR)

    try:
        subprocess.run(
            [sys.executable, "-m", "PyInstaller", "--version"],
            cwd=WORKSPACE_DIR,
            check=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
    except subprocess.CalledProcessError:
        print(
            "PyInstaller mangler i miljøet. Kjør: python3 -m pip install pyinstaller",
            file=sys.stderr,
        )
        return 1

    _remove_path(BUILD_DIR)
    _remove_path(DIST_DIR / "norscode")
    _remove_path(DIST_DIR / "norscode.exe")

    subprocess.run(
        [
            sys.executable,
            "-m",
            "PyInstaller",
            "--onefile",
            "--paths",
            str(WORKSPACE_DIR),
            "--name",
            "norscode",
            "--clean",
            "--distpath",
            "dist",
            "--workpath",
            "build/pyinstaller",
            "--specpath",
            "build/pyinstaller",
            "main.py",
        ],
        cwd=WORKSPACE_DIR,
        check=True,
    )

    output_path = _output_path()
    if output_path.exists():
        print(f"Bygget binær: {output_path.relative_to(WORKSPACE_DIR)}")
        return 0

    print(f"Bygg ferdig, men fant ikke {output_path.relative_to(WORKSPACE_DIR)}", file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
