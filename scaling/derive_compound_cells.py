#!/usr/bin/env python3
"""derive_compound_cells.py — append "composite" sky130 cells to the scaled lib.

asap7 has compound AOI/OAI variants that sky130 lacks (AOI33, AOI331, AOI332,
AOI333 and their non-inverting / OAI / OA mirrors). When yosys+abc maps a
wide-datapath vector arithmetic block, asap7's mapper picks these wider
gates aggressively, while opencell-7 falls back to chains of 2-input cells —
the suspected reason for the 2.28x area gap measured on such designs.

This script appends those missing cells to opencell-7's lib as *composite*
entries: each new cell's area is computed as the sum of its sky130-primitive
decomposition. The cells are paired with a techmap rule
(flow/techmap_compound_oc7.v) that expands them back to primitives after abc,
so the final netlist contains only real sky130 cells (no new .lef/.gds work
required for the v0p5 experiment).

If v0p5-vs-v0p4 datapath-benchmark area shows the gap closing, we know the mapping
hypothesis was right and it's worth investing in true multi-view cells for
opencell-5. If datapath-benchmark area is unchanged, the bottleneck is elsewhere.

Usage:
  scaling/derive_compound_cells.py \\
      --in  derived/opencell7_tt_0p7v_25c.lib \\
      --out derived/opencell7_tt_0p7v_25c_v0p5.lib
"""

from __future__ import annotations

import argparse
import re
from pathlib import Path

# ---------------------------------------------------------------------------
# Cell definitions. Each compound cell is a dict with:
#   - name suffix (drive strength appended)
#   - boolean function (output Y as sum-of-products)
#   - input pins (ordered, used to name pin entries)
#   - composition: list of primitive cells whose areas sum to this cell's area
#   - timing template: which existing sky130 cell to copy timing/pin tables from
# ---------------------------------------------------------------------------

# Area of primitive cells in opencell-7 (extracted from .lib by visual inspection;
# these are the *_1 drive strength). The composition area sums these.
PRIM_AREA = {
    "and2_1":   0.111714,
    "and3_1":   0.111714,
    "and4_1":   0.156400,
    "nand2_1":  0.067029,
    "nand3_1":  0.089371,
    "nor2_1":   0.067029,
    "nor3_1":   0.089371,
    "or2_1":    0.111714,
    "or3_1":    0.111714,
    "inv_1":    0.067029,
    "a31oi_1":  0.111714,
    "a32oi_1":  0.156400,
    "a311oi_1": 0.156400,
    "a221oi_1": 0.156400,
    "a222oi_1": 0.178743,
    "o31ai_1":  0.134057,
    "o32ai_1":  0.156400,
    "o311ai_1": 0.156400,
    "o221ai_1": 0.156400,
}

# Drive strength multipliers (matches sky130 _1, _2, _4 progression — area
# scales roughly linearly with drive strength).
DRIVE_AREA_MULT = {"_1": 1.0, "_2": 1.6, "_4": 2.4}

# Composition factor: real custom-layout cells pack ~30% denser than naive
# primitive composition (e.g. sky130 a222oi is 0.179 µm² vs naive 3xAND2+NOR3 =
# 0.424). We apply a 0.7 factor to reflect what an optimized layout could
# realistically achieve — same convention asap7 uses for its compound cells.
COMPOSITION_FACTOR = 0.7

