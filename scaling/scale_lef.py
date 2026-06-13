#!/usr/bin/env python3
"""scale_lef.py — scale a sky130 LEF file's dimensions to a 7nm-class layout.

Reads scale_factors.json to get the area factor (30× by default), computes
a linear factor (sqrt(area_factor) ≈ 5.477), and rewrites every micron-
dimension in the LEF by dividing by that linear factor. This is the LEF
companion to scale_lib.py.

Input formats handled:
  - per-cell LEFs (MACRO ... END <name>)
  - tech LEFs (LAYER, VIA, SITE, MANUFACTURINGGRID, PROPERTYDEFINITIONS)

The scaler is a stateful line-oriented rewriter. It recognises the LEF
keywords whose numeric arguments are micron dimensions, and divides
those numbers by the linear factor. Numeric arguments that are NOT
dimensions (counts, ratios, antenna areas in their own units) are
preserved or scaled differently — see SCALED_KEYWORDS below.

Areas (antenna gate area, antenna diff area) scale by the AREA factor
(area_factor squared in linear terms), not the linear factor.

Usage:
  scaling/scale_lef.py --in <sky130.lef> --out <opencell7.lef>
                       [--factors scaling/scale_factors.json]
  scaling/scale_lef.py --in-dir <cells/> --out-dir <derived/lef/>
                       [--factors scaling/scale_factors.json]
"""

import argparse
import json
import math
import os
import re
from pathlib import Path

# LEF keywords whose numeric arguments are LINEAR micron dimensions.
# Scale by 1/linear_factor.
LINEAR_KEYWORDS = {
    "SIZE",       # SIZE <x> BY <y>
    "ORIGIN",     # ORIGIN <x> <y>
    "RECT",       # RECT <x1> <y1> <x2> <y2>
    "POLYGON",    # POLYGON <x1> <y1> ...
    "PITCH",      # PITCH <x> [<y>]
    "WIDTH",      # WIDTH <value>
    "SPACING",    # SPACING <value>
    "SPACINGTABLE", # values inside are widths/spacings
    "OFFSET",
    "THICKNESS",
    "MINWIDTH",
    "MAXWIDTH",
    "MANUFACTURINGGRID",  # also a length in um
    "ENCLOSURE",
    "MINENCLOSEDAREA",    # actually an area, but rare; skip via fallback
}

# Keywords whose numeric arguments are AREAS (um²). Scale by 1/area_factor.
AREA_KEYWORDS = {
    "AREA",            # metal min-area rule (um^2)
    "ANTENNAGATEAREA",
    "ANTENNADIFFAREA",
}

# Keywords with their own non-dimensional units. DO NOT scale.
# (Resistance in Ohms; capacitance in pF; ratios unitless.)
PRESERVE_KEYWORDS = {
    "RESISTANCE",          # RESISTANCE RPERSQ <value> [ohm/sq]
    "CAPACITANCE",         # CAPACITANCE CPERSQDIST <value> [pF/um^2]
    "EDGECAPACITANCE",     # [pF/um]
    "ANTENNAMAXAREACAR",   # unitless ratio
    "ANTENNAMAXSIDEAREACAR",
    "VERSION",
    "DATABASE",
    "NAMESCASESENSITIVE",
    "BUSBITCHARS",
    "DIVIDERCHAR",
    "UNITS",
}

# Regex for floats INCLUDING scientific notation (the bug-fix). Must
# greedily consume the exponent so we don't scale parts of E-notation
# numbers independently.
_FLOAT_RE = re.compile(
    r"[-+]?(?:\d+\.\d+|\.\d+|\d+)(?:[eE][-+]?\d+)?"
)


def scale_floats_in_line(line, linear_factor, area_factor):
    """For a line whose first non-whitespace token is a recognised keyword,
    scale the appropriate numbers. Return the rewritten line."""
    stripped = line.lstrip()
    if not stripped or stripped.startswith("#"):
        return line
    tokens = stripped.split()
    if not tokens:
        return line
    kw = tokens[0]

    # Decide what to divide each float by.
    if kw in PRESERVE_KEYWORDS:
        return line
    if kw in LINEAR_KEYWORDS:
        divisor = linear_factor
    elif kw in AREA_KEYWORDS:
        divisor = area_factor
    else:
        return line

    # Rewrite floats in place (preserves surrounding whitespace + tokens).
    def repl(m):
        try:
            v = float(m.group(0))
        except ValueError:
            return m.group(0)
        return _format_number(v / divisor)

    indent = line[: len(line) - len(stripped)]
    # Skip the keyword token; only rewrite numerics after it.
    head, _, tail = stripped.partition(" ")
    new_tail = _FLOAT_RE.sub(repl, tail)
    return f"{indent}{head} {new_tail}"


def _format_number(x):
    """LEF-style 6-decimal float formatting; integers stay integers."""
    if x == int(x) and abs(x) < 1e6:
        # keep as integer-looking value
        return f"{int(x)}"
    return f"{x:.6f}".rstrip("0").rstrip(".")


def scale_lef_text(text, linear_factor, area_factor):
    out = []
    for line in text.splitlines(keepends=True):
        out.append(scale_floats_in_line(line, linear_factor, area_factor))
    return "".join(out)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--in", dest="src", help="single sky130 LEF input")
    ap.add_argument("--out", dest="dst", help="single output LEF")
    ap.add_argument("--in-dir", help="directory containing many sky130 LEFs")
    ap.add_argument("--out-dir", help="directory to write scaled LEFs to")
    ap.add_argument(
        "--factors",
        default=str(Path(__file__).parent / "scale_factors.json"),
    )
    ap.add_argument(
        "--lef-suffix",
        default=".lef",
        help="when scanning --in-dir, only files ending in this suffix are"
        " processed (default .lef; skips .magic.lef)",
    )
    ap.add_argument(
        "--exclude-suffix",
        default=".magic.lef",
        help="exclude files ending in this suffix from --in-dir scan",
    )
    args = ap.parse_args()

    cfg = json.load(open(args.factors))
    area_factor = cfg["factors"]["area"]["value"]
    linear_factor = math.sqrt(area_factor)
    print(f"area factor: {area_factor:.4f}")
    print(f"linear factor (sqrt): {linear_factor:.4f}")

    if args.src and args.dst:
        text = Path(args.src).read_text()
        scaled = scale_lef_text(text, linear_factor, area_factor)
        Path(args.dst).parent.mkdir(parents=True, exist_ok=True)
        Path(args.dst).write_text(scaled)
        print(f"wrote {args.dst}")
        return

    if not args.in_dir or not args.out_dir:
        raise SystemExit("either --in/--out or --in-dir/--out-dir required")

    in_dir = Path(args.in_dir)
    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    count = 0
    for p in sorted(in_dir.rglob("*" + args.lef_suffix)):
        if str(p).endswith(args.exclude_suffix):
            continue
        rel = p.relative_to(in_dir)
        # Flatten the directory tree: derived/lef/sky130_fd_sc_hd__inv_1.lef
        out_path = out_dir / p.name
        text = p.read_text()
        scaled = scale_lef_text(text, linear_factor, area_factor)
        out_path.write_text(scaled)
        count += 1
    print(f"scaled {count} LEF files into {out_dir}")


if __name__ == "__main__":
    main()
