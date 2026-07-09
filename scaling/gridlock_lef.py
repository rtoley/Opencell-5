#!/usr/bin/env python3
"""Grid-locked LEF re-scaler: opencell5 -> opencell5.

The naive scale_lef.py divides every dim by linear and rounds to mfgrid
INDEPENDENTLY, so the scaled SITE (0.046023) is off the 0.0005 DB grid; OpenROAD
quantizes SITE and cell widths separately and they stop aligning -> DPL-0033
overlaps on cell-diverse designs. Fix: pin SITE to a clean DB-grid value and
force every cell to an integer number of that SITE.

opencell5 SITE = 0.0615 x 0.3632 (cells are integer x-sites).
opencell5 SITE = 0.0460 x 0.2720 (both multiples of 0.0005; ~/1.336 -> area /100).
"""
import re, sys
SW_OLD, SH_OLD = 0.0615, 0.3632
SW_NEW, SH_NEW = 0.0460, 0.2720
DB = 0.0005
RX, RY = SW_NEW/SW_OLD, SH_NEW/SH_OLD   # x,y linear ratios (~0.748)

def snap(v, g=DB):
    return round(round(v/g)*g, 4)
def sites(w):
    return round(w/SW_OLD)   # integer site count from the clean oc5 width

src, dst = sys.argv[1], sys.argv[2]
is_tlef = "--tlef" in sys.argv
lines = open(src).read().splitlines()
out = []
for ln in lines:
    s = ln.strip()
    # SITE definition (tlef): pin to the clean new site
    m = re.match(r'^(\s*)SIZE\s+([\d.]+)\s+BY\s+([\d.]+)\s*;', ln)
    if m and is_tlef and 0.05 < float(m.group(2)) < 0.07:
        out.append(f"{m.group(1)}SIZE {SW_NEW:.4f} BY {SH_NEW:.4f} ;"); continue
    if m and not is_tlef:
        # MACRO cell SIZE: integer sites x new-site-width, one-row height
        w, h = float(m.group(2)), float(m.group(3))
        nrows = max(1, round(h/SH_OLD))
        out.append(f"{m.group(1)}SIZE {sites(w)*SW_NEW:.4f} BY {snap(nrows*SH_NEW):.4f} ;"); continue
    m = re.match(r'^(\s*)RECT\s+([\d.-]+)\s+([\d.-]+)\s+([\d.-]+)\s+([\d.-]+)\s*;', ln)
    if m:
        g = m.groups()
        out.append(f"{g[0]}RECT {snap(float(g[1])*RX)} {snap(float(g[2])*RY)} "
                   f"{snap(float(g[3])*RX)} {snap(float(g[4])*RY)} ;"); continue
    m = re.match(r'^(\s*)(ORIGIN|FOREIGN\s+\S+)\s+([\d.-]+)\s+([\d.-]+)\s*;', ln)
    if m:
        out.append(f"{m.group(1)}{m.group(2)} {snap(float(m.group(3))*RX)} {snap(float(m.group(4))*RY)} ;"); continue
    # generic tlef routing dims: scale by RX, snap (pitches/widths); leave ints/keywords
    if is_tlef:
        m = re.match(r'^(\s*)(PITCH|WIDTH|SPACING|OFFSET|THICKNESS|HEIGHT)\s+([\d.]+)(\s+([\d.]+))?\s*;', ln)
        if m:
            a = snap(float(m.group(3))*RX)
            b = f" {snap(float(m.group(5))*RY)}" if m.group(5) else ""
            out.append(f"{m.group(1)}{m.group(2)} {a}{b} ;"); continue
    out.append(ln)
open(dst, "w").write("\n".join(out) + "\n")
print(f"grid-locked {'tlef' if is_tlef else 'lef'}: SITE {SW_NEW}x{SH_NEW}, DB {DB} -> {dst.split('/')[-1]}")
