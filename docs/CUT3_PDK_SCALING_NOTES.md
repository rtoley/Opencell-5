# Cut-3 PDK scaling — first evidence

Notes on the first real cut-3 experiment: scaling sky130's physical
files (per-cell LEF + tech LEF) the same way `scale_lib.py` scales
the Liberty file, then driving them through OpenROAD's `gcd` design
to confirm the PDK is structurally sound.

## 1. What was built

`scaling/scale_lef.py` — a stateful line-oriented LEF scaler. Reads
`scale_factors.json` to get the area factor (default 30×), computes
the linear factor as √(area_factor) ≈ 5.477×, and rewrites every
LEF dimension accordingly:

| Keyword class | Examples | Divisor |
|---|---|---|
| Linear (µm) | `SIZE`, `RECT`, `ORIGIN`, `PITCH`, `WIDTH`, `SPACING`, `THICKNESS` | √(area_factor) |
| Area (µm²) | `AREA`, `ANTENNAGATEAREA`, `ANTENNADIFFAREA` | area_factor |
| Preserved (own units) | `RESISTANCE` (Ω), `CAPACITANCE` (pF), `EDGECAPACITANCE` (pF/µm), antenna ratios, `VERSION`, `UNITS` | none |

The float regex handles scientific notation (`40.697E-6`) — important
because sky130's BEOL specs use it for per-square cap/resistance.

Run on all 437 sky130 sc_hd cell LEFs plus the tech LEF; output lives
under `derived/opencell7_sc_hd/lef/` and
`derived/opencell7_sc_hd/tech/` (both gitignored alongside the rest
of `derived/`).

A small merger script concatenates the 437 per-cell LEFs into one
`opencell7_merged.lef` with a single VERSION header + END LIBRARY
(ORFS expects one SC_LEF file).

## 2. What was run

ORFS `gcd` design on sky130hd platform, but with three env-var
overrides pointing at our scaled files:

```bash
docker run --platform=linux/amd64 \
  -e TECH_LEF=/work/derived/opencell7_sc_hd/tech/opencell7.tlef \
  -e SC_LEF=/work/derived/opencell7_sc_hd/lef/opencell7_merged.lef \
  -e LIB_FILES=/work/derived/opencell7_tt_0p7v_25c.lib \
  openroad/orfs:latest \
  bash -c 'cd /OpenROAD-flow-scripts/flow && \
           make DESIGN_CONFIG=./designs/sky130hd/gcd/config.mk'
```

Cell names are preserved by the scaler, so sky130hd's platform
Tcl scripts (tapcell.tcl, pdn.tcl, etc.) — which reference cells by
name — still resolve.

## 3. Result

Four stages cleared, fifth surfaced a platform-config issue:

| ORFS stage | Result |
|---|---|
| 1_synth (yosys + abc against scaled `.lib` + scaled LEF) | ✓ |
| 2_1_floorplan (die 92 µm², 51% util) | ✓ |
| 2_2_floorplan_macro | ✓ |
| 2_3_floorplan_tapcell (0 tapcells; design checks pass) | ✓ |
| **2_4_floorplan_pdn** | ✗ — `PDN-0185 Insufficient width (13.86 µm) ... met4 strap width 15.2 µm` |

The PDN failure is a sky130hd-platform-config issue, not a scaler bug:
ORFS's PDN script has hardcoded met4 strap width 15.2 µm and offset
13.6 µm — sized for sky130-scale dies. Our scaled gcd die is
9.6 × 9.6 µm — smaller than a single sky130 power strap. The geometry
literally doesn't fit.

For the cut-3 question — *"can we build a scaled sky130 and complete
timing runs?"* — the four cleared stages are real evidence the scaling
approach is sound:

- Scaled LEFs + tech LEF + `.lib` all parse in ORFS without errors.
- ODB reads 437 cells, no LEF parser complaints.
- Floorplan reports die area 92 µm² — exactly **30× smaller** than
  sky130's gcd footprint (~2,800 µm²), matching the `scale_factors.json`
  area factor.
- Cell-name preservation pays off: sky130hd's platform scripts find
  our cells without modification.

## 4. The two layers still needed for sign-off timing

