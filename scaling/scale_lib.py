#!/usr/bin/env python3
"""scale_lib.py — scale a sky130 Liberty file to a 7nm-class operating point.

Reads scale_factors.json, applies factors to numeric fields, preserves
structure and attribution. Single file in, single file out.

Usage:
  scaling/scale_lib.py --in <sky130.lib> --out <opencell7.lib> \\
      [--factors scaling/scale_factors.json]

Approach:
  1. Tokenize the Liberty file.
  2. Walk groups recursively, tracking the group stack.
  3. For each numeric value, decide scaling based on:
       - simple attribute: (parent_group, attr_name) -> factor
       - complex attribute (e.g. values, index_1): (parent_group, attr_name)
         with template-aware override of index_X based on variable_X type.
  4. Rewrite numbers in place; re-emit by joining token text.
  5. Substitute library and operating-condition names; inject derivation header.
"""

import argparse
import datetime
import json
import os
import re
import sys
from pathlib import Path


TOKEN_RE = re.compile(
    r"""
    (?P<COMMENT>/\*[\s\S]*?\*/)|
    (?P<BACKSLASH_NL>\\\r?\n)|
    (?P<NL>\r?\n)|
    (?P<WS>[ \t]+)|
    (?P<STRING>"(?:[^"\\]|\\.)*")|
    (?P<NUMBER>[+-]?(?:\d+\.\d+|\.\d+|\d+\.|\d+)(?:[eE][+-]?\d+)?)|
    (?P<IDENT>[A-Za-z_][A-Za-z_0-9.]*)|
    (?P<LBRACE>\{)|
    (?P<RBRACE>\})|
    (?P<LPAREN>\()|
    (?P<RPAREN>\))|
    (?P<SEMI>;)|
    (?P<COMMA>,)|
    (?P<COLON>:)|
    (?P<OTHER>.)
""",
    re.VERBOSE,
)

TRIVIA = {"WS", "NL", "COMMENT", "BACKSLASH_NL"}


def tokenize(source):
    tokens = []
    pos = 0
    n = len(source)
    while pos < n:
        m = TOKEN_RE.match(source, pos)
        if not m:
            raise ValueError(f"tokenize stuck at pos {pos}: {source[pos:pos+60]!r}")
        kind = m.lastgroup
        text = m.group()
        tokens.append([kind, text])
        pos = m.end()
    return tokens


def skip_trivia(tokens, i, end):
    while i < end and tokens[i][0] in TRIVIA:
        i += 1
    return i


# (parent_group, attr_name) -> factor key (None means leave alone).
SIMPLE_ATTR_SCALING = {
    ("cell", "area"): "area",
    ("cell", "cell_leakage_power"): "leakage",
    ("pin", "capacitance"): "input_cap",
    ("pin", "rise_capacitance"): "input_cap",
    ("pin", "fall_capacitance"): "input_cap",
    ("pin", "max_capacitance"): "input_cap",
    ("pin", "max_transition"): "delay",
    ("leakage_power", "value"): "leakage",
    ("library", "default_max_transition"): "delay",
    ("library", "default_max_capacitance"): "input_cap",
    ("library", "default_max_fanout"): None,
    ("library", "default_inout_pin_cap"): "input_cap",
    ("library", "default_input_pin_cap"): "input_cap",
    ("library", "default_output_pin_cap"): "input_cap",
    ("library", "default_cell_leakage_power"): "leakage",
}

