#!/usr/bin/env python3
"""scale_platform.py — scale ORFS sky130hd platform Tcl files to opencell-7
class numerics.

Reads scale_factors.json for the area factor (default 40), computes
linear_factor = sqrt(area_factor), and rewrites the hardcoded micron
values in:
  - pdn.tcl       (strap widths, pitches, offsets, macro halos)
  - make_tracks.tcl (track pitches/offsets)
  - setRC.tcl     (per-layer R/sq scales with L_factor; cap-per-length
                   unchanged; via R scales with L_factor**2)
  - tapcell.tcl   (tap distance)

This is a first-order geometric scaling. The cap-per-unit-length is
assumed invariant under uniform shrink (W/S aspect ratios preserved),
which is defensible for a methodology-first scaler but does not capture
the full BEOL physics (e.g. ratio of self-cap to coupling cap shifts
with finer geometry, fringe effects, etc.). Documented in
docs/CUT3_PDK_SCALING_NOTES.md.

Usage:
  python3 scaling/scale_platform.py --in platforms/sky130hd \\
      --out platforms/opencell7
"""
import argparse
import json
import math
import re
import shutil
from pathlib import Path


def load_factors(path: str = "scaling/scale_factors.json") -> tuple[float, float]:
    with open(path) as f:
        d = json.load(f)
    area_factor = float(d["factors"]["area"]["value"])
    return area_factor, math.sqrt(area_factor)


def scale_line_dims(text: str, divisor: float, kw_re: str) -> str:
    """Rewrite lines matching kw_re: divide all bare floats by divisor."""
    out = []
    for line in text.splitlines(keepends=True):
        if re.search(kw_re, line):
            def repl(m):
                v = float(m.group(0))
                return f"{v / divisor:.4f}"
            line = re.sub(r"(?<![A-Za-z_\d.])(?:\d+\.\d+|\d+\.|\.\d+)(?:[eE][-+]?\d+)?",
                          repl, line)
        out.append(line)
    return "".join(out)


# PDN snap grid: ORFS pdngen requires width/pitch/offset to be multiples
# of 2x the database resolution (0.002 um for DATABASE MICRONS 1000). We
# snap up to the next multiple to stay above any min-width constraints.
PDN_SNAP_UM = 0.002


def _snap_up(v: float, grid: float = PDN_SNAP_UM) -> float:
    return math.ceil(v / grid) * grid


def scale_pdn(text: str, lin: float) -> str:
    out_lines = []
    for line in text.splitlines(keepends=True):
        # add_pdn_stripe: scale -width, -pitch, -offset values, snap up to grid
        if "add_pdn_stripe" in line:
            for kw in ("-width", "-pitch", "-offset"):
                line = re.sub(
                    kw + r"\s*\{\s*([\d.eE+-]+)\s*\}",
                    lambda m, _kw=kw: f"{_kw} {{{_snap_up(float(m.group(1))/lin):.5f}}}",
                    line)
        # define_pdn_grid: scale -halo values (4 numbers in braces)
        elif "define_pdn_grid" in line or "-halo" in line:
            def halo_repl(m):
                vals = [float(v) for v in m.group(1).split()]
                return "-halo {" + " ".join(f"{_snap_up(v/lin):.4f}" for v in vals) + "}"
            line = re.sub(r"-halo\s*\{([\d.\s]+)\}", halo_repl, line)
        out_lines.append(line)
    return "".join(out_lines)


def scale_make_tracks(text: str, lin: float) -> str:
    out_lines = []
    for line in text.splitlines(keepends=True):
        if "make_tracks" in line:
            for kw in ("-x_offset", "-x_pitch", "-y_offset", "-y_pitch"):
                line = re.sub(
                    kw + r"\s+([\d.eE+-]+)",
                    lambda m, _kw=kw: f"{_kw} {float(m.group(1))/lin:.5f}",
                    line)
        out_lines.append(line)
    return "".join(out_lines)


def scale_setrc(text: str, lin: float) -> str:
    """Cap unchanged; layer R multiplied by lin (ohms/sq, thickness shrinks);
    via R multiplied by lin**2 (area shrinks)."""
    out_lines = []
    for line in text.splitlines(keepends=True):
        if "set_layer_rc" not in line:
            out_lines.append(line)
            continue
        is_via = " -via " in line
        # Scale only -resistance
        def res_repl(m):
            v = float(m.group(1))
            mult = lin * lin if is_via else lin
            return f"-resistance {v * mult:.6e}"
        line = re.sub(r"-resistance\s+([\d.eE+-]+)", res_repl, line)
        out_lines.append(line)
    return "".join(out_lines)


def scale_tapcell(text: str, lin: float) -> str:
    return re.sub(
        r"-distance\s+([\d.eE+-]+)",
        lambda m: f"-distance {float(m.group(1))/lin:.4f}",
        text)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--in", dest="src", required=True,
                    help="source platform directory (e.g. platforms/sky130hd)")
    ap.add_argument("--out", required=True,
                    help="destination platform directory")
    ap.add_argument("--factors", default="scaling/scale_factors.json")
    ap.add_argument("--force", action="store_true",
                    help="re-scale even if .scaled marker exists (DANGEROUS — "
                         "double-scaling silently produces invalid platforms)")
    args = ap.parse_args()

    area, lin = load_factors(args.factors)
    print(f"area factor: {area:.4f}")
    print(f"linear factor (sqrt): {lin:.4f}")

    src, dst = Path(args.src), Path(args.out)
    marker = dst / ".scaled"
    if marker.exists() and not args.force:
        prev = marker.read_text().strip()
        print(f"ABORT: {marker} exists (prior scaling: {prev}). "
              f"Re-scaling would double-shrink dimensions. "
              f"Use --force to override, or rm the marker after restoring sources.")
        raise SystemExit(2)
    # Files we don't touch (just copy) vs. files we scale
    SCALERS = {
        "pdn.tcl":          scale_pdn,
        "make_tracks.tcl":  scale_make_tracks,
        "setRC.tcl":        scale_setrc,
        "tapcell.tcl":      scale_tapcell,
    }

    for f in src.iterdir():
        d = dst / f.name
        if f.name in SCALERS:
            scaler = SCALERS[f.name]
            d.write_text(scaler(f.read_text(), lin))
            print(f"  scaled  {f.name}")
        elif f.is_file() and f.resolve() != d.resolve():
            shutil.copy2(f, d)
        # else: same-file in-place run, or a directory — skip

    print(f"wrote scaled platform -> {dst}")


if __name__ == "__main__":
    main()