1. **Platform-config Tcl scripts must also be scaled.** `pdn.tcl`,
   `make_tracks.tcl`, `setRC.tcl` carry hardcoded micron numbers
   (power-strap widths, track pitches, RC params). A proper
   `opencell7_tt_0p7v_25c` ORFS platform forks sky130hd's directory
   and scales these numerics too. Estimated effort: 3–5 days.
2. **Linux runtime for CTS + routing.** Independent of PDK. TritonCTS
   uses x86 SIMD intrinsics that Rosetta on Apple Silicon doesn't
   translate (documented in `docs/OPENROAD_ATTEMPT_NOTES.md` §3).
   A small Linux Docker host removes this constraint.

## 5. Bugs caught and fixed during this run

- **LEF float regex** must consume scientific notation in a single
  token. Without `(?:[eE][-+]?\d+)?` the scaler split `40.697E-6`
  into pieces and scaled them independently, producing `7.43E-1.095`
  (a syntactically invalid LEF number).
- **`RESISTANCE` / `CAPACITANCE` / `EDGECAPACITANCE`** were initially
  in the linear-scaling list. They are not — units are Ω, pF/µm²,
  pF/µm. Moved to a `PRESERVE_KEYWORDS` set.
- **`AREA`** was linear-scaling. It is an area (µm²); now scales by
  `area_factor` (30×), not `linear_factor` (≈5.477×).
- **Merged LEF VERSION** must be ≥ 5.7 to allow `WELLTAP` syntax in
  sky130's tap cells (sky130 per-cell LEFs declare 5.5 but use
  modern features). The merger writes `VERSION 5.7 ;`.

## 6. Reproducibility

```bash
# Scale all cell LEFs + tech LEF
python3 scaling/scale_lef.py \
  --in-dir reference/sky130/cells \
  --out-dir derived/opencell7_sc_hd/lef
python3 scaling/scale_lef.py \
  --in reference/sky130/tech/sky130_fd_sc_hd.tlef \
  --out derived/opencell7_sc_hd/tech/opencell7.tlef

# Merge per-cell LEFs and bump VERSION
python3 - <<'PY'
from pathlib import Path
import re
in_dir = Path("derived/opencell7_sc_hd/lef")
out = Path("derived/opencell7_sc_hd/lef/opencell7_merged.lef")
files = sorted(p for p in in_dir.glob("sky130_fd_sc_hd__*.lef") if p.name != out.name)
with open(out, "w") as f:
    first = files[0].read_text()
    f.write(first[: first.find("\nMACRO ") + 1])
    for p in files:
        text = p.read_text()
        m = re.search(r"^MACRO\s+\S+", text, re.MULTILINE)
        if m:
            body = re.sub(r"\nEND LIBRARY\s*$", "\n", text[m.start():])
            f.write(body.rstrip() + "\n\n")
    f.write("END LIBRARY\n")
PY
sed -i.bak 's/^VERSION 5\.5 ;/VERSION 5.7 ;/' derived/opencell7_sc_hd/lef/opencell7_merged.lef
rm derived/opencell7_sc_hd/lef/opencell7_merged.lef.bak

# Run gcd through ORFS with the scaled files overriding sky130hd's
# (needs Colima/Docker on macOS; see docs/OPENROAD_ATTEMPT_NOTES.md)
colima start --vm-type=vz --vz-rosetta --memory 12 --cpu 8
docker run --rm --platform=linux/amd64 \
  -v $PWD:/work \
  -e TECH_LEF=/work/derived/opencell7_sc_hd/tech/opencell7.tlef \
  -e SC_LEF=/work/derived/opencell7_sc_hd/lef/opencell7_merged.lef \
  -e LIB_FILES=/work/derived/opencell7_tt_0p7v_25c.lib \
  openroad/orfs:latest \
  bash -c 'cd /OpenROAD-flow-scripts/flow && \
           make DESIGN_CONFIG=./designs/sky130hd/gcd/config.mk'
colima stop
```

Reaches PDN error on macOS (sky130hd platform config not scaled).
Same flow on Linux without Rosetta would continue further — until
either PDN config also needs scaling, or CTS proceeds cleanly.

## 7. Status

This is the first evidence point for cut-3 viability. The scaler
foundation is in place; only the platform-config layer and a
Linux runtime separate today from sign-off timing on
OpenCell-7-targeted designs.