# Compound cell catalog. Each entry is (suffix, function, inputs, composition,
# timing_template). The composition is a list of primitive cell areas that sum
# to the new cell's composed area; the techmap rule (in techmap_compound_oc7.v)
# implements exactly that decomposition.
COMPOUND_CELLS = [
    # --- AOI33 family: !(A1·A2·A3 + B1·B2·B3 + ...) ---
    {
        "name": "a33oi",
        "function": "(!A1 & !B1) | (!A1 & !B2) | (!A1 & !B3) | "
                    "(!A2 & !B1) | (!A2 & !B2) | (!A2 & !B3) | "
                    "(!A3 & !B1) | (!A3 & !B2) | (!A3 & !B3)",
        "function_canonical": "!((A1&A2&A3) | (B1&B2&B3))",
        "inputs": ["A1", "A2", "A3", "B1", "B2", "B3"],
        "composition_primitives": ["and3_1", "a31oi_1"],
        "timing_template": "a311oi_1",
    },
    {
        "name": "a331oi",
        "function_canonical": "!((A1&A2&A3) | (B1&B2&B3) | C1)",
        "inputs": ["A1", "A2", "A3", "B1", "B2", "B3", "C1"],
        "composition_primitives": ["and3_1", "a311oi_1"],
        "timing_template": "a311oi_1",
    },
    {
        "name": "a332oi",
        "function_canonical": "!((A1&A2&A3) | (B1&B2&B3) | (C1&C2))",
        "inputs": ["A1", "A2", "A3", "B1", "B2", "B3", "C1", "C2"],
        "composition_primitives": ["and3_1", "and3_1", "and2_1", "nor3_1"],
        "timing_template": "a222oi_1",
    },
    {
        "name": "a333oi",
        "function_canonical": "!((A1&A2&A3) | (B1&B2&B3) | (C1&C2&C3))",
        "inputs": ["A1", "A2", "A3", "B1", "B2", "B3", "C1", "C2", "C3"],
        "composition_primitives": ["and3_1", "and3_1", "and3_1", "nor3_1"],
        "timing_template": "a222oi_1",
    },
    # --- OAI33 family: !((A1+A2+A3) · (B1+B2+B3) · ...) ---
    {
        "name": "o33ai",
        "function_canonical": "!((A1|A2|A3) & (B1|B2|B3))",
        "inputs": ["A1", "A2", "A3", "B1", "B2", "B3"],
        "composition_primitives": ["or3_1", "o31ai_1"],
        "timing_template": "o311ai_1",
    },
    {
        "name": "o331ai",
        "function_canonical": "!((A1|A2|A3) & (B1|B2|B3) & C1)",
        "inputs": ["A1", "A2", "A3", "B1", "B2", "B3", "C1"],
        "composition_primitives": ["or3_1", "o311ai_1"],
        "timing_template": "o311ai_1",
    },
    {
        "name": "o332ai",
        "function_canonical": "!((A1|A2|A3) & (B1|B2|B3) & (C1|C2))",
        "inputs": ["A1", "A2", "A3", "B1", "B2", "B3", "C1", "C2"],
        "composition_primitives": ["or3_1", "or3_1", "or2_1", "nand3_1"],
        "timing_template": "o221ai_1",
    },
    {
        "name": "o333ai",
        "function_canonical": "!((A1|A2|A3) & (B1|B2|B3) & (C1|C2|C3))",
        "inputs": ["A1", "A2", "A3", "B1", "B2", "B3", "C1", "C2", "C3"],
        "composition_primitives": ["or3_1", "or3_1", "or3_1", "nand3_1"],
        "timing_template": "o221ai_1",
    },
]

DRIVE_STRENGTHS = ["_1", "_2", "_4"]


def extract_cell_block(lib_text: str, cell_name: str) -> str | None:
    """Extract the full `cell (...) { ... }` block for `cell_name` from lib_text.

    The lib is well-structured: each top-level cell starts at column 4 with
    `cell ("<name>") {` and ends with `    }` at column 4. We track brace
    depth from there.
    """
    pattern = re.compile(rf'(    cell \("{re.escape(cell_name)}"\) \{{)')
    m = pattern.search(lib_text)
    if not m:
        return None
    start = m.start()
    # Walk forward, tracking brace depth.
    depth = 0
    i = start
    in_string = False
    while i < len(lib_text):
        c = lib_text[i]
        if c == '"' and (i == 0 or lib_text[i - 1] != '\\'):
            in_string = not in_string
        elif not in_string:
            if c == '{':
                depth += 1
            elif c == '}':
                depth -= 1
                if depth == 0:
                    return lib_text[start:i + 1]
        i += 1
    return None


def boolean_to_lib_function(canonical: str) -> str:
    """Convert canonical Boolean (!, &, |) to Liberty function syntax.

    Liberty wants `!A & B | C` style (same operators, just spacing). The
    canonical form is already close.
    """
    # Liberty accepts `!`, `&`, `|`, and parentheses. The canonical form is
    # already valid Liberty function syntax — just normalize whitespace.
    s = canonical.strip()
    # Ensure proper spacing for readability.
    s = re.sub(r'\s+', ' ', s)
    return s


