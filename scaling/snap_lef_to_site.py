#!/usr/bin/env python3
"""snap_lef_to_site.py — snap cell SIZEs in scaled LEF to integer site multiples.

The scaled tech LEF declares SITE unithd = 0.06147 × 0.363475 µm. After
scaling, cell sizes (e.g., NAND2 = 0.18441 µm) are *mathematically* exact
multiples of the site (NAND2 = 3 × 0.06147 = 0.18441). But at DATABASE
MICRONS = 1000, the LEF parser rounds to integer DBUs:

    site_w = 61.47 → 61 DBU (truncated)
    NAND2  = 184.41 → 184 DBU (truncated)
    3 × 61 = 183 DBU, but NAND2 reports 184 DBU — 1-DBU overhang into the
    next site, causing DPL-0033 detailed-placement overlap with tap cells.

This script fixes both halves of the bug:

  1. Snap each cell's SIZE x and y to integer-site multiples computed from
     a chosen *snapped* site dimension (so the values are exact in DBU at
     DBM = 10000, which is the highest standard value OpenROAD accepts).
  2. Pair with an updated tech LEF that uses DBM = 10000, site_w = 0.0615,
     site_h = 0.3635 (these snap exactly at DBM = 10000).

The tech LEF edit is left to the caller; this script only rewrites cell
SIZEs in the merged macro LEF.

Usage:
  scaling/snap_lef_to_site.py --in  <path-to-merged.lef> \\
                              --out <path-to-merged.lef.snapped>
"""

from __future__ import annotations

import argparse
import re
from pathlib import Path

# Original scaled values that came out of scale_lef.py (averages of sky130 / 7.485):
ORIG_SITE_W = 0.06147
ORIG_SITE_H = 0.363475

# Snapped to clean fractional positions at DATABASE MICRONS = 10000:
#   0.0615 × 10000 = 615 DBU (exact)
#   0.3635 × 10000 = 3635 DBU (exact)
SNAP_SITE_W = 0.0615
SNAP_SITE_H = 0.3635

SIZE_PATTERN = re.compile(r'(\s*SIZE\s+)([0-9.]+)(\s+BY\s+)([0-9.]+)(\s*;.*)')


def snap_value(v: float, orig_step: float, snap_step: float) -> float:
    """Snap micron value v to integer multiples of snap_step.

    The number of "site steps" is inferred from the original (pre-snap)
    geometry — i.e. how many sites this dimension is *intended* to span —
    then expressed in the snapped step size.
    """
    n_sites = round(v / orig_step)
    return n_sites * snap_step


def snap_lef(text: str) -> tuple[str, int]:
    out_lines = []
    n_changed = 0
    for line in text.splitlines(keepends=True):
        m = SIZE_PATTERN.match(line)
        if m:
            prefix, x_str, mid, y_str, suffix = m.groups()
            x_old = float(x_str)
            y_old = float(y_str)
            x_new = snap_value(x_old, ORIG_SITE_W, SNAP_SITE_W)
            y_new = snap_value(y_old, ORIG_SITE_H, SNAP_SITE_H)
            # Format with 5 decimal places, strip trailing zeros gracefully.
            line = f"{prefix}{x_new:.5f} BY {y_new:.5f}{suffix}"
            if not line.endswith("\n"):
                line += "\n"
            n_changed += 1
        out_lines.append(line)
    return "".join(out_lines), n_changed


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--in", dest="inp", required=True, type=Path)
    p.add_argument("--out", dest="out", required=True, type=Path)
    args = p.parse_args()
    text = args.inp.read_text()
    new_text, n = snap_lef(text)
    args.out.write_text(new_text)
    print(f"==> Snapped {n} SIZE statements")
    print(f"   site_w: {ORIG_SITE_W} -> {SNAP_SITE_W}")
    print(f"   site_h: {ORIG_SITE_H} -> {SNAP_SITE_H}")
    print(f"   At DBM=10000, site = {SNAP_SITE_W * 10000:.0f} x {SNAP_SITE_H * 10000:.0f} DBU (integer)")
    print(f"==> Wrote {args.out}")


if __name__ == "__main__":
    main()
