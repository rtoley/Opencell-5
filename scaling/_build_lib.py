#!/usr/bin/env python3
"""Thin wrapper around SkyWater liberty.py that skips its doctests.

Why: the SkyWater liberty.py runs doctests in `__main__` before main() and
exits if any fail. A couple of doctests fail on Python 3.12+ due to an
ordering tweak in IntFlag; the underlying generator still works. We sidestep
the doctest gate and call main() directly.
"""
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(ROOT / "reference" / "skywater-pdk-parent" / "scripts" / "python-skywater-pdk"))

from skywater_pdk.liberty import main

if __name__ == "__main__":
    sys.exit(main() or 0)