# Numbers inside `IDENT (args) ;` get scaled when (parent_group, IDENT) matches.
COMPLEX_ATTR_SCALING = {
    # NLDM delay tables
    ("cell_rise", "values"): "delay",
    ("cell_fall", "values"): "delay",
    ("rise_transition", "values"): "delay",
    ("fall_transition", "values"): "delay",
    ("cell_rise", "index_1"): "delay",
    ("cell_fall", "index_1"): "delay",
    ("rise_transition", "index_1"): "delay",
    ("fall_transition", "index_1"): "delay",
    ("cell_rise", "index_2"): "input_cap",
    ("cell_fall", "index_2"): "input_cap",
    ("rise_transition", "index_2"): "input_cap",
    ("fall_transition", "index_2"): "input_cap",
    # NLDM power tables
    ("rise_power", "values"): "dynamic_power",
    ("fall_power", "values"): "dynamic_power",
    ("power", "values"): "dynamic_power",
    ("rise_power", "index_1"): "delay",
    ("fall_power", "index_1"): "delay",
    ("power", "index_1"): "delay",
    ("rise_power", "index_2"): "input_cap",
    ("fall_power", "index_2"): "input_cap",
    ("power", "index_2"): "input_cap",
    # Setup / hold constraint tables: VALUES are the constraint time (setup_hold);
    # both INDEX axes are transitions (delay).
    ("rise_constraint", "values"): "setup_hold",
    ("fall_constraint", "values"): "setup_hold",
    ("rise_constraint", "index_1"): "delay",
    ("rise_constraint", "index_2"): "delay",
    ("fall_constraint", "index_1"): "delay",
    ("fall_constraint", "index_2"): "delay",
}

# These get corner-specific substitution: kind in {"voltage", "temperature"}.
SUBSTITUTE_ATTRS = {
    ("library", "nom_voltage"): "voltage",
    ("library", "nom_temperature"): "temperature",
    ("operating_conditions", "voltage"): "voltage",
    ("operating_conditions", "temperature"): "temperature",
}

TEMPLATE_GROUPS = {"lu_table_template", "power_lut_template"}


def var_kind_to_factor(var_name):
    """Map a Liberty variable_N type name to a scaling factor key."""
    if var_name is None:
        return None
    v = var_name.lower()
    if "cap" in v:
        return "input_cap"
    # transitions, related_pin_transition, constrained_pin_transition, etc.
    return "delay"


def collect_template_vars(tokens, start, end):
    """Scan template body for variable_1 / variable_2 assignments."""
    var1 = var2 = None
    i = start
    while i < end:
        kind, text = tokens[i]
        if kind == "IDENT" and text in ("variable_1", "variable_2"):
            j = skip_trivia(tokens, i + 1, end)
            if j < end and tokens[j][0] == "COLON":
                k = skip_trivia(tokens, j + 1, end)
                if k < end and tokens[k][0] == "IDENT":
                    if text == "variable_1":
                        var1 = tokens[k][1]
                    else:
                        var2 = tokens[k][1]
        i += 1
    return var1, var2


def format_number(x):
    """Render a scaled float in a sky130-style compact form."""
    if x == 0:
        return "0"
    if abs(x) < 1e-30:
        return "0"
    # Use up to 6 significant digits; strip trailing zeros except the leading one
    s = f"{x:.6g}"
    return s


class Scaler:
    def __init__(self, cfg, corner_name):
        self.cfg = cfg
        self.factors = cfg["factors"]
        if corner_name not in cfg.get("corners", {}):
            raise ValueError(
                f"corner {corner_name!r} not in scale_factors.json corners; "
                f"available: {list(cfg.get('corners', {}).keys())}"
            )
        self.corner_name = corner_name
        self.corner = cfg["corners"][corner_name]
        self.derate = self.factors.get("process_derate", {"operation": "multiply", "value": 1.0})

    def apply(self, val, factor_key):
        if factor_key is None:
            return val
        f = self.factors[factor_key]
        op = f["operation"]
        v = f["value"]
        if op == "divide":
            result = val / v
        elif op == "multiply":
            result = val * v
        else:
            raise ValueError(f"unknown op {op} for factor {factor_key}")
        # Compose process_derate onto delay-class quantities.
        if factor_key in ("delay", "setup_hold"):
            d_op = self.derate.get("operation", "multiply")
            d_v = self.derate.get("value", 1.0)
            if d_op == "multiply":
                result = result * d_v
            elif d_op == "divide":
                result = result / d_v
        return result

    def substitute(self, val, kind):
        """kind in {'voltage', 'temperature'}."""
        src = self.corner["source"][kind]
        tgt = self.corner["target"][kind]
        # Use a tolerance proportional to the source magnitude, with a floor.
        tol = max(abs(src) * 0.05, 0.1)
        if abs(val - src) <= tol:
            return tgt
        return val