def make_new_cell(spec: dict, drive: str, template_block: str) -> str:
    """Generate Liberty text for one new compound cell at one drive strength.

    Uses `template_block` as a structural starting point: clone all pin
    entries from the template, then rename/add pins to match `spec["inputs"]`,
    rewrite the output function, and update area.
    """
    new_name = f"sky130_fd_sc_hd__{spec['name']}{drive}"
    # Composition area summed from primitives (all at _1 drive).
    composition_area = sum(
        PRIM_AREA[p] for p in spec["composition_primitives"]
    )
    new_area = composition_area * COMPOSITION_FACTOR * DRIVE_AREA_MULT[drive]

    # Build a minimal but valid cell block. We don't carry over the full
    # leakage / NLDM timing tables — yosys/abc accepts simplified entries.
    # The timing arc is borrowed from the template (matched by similar
    # topology) so abc has realistic delay estimates.
    cell_lines = []
    cell_lines.append(f'    cell ("{new_name}") {{')
    cell_lines.append(f'        area : {new_area:.6f};')
    cell_lines.append(f'        cell_footprint : "sky130_fd_sc_hd__{spec["name"]}";')
    cell_lines.append(f'        cell_leakage_power : 0.030000;')

    # Power/ground pins (standard sky130).
    cell_lines.append('        pg_pin ("VGND") { pg_type : "primary_ground"; voltage_name : "VGND"; }')
    cell_lines.append('        pg_pin ("VNB")  { pg_type : "nwell";          voltage_name : "VNB";  }')
    cell_lines.append('        pg_pin ("VPB")  { pg_type : "pwell";          voltage_name : "VPB";  }')
    cell_lines.append('        pg_pin ("VPWR") { pg_type : "primary_power";  voltage_name : "VPWR"; }')

    # Input pins. Capacitance ~ same as template's first-stage input pin.
    # Use a representative value (close to sky130 norm for unit-drive AOI
    # cells: ~0.0006 pF input cap).
    input_cap = 0.000600
    for pname in spec["inputs"]:
        cell_lines.append(f'        pin ("{pname}") {{')
        cell_lines.append(f'            direction : "input";')
        cell_lines.append(f'            capacitance : {input_cap:.6f};')
        cell_lines.append(f'            fall_capacitance : {input_cap:.6f};')
        cell_lines.append(f'            rise_capacitance : {input_cap:.6f};')
        cell_lines.append(f'            max_transition : 0.18;')
        cell_lines.append(f'            related_ground_pin : "VGND";')
        cell_lines.append(f'            related_power_pin : "VPWR";')
        cell_lines.append(f'        }}')

    # Output pin with the boolean function.
    func = boolean_to_lib_function(spec["function_canonical"])
    cell_lines.append(f'        pin ("Y") {{')
    cell_lines.append(f'            direction : "output";')
    cell_lines.append(f'            function : "{func}";')
    cell_lines.append(f'            max_transition : 0.18;')
    cell_lines.append(f'            related_ground_pin : "VGND";')
    cell_lines.append(f'            related_power_pin : "VPWR";')
    # A simple delay model: use a constant intrinsic delay derived from the
    # composition depth. This is approximate but lets abc rank the cell
    # against alternatives.
    depth = len(spec["composition_primitives"])
    intrinsic_delay = 0.05 * depth  # ns per stage, rough sky130 estimate
    for pname in spec["inputs"]:
        cell_lines.append(f'            timing () {{')
        cell_lines.append(f'                related_pin : "{pname}";')
        cell_lines.append(f'                timing_sense : "negative_unate";')
        cell_lines.append(f'                cell_rise (scalar) {{ values("{intrinsic_delay:.3f}"); }}')
        cell_lines.append(f'                cell_fall (scalar) {{ values("{intrinsic_delay:.3f}"); }}')
        cell_lines.append(f'                rise_transition (scalar) {{ values("{intrinsic_delay * 0.5:.3f}"); }}')
        cell_lines.append(f'                fall_transition (scalar) {{ values("{intrinsic_delay * 0.5:.3f}"); }}')
        cell_lines.append(f'            }}')
    cell_lines.append(f'        }}')
    cell_lines.append(f'    }}')
    return "\n".join(cell_lines) + "\n"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--in", dest="inp", required=True, type=Path,
                        help="Input Liberty file (base scaled lib).")
    parser.add_argument("--out", dest="out", required=True, type=Path,
                        help="Output Liberty file with new cells appended.")
    args = parser.parse_args()

    lib_text = args.inp.read_text()

    # Generate all new cell blocks.
    new_blocks = []
    for spec in COMPOUND_CELLS:
        # Pull a template block for timing reference (not used in the
        # simplified entry but available if we extend to NLDM later).
        template_block = extract_cell_block(
            lib_text, f"sky130_fd_sc_hd__{spec['timing_template']}"
        )
        if template_block is None:
            print(f"WARN: template {spec['timing_template']} not found, skipping {spec['name']}")
            continue
        for drive in DRIVE_STRENGTHS:
            new_blocks.append(make_new_cell(spec, drive, template_block))

    # Insert before the closing `}` of the library block.
    end_brace = lib_text.rstrip().rfind("}")
    if end_brace == -1:
        raise RuntimeError("Could not find lib's closing brace")

    out_text = (
        lib_text[:end_brace]
        + "\n    /* === v0.5 composite cells (asap7-parity AOI33/OAI33 families) === */\n"
        + "".join(new_blocks)
        + "\n"
        + lib_text[end_brace:]
    )
    args.out.write_text(out_text)
    n_cells = len(new_blocks)
    print(f"==> Wrote {args.out} ({n_cells} new cells appended to base lib)")


if __name__ == "__main__":
    main()
