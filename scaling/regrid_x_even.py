#!/usr/bin/env python3
"""regrid_x_even.py — shrink the X (vertical-track) grid of the scaled cell
LEF from a 615-DBU site to a 614-DBU site, so the vertical pitch is an EVEN
number of manufacturing-grid units.

Why: opencell-7's vertical pitch / site width landed on 0.0615 µm = 615 DBU
(odd) after independent mfgrid snapping. The standard cells are SYMMETRY Y,
so the placer mirrors them in alternating rows. A mirror-symmetric track grid
requires 2*offset == 0 (mod pitch); with an ODD pitch that is impossible
(offset 307, 2*307=614 != 0 mod 615), so every FLIPPED cell has its pins one
DBU off the li1/met2 track -> DRT-0073 "No access point". Moving the site to
614 DBU (even, half = 307 exactly) makes the grid mirror-symmetric and the
access points land for flipped and unflipped instances alike.

This rewrites X coordinates only (Y is already clean: row = 8 x met1 pitch).
Every X token is scaled by 614/615 and snapped to the manufacturing grid, so
a cell that was N*0.0615 wide becomes exactly N*0.0614.

Usage: regrid_x_even.py --in merged.lef --out merged.lef.even
"""
from __future__ import annotations
import argparse, re
from pathlib import Path

OLD = 0.0615
NEW = 0.0614
FACTOR = NEW / OLD
MFG = 0.0001

def sx(v: float) -> float:
    return round((v * FACTOR) / MFG) * MFG

def fmt(v: float) -> str:
    return f"{v:.4f}"

def regrid(text: str) -> tuple[str, int]:
    out, n = [], 0
    for line in text.splitlines(keepends=True):
        body = line[:-1] if line.endswith("\n") else line
        end = "\n" if line.endswith("\n") else ""
        s = body.strip()
        kw = s.split()[0] if s.split() else ""
        new = None
        if kw == "SIZE":  # SIZE x BY y ;
            m = re.match(r'(\s*SIZE\s+)([\d.]+)(\s+BY\s+)([\d.]+)(\s*;.*)', body)
            if m:
                new = f"{m.group(1)}{fmt(sx(float(m.group(2))))}{m.group(3)}{m.group(4)}{m.group(5)}"
        elif kw in ("ORIGIN", "FOREIGN"):  # ...[name] x y ;  -> scale x (first coord pair's x)
            m = re.match(r'(.*?)(-?[\d.]+)(\s+)(-?[\d.]+)(\s*;.*)', body)
            if m:
                new = f"{m.group(1)}{fmt(sx(float(m.group(2))))}{m.group(3)}{m.group(4)}{m.group(5)}"
        elif kw == "RECT":  # RECT x1 y1 x2 y2 ;
            m = re.match(r'(\s*RECT\s+)(-?[\d.]+)(\s+)(-?[\d.]+)(\s+)(-?[\d.]+)(\s+)(-?[\d.]+)(\s*;.*)', body)
            if m:
                g = m.groups()
                new = (f"{g[0]}{fmt(sx(float(g[1])))}{g[2]}{g[3]}{g[4]}"
                       f"{fmt(sx(float(g[5])))}{g[6]}{g[7]}{g[8]}")
        elif kw == "POLYGON":  # POLYGON x1 y1 x2 y2 ... ;
            m = re.match(r'(\s*POLYGON\s+)(.*?)(\s*;.*)', body)
            if m:
                nums = m.group(2).split()
                scaled = [fmt(sx(float(t))) if i % 2 == 0 else t for i, t in enumerate(nums)]
                new = f"{m.group(1)}{' '.join(scaled)}{m.group(3)}"
        if new is not None and new != body:
            out.append(new + end); n += 1
        else:
            out.append(line)
    return "".join(out), n

def main():
    p = argparse.ArgumentParser()
    p.add_argument("--in", dest="inp", required=True, type=Path)
    p.add_argument("--out", dest="out", required=True, type=Path)
    a = p.parse_args()
    txt, n = regrid(a.inp.read_text())
    a.out.write_text(txt)
    print(f"==> regrid X {OLD}->{NEW} (factor {FACTOR:.6f}); rewrote {n} geometry lines")
    print(f"==> {a.out}")

if __name__ == "__main__":
    main()