def scale_numbers_in_range(tokens, start, end, scaler, factor_key):
    """Scale every NUMBER token and every number inside STRINGs in [start, end)."""
    if factor_key is None:
        return
    for i in range(start, end):
        kind, text = tokens[i]
        if kind == "NUMBER":
            try:
                v = float(text)
            except ValueError:
                continue
            tokens[i][1] = format_number(scaler.apply(v, factor_key))
        elif kind == "STRING":
            inner = text[1:-1]
            parts = [p.strip() for p in inner.split(",")]
            scaled = []
            for p in parts:
                try:
                    v = float(p)
                    scaled.append(format_number(scaler.apply(v, factor_key)))
                except ValueError:
                    scaled.append(p)
            tokens[i][1] = '"' + ", ".join(scaled) + '"'


def walk_group(tokens, start, end, scaler, group_stack, var_overrides=None):
    """Walk tokens [start, end) processing groups recursively.

    var_overrides: dict mapping complex-attr name (e.g. 'index_1') to factor_key,
    used to override COMPLEX_ATTR_SCALING when inside a template that knows its
    own variable_X type.
    """
    i = start
    while i < end:
        i = skip_trivia(tokens, i, end)
        if i >= end:
            break
        kind, text = tokens[i]

        if kind == "IDENT":
            j = skip_trivia(tokens, i + 1, end)
            if j >= end:
                i = j
                continue
            next_kind = tokens[j][0]

            if next_kind == "LPAREN":
                # Find matching RPAREN
                depth = 1
                k = j + 1
                while k < end and depth > 0:
                    tk = tokens[k][0]
                    if tk == "LPAREN":
                        depth += 1
                    elif tk == "RPAREN":
                        depth -= 1
                    k += 1
                rparen_end = k  # one past matching RPAREN

                m = skip_trivia(tokens, rparen_end, end)
                if m < end and tokens[m][0] == "LBRACE":
                    # Group with args: IDENT (args) { body }
                    group_name = text
                    body_start = m + 1
                    # Find matching RBRACE for body
                    depth = 1
                    b = body_start
                    while b < end and depth > 0:
                        tb = tokens[b][0]
                        if tb == "LBRACE":
                            depth += 1
                        elif tb == "RBRACE":
                            depth -= 1
                        b += 1
                    body_end = b - 1  # index of RBRACE

                    new_overrides = None
                    if group_name in TEMPLATE_GROUPS:
                        v1, v2 = collect_template_vars(tokens, body_start, body_end)
                        new_overrides = {
                            "index_1": var_kind_to_factor(v1),
                            "index_2": var_kind_to_factor(v2),
                        }

                    group_stack.append(group_name)
                    walk_group(tokens, body_start, body_end, scaler, group_stack, new_overrides)
                    group_stack.pop()

                    i = body_end + 1
                    continue

                elif m < end and tokens[m][0] == "SEMI":
                    # Complex attribute: IDENT (args) ;
                    parent = group_stack[-1] if group_stack else None
                    factor_key = None
                    if var_overrides and text in var_overrides:
                        factor_key = var_overrides[text]
                    if factor_key is None:
                        factor_key = COMPLEX_ATTR_SCALING.get((parent, text))
                    if factor_key:
                        scale_numbers_in_range(tokens, j + 1, rparen_end - 1, scaler, factor_key)
                    i = m + 1
                    continue
                else:
                    i = rparen_end
                    continue

            elif next_kind == "LBRACE":
                # Group without args: IDENT { body }
                group_name = text
                body_start = j + 1
                depth = 1
                b = body_start
                while b < end and depth > 0:
                    tb = tokens[b][0]
                    if tb == "LBRACE":
                        depth += 1
                    elif tb == "RBRACE":
                        depth -= 1
                    b += 1
                body_end = b - 1
                group_stack.append(group_name)
                walk_group(tokens, body_start, body_end, scaler, group_stack, None)
                group_stack.pop()
                i = body_end + 1
                continue

            elif next_kind == "COLON":
                # Simple attribute: IDENT : VALUE ;
                v = skip_trivia(tokens, j + 1, end)
                parent = group_stack[-1] if group_stack else None
                sub_kind = SUBSTITUTE_ATTRS.get((parent, text))
                if sub_kind is not None:
                    if v < end and tokens[v][0] == "NUMBER":
                        val = float(tokens[v][1])
                        new_val = scaler.substitute(val, sub_kind)
                        if new_val != val:
                            tokens[v][1] = format_number(new_val)
                else:
                    factor_key = SIMPLE_ATTR_SCALING.get((parent, text))
                    if factor_key and v < end and tokens[v][0] == "NUMBER":
                        val = float(tokens[v][1])
                        new_val = scaler.apply(val, factor_key)
                        tokens[v][1] = format_number(new_val)
                # Advance past SEMI
                s = v + 1
                while s < end and tokens[s][0] != "SEMI":
                    s += 1
                i = s + 1
                continue

            else:
                i += 1
                continue
        else:
            i += 1


