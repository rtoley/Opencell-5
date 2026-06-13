#!/usr/bin/env python3
"""pin_snap_li1.py — guarantee every li1 signal pin covers a legal on-track
via landing, fixing DRT-0073 "No access point".

Root cause (measured): after independent scale+snap, li1 input-pin RECTs no
longer line up with the li1 vertical track grid. The mcon (li1->met1) via,
centered on the nearest track, pokes a few DBU past the pin edge, so its li1
enclosure is illegal and the router finds no access point. Example:
  pin A1 li1 RECT x=[0.0200,0.0547]; nearest track 0.0307; via needs li1
  coverage [0.0193,0.0421]; pin starts at 0.0200 -> 7 DBU short on the left.

Fix: for each li1 PORT RECT inside a PIN, find the nearest li1 track to the
RECT's x-center and EXTEND (never shift) the RECT in x so it fully covers the
via landing [T-half, T+half]. Extension only grows existing metal toward a
track that already overlaps the pin, so internal connectivity is preserved.
OBS (obstruction) geometry is left untouched.

Track grid (vertical / x), from the even-grid tech LEF:
  pitch 0.0614, offset 0.0307.  mcon li1 half-landing = 0.0114.
"""
from __future__ import annotations
import argparse, math, re
from pathlib import Path

PITCH  = 0.0614
OFFSET = 0.0307
VIA_HALF = 0.0114      # mcon li1 landing half-width (L1M1_PR)
MFG = 0.0001

def nearest_track(xc: float) -> float:
    n = round((xc - OFFSET) / PITCH)
    return OFFSET + n * PITCH

def fdown(v): return round(math.floor(v / MFG) * MFG, 4)
def fup(v):   return round(math.ceil(v / MFG) * MFG, 4)

RECT_RE = re.compile(r'(\s*RECT\s+)(-?[\d.]+)(\s+)(-?[\d.]+)(\s+)(-?[\d.]+)(\s+)(-?[\d.]+)(\s*;.*)')

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--in", dest="inp", required=True, type=Path)
    ap.add_argument("--out", dest="out", required=True, type=Path)
    a = ap.parse_args()

    in_pin = False        # inside a PIN ... END <pin>
    in_obs = False        # inside OBS ... END
    layer = None
    changed = 0
    out = []
    for line in a.inp.read_text().splitlines(keepends=True):
        s = line.strip()
        tok = s.split()
        if tok[:1] == ["PIN"]:
            in_pin = True; layer = None
        elif tok[:1] == ["OBS"]:
            in_obs = True; layer = None
        elif tok and tok[0] == "END" and in_obs and len(tok) == 1:
            in_obs = False; layer = None
        elif tok[:1] == ["END"] and in_pin and len(tok) == 2:
            in_pin = False; layer = None
        elif tok[:1] == ["LAYER"] and len(tok) >= 2:
            layer = tok[1]

        if in_pin and not in_obs and layer == "li1":
            m = RECT_RE.match(line.rstrip("\n"))
            if m:
                g = list(m.groups())
                x1, y1, x2, y2 = float(g[1]), float(g[3]), float(g[5]), float(g[7])
                xc = (x1 + x2) / 2.0
                T = nearest_track(xc)
                need_lo, need_hi = T - VIA_HALF, T + VIA_HALF
                nx1, nx2 = min(x1, fdown(need_lo)), max(x2, fup(need_hi))
                if abs(nx1 - x1) > 1e-9 or abs(nx2 - x2) > 1e-9:
                    nl = f"{g[0]}{nx1:.4f}{g[2]}{y1:.4f}{g[4]}{nx2:.4f}{g[6]}{y2:.4f}{g[8]}"
                    out.append(nl + ("\n" if line.endswith("\n") else "")); changed += 1
                    continue
        out.append(line)
    a.out.write_text("".join(out))
    print(f"==> extended {changed} li1 pin RECTs to cover on-track via landing")
    print(f"==> {a.out}")

if __name__ == "__main__":
    main()
