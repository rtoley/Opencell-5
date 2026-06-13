#!/usr/bin/env python3
"""snap_lef_to_mfgrid.py — snap every linear-dim value in a LEF to the
manufacturing grid (0.0001 µm = 1 DBU at DATABASE MICRONS = 10000).

This is the routing-layer companion to snap_lef_to_site.py. Whereas
snap_lef_to_site.py only handles cell-boundary `SIZE` values (snapping
them to integer site multiples to fix DPL-0033), this tool walks every
line of the LEF and snaps numeric tokens of routing/pin/via dimensions
to 4 decimal places so they all land on integer DBUs at DBM=10000.

Without this, lines like:

    PITCH 0.06147 0.045434 ;          # = 614.7 and 454.34 DBU
    RECT  0.388197 0.132962 ... ;     # = 3881.97 1329.62 DBU
    WIDTH 0.022717 ;                  # = 227.17 DBU

get silently truncated by the LEF parser, the routing-grid alignment is
off by fractions of a DBU per layer, and downstream routing fails with
DRT-0073 (No access point) because pin shapes don't intersect tracks
cleanly.

After snapping, every dimension is an integer DBU and the routing-grid
arithmetic stays exact end-to-end.

Snap rule: nearest 0.0001 µm. Values like 0.06147 -> 0.0615.
Tokens snapped: every floating-point number following one of these
keywords: PITCH OFFSET WIDTH SPACING THICKNESS SIZE ORIGIN RECT POLYGON
EDGECAPACITANCE (preserves topology of these statements; doesn't touch
RESISTANCE, CAPACITANCE, AREA, or numeric counts).

Usage:
  scaling/snap_lef_to_mfgrid.py --in <lef> --out <lef.snapped>
"""

from __future__ import annotations

import argparse
import re
from pathlib import Path

# Grid resolution: 0.0001 µm = 1 DBU at DATABASE MICRONS = 10000.
MFGRID = 0.0001

# Match lines that begin with a linear-dimension keyword (after optional
# whitespace) and capture the keyword + the rest of the line.
LINEAR_KEYWORDS = {
    "PITCH",
    "OFFSET",
    "WIDTH",
    "SPACING",
    "THICKNESS",
    "SIZE",
    "ORIGIN",
    "RECT",
    "POLYGON",
}

KEYWORD_RE = re.compile(
    r'^(\s*)(' + '|'.join(LINEAR_KEYWORDS) + r')\b(.*)$'
)

# Match floats in a string (handles scientific notation too).
FLOAT_RE = re.compile(r'-?\d+\.\d+(?:[eE][+-]?\d+)?|-?\d+(?:[eE][+-]?\d+)')


def snap_float(s: str) -> str:
    """Round a numeric token to MFGRID precision, preserving sign.

    Integer-only tokens (like counts in SPACINGTABLE PARALLELRUNLENGTH)
    are left alone — they don't have a decimal point so the regex
    skips them anyway (the FLOAT_RE requires a `.`)."""
    v = float(s)
    snapped = round(v / MFGRID) * MFGRID
    # Format with 4 decimals; trim trailing zeros only if the result is
    # still distinguishable (always keep at least 4 to make snap explicit).
    return f"{snapped:.4f}"


def snap_line(line: str) -> tuple[str, int]:
    """Snap any float tokens in `line` if it starts with a linear keyword.

    Returns (new_line, n_replaced). Non-linear-keyword lines pass through.
    SIZE lines get snapped too, which is harmless: if they were already
    site-snapped by snap_lef_to_site.py, the snap-to-mfgrid is a no-op
    (sites at 0.0615 / 0.3635 already land on 0.0001 grid).
    """
    # Strip trailing newline before matching, restore it on the way out —
    # the regex `$` anchor doesn't include `\n`, so doing the substitution
    # on the body-only text and re-appending the newline keeps line
    # boundaries intact (the prior bug: omitted newline collapsed
    # statements onto one line).
    if line.endswith("\n"):
        body, ending = line[:-1], "\n"
    else:
        body, ending = line, ""
    m = KEYWORD_RE.match(body)
    if not m:
        return line, 0
    indent, kw, rest = m.groups()
    n = 0

    def replace(match: re.Match) -> str:
        nonlocal n
        n += 1
        return snap_float(match.group(0))

    new_rest = FLOAT_RE.sub(replace, rest)
    if new_rest == rest:
        return line, 0
    return f"{indent}{kw}{new_rest}{ending}", n


def snap_lef(text: str) -> tuple[str, int, int]:
    out_lines = []
    lines_changed = 0
    tokens_changed = 0
    for line in text.splitlines(keepends=True):
        new_line, n = snap_line(line)
        if n:
            lines_changed += 1
            tokens_changed += n
        out_lines.append(new_line)
    return "".join(out_lines), lines_changed, tokens_changed


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--in", dest="inp", required=True, type=Path)
    p.add_argument("--out", dest="out", required=True, type=Path)
    args = p.parse_args()

    text = args.inp.read_text()
    new_text, lc, tc = snap_lef(text)
    args.out.write_text(new_text)
    print(f"==> Snapped {tc} numeric tokens across {lc} lines")
    print(f"   grid: {MFGRID} µm (= 1 DBU at DATABASE MICRONS = 10000)")
    print(f"==> Wrote {args.out}")


if __name__ == "__main__":
    main()