def build_header(src_path, factors_cfg, factors_path, corner):
    """Banner injected at the top of every derived .lib."""
    today = datetime.date.today().isoformat()
    src = corner["source"]
    tgt = corner["target"]
    return (
        "/*\n"
        " * ============================================================\n"
        " * OpenCell-7 — derived 7nm-class Liberty file\n"
        " * ============================================================\n"
        f" *   Generated:        {today}\n"
        f" *   Source library:   {os.path.basename(src_path)}\n"
        f" *                     (SkyWater PDK sky130_fd_sc_hd, Apache-2.0)\n"
        f" *   Scaling factors:  {os.path.basename(factors_path)} v{factors_cfg.get('version','?')}\n"
        f" *   Source corner:    {src['name']}  ({src['voltage']}V, {src['temperature']}C)\n"
        f" *   Target corner:    {tgt['name']}  ({tgt['voltage']}V, {tgt['temperature']}C)\n"
        f" *   Methodology:      docs/METHODOLOGY.md\n"
        f" *   Sources:          docs/SOURCES.md\n"
        " *\n"
        " * NOTE: This is a SYNTHETIC library derived by statistical\n"
        " * scaling of sky130 silicon-validated numbers. It is dimensionally\n"
        " * consistent with published 7nm scaling but is NOT foundry-correlated\n"
        " * and NOT silicon-validated at 7nm. Do not use for tape-out.\n"
        " *\n"
        " * Scaling factors applied (from scale_factors.json):\n"
        + "\n".join(
            f" *   {k:20s}  {v.get('operation','?'):8s} {v.get('value','?')}"
            for k, v in factors_cfg["factors"].items()
            if isinstance(v, dict) and "operation" in v
        )
        + "\n"
        " *\n"
        " * Upstream attribution (from sky130_fd_sc_hd):\n"
        " *   Copyright 2020 The SkyWater PDK Authors\n"
        " *   Licensed under the Apache License, Version 2.0\n"
        " *   https://github.com/google/skywater-pdk-libs-sky130_fd_sc_hd\n"
        " * ============================================================\n"
        " */\n\n"
    )


def rename_library(text, src_lib_name, dst_lib_name, src_oc_name, dst_oc_name):
    """Post-pass rename of the library and operating_conditions names."""
    # Whole-word library declaration. We accept either bare or quoted name.
    text = re.sub(
        r"\blibrary\s*\(\s*\"?" + re.escape(src_lib_name) + r"\"?\s*\)",
        f"library ({dst_lib_name})",
        text,
    )
    # operating_conditions ("name") or operating_conditions(name)
    text = re.sub(
        r"\boperating_conditions\s*\(\s*\"?" + re.escape(src_oc_name) + r"\"?\s*\)",
        f'operating_conditions ("{dst_oc_name}")',
        text,
    )
    # default_operating_conditions : name ;
    text = re.sub(
        r"(default_operating_conditions\s*:\s*)" + re.escape(src_oc_name) + r"\s*;",
        rf"\1{dst_oc_name} ;",
        text,
    )
    return text


def detect_src_names(text):
    """Extract the source library name and the canonical TT operating-condition name."""
    m = re.search(r"\blibrary\s*\(\s*\"?([A-Za-z0-9_]+)\"?\s*\)", text)
    src_lib = m.group(1) if m else None
    m = re.search(r"\boperating_conditions\s*\(\s*\"?([A-Za-z0-9_]+)\"?\s*\)", text)
    src_oc = m.group(1) if m else None
    return src_lib, src_oc


def main():
    ap = argparse.ArgumentParser(description="Scale a sky130 Liberty file to 7nm-class.")
    ap.add_argument("--in", dest="src", required=True, help="path to sky130 .lib")
    ap.add_argument("--out", dest="dst", required=True, help="path to output derived .lib")
    ap.add_argument(
        "--corner",
        default="tt",
        help="corner key from scale_factors.json corners {tt, ss, ...}; default tt",
    )
    ap.add_argument(
        "--factors",
        default=str(Path(__file__).parent / "scale_factors.json"),
        help="path to scale_factors.json",
    )
    args = ap.parse_args()

    print(f"==> Loading factors: {args.factors}")
    with open(args.factors) as f:
        cfg = json.load(f)
    scaler = Scaler(cfg, args.corner)
    corner = scaler.corner
    print(
        f"    corner:            {args.corner}  "
        f"({corner['source']['name']} -> {corner['target']['name']})"
    )

    print(f"==> Reading source: {args.src} ({os.path.getsize(args.src) / 1e6:.1f} MB)")
    with open(args.src) as f:
        source_text = f.read()

    src_lib_name, src_oc_name = detect_src_names(source_text)
    print(f"    source library:    {src_lib_name}")
    print(f"    source op-cond:    {src_oc_name}")

    print("==> Tokenizing")
    tokens = tokenize(source_text)
    print(f"    tokens:            {len(tokens):,}")

    print("==> Walking + rewriting")
    walk_group(tokens, 0, len(tokens), scaler, group_stack=[], var_overrides=None)

    print("==> Reassembling")
    out_text = "".join(t[1] for t in tokens)

    dst_lib_name = corner["target"]["library_name"]
    dst_oc_name = corner["target"]["name"]
    if src_lib_name:
        out_text = rename_library(
            out_text,
            src_lib_name,
            dst_lib_name,
            src_oc_name or corner["source"]["name"],
            dst_oc_name,
        )

    print("==> Injecting header")
    header = build_header(args.src, cfg, args.factors, corner)
    lib_match = re.search(r"\blibrary\s*\(", out_text)
    if lib_match:
        idx = lib_match.start()
        out_text = out_text[:idx] + header + out_text[idx:]
    else:
        out_text = header + out_text

    os.makedirs(os.path.dirname(os.path.abspath(args.dst)) or ".", exist_ok=True)
    with open(args.dst, "w") as f:
        f.write(out_text)

    print(f"==> Wrote: {args.dst} ({os.path.getsize(args.dst) / 1e6:.1f} MB)")


if __name__ == "__main__":
    main()
