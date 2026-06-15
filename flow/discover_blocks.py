#!/usr/bin/env python3
"""discover_blocks.py — autonomous hierarchical-block discovery for the flow.

Point it at RTL and it answers two questions, with no hand-written block list:

  1. Does this design need hierarchy at all?   (the "size gate")
  2. If so, which sub-modules should be hardened bottom-up as blocks?

It runs a cheap yosys probe (read -> hierarchy -> proc/opt -> stat, NO flatten),
reconstructs the module tree with per-module sizes and submodule instance counts,
then selects blocks by three autonomous criteria:

  * REPLICATION  — a module instantiated many times (lanes, PEs, cores, sboxes).
                   Harden it ONCE, reuse the abstract N times. Biggest win.
  * SIZE BAND    — modules big enough to matter, small enough to P&R cleanly.
  * (boundary/interface quality is reported to help the budgeting step; a clean
     registered boundary is preferred but not required to flag a block.)

Output: a human report + a JSON plan (--json) + optional ORFS BLOCKS scaffolding
(--emit-config), ready to feed the bottom-up build (generate_abstract -> macro).

Usage:
  flow/discover_blocks.py --top aes_cipher_top designs/src/aes/*.v
  flow/discover_blocks.py --design designs/opencell7/aes        # read its config.mk
  flow/discover_blocks.py --top X a.v b.v --json plan.json --emit-config out_dir/

Why these defaults: the probe is RTL-level (fast, seconds). Sizes are relative
RTLIL-op counts — enough to rank blocks and find replication. Pass --synth for a
generic-gate pass when you need absolute gate counts for the size gate.
"""
from __future__ import annotations
import argparse, json, os, re, subprocess, sys, shlex
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
ORFS_IMAGE = os.environ.get("ORFS_IMAGE", "openroad/orfs:latest")

# --- autonomous thresholds (override via CLI) ----------------------------------
DEFAULTS = dict(
    flat_max=40000,   # top size (cells) above which hierarchy is recommended
    block_min=200,    # below this a block is too small to bother hardening
    block_max=150000, # above this a block is itself too big -> descend into it
    replicate_min=4,  # instantiated >= this many times -> harden once, reuse
)


def run_yosys_probe(top: str, files: list[str], do_synth: bool) -> str:
    """Run the yosys hierarchy/stat probe and return its log text."""
    rd = " ".join(shlex.quote(f) for f in files)
    steps = [f"read_verilog {rd}", f"hierarchy -check -top {top}", "proc", "opt"]
    if do_synth:
        steps += ["techmap", "opt"]   # generic gates, hierarchy preserved
    steps.append("stat")
    script = "; ".join(steps)

    # Prefer a local yosys; else run inside the ORFS container (repo mounted RO).
    if _have("yosys"):
        cmd = ["yosys", "-p", script]
        cwd = str(REPO)
    else:
        cmd = ["docker", "run", "--rm", "-v", f"{REPO}:/work:ro", "-w", "/work",
               ORFS_IMAGE, "yosys", "-p", script]
        cwd = None
    p = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True)
    out = p.stdout + p.stderr
    if "End of script" not in out:
        sys.exit(f"yosys probe failed:\n{out[-2000:]}")
    return out


def _have(exe: str) -> bool:
    return subprocess.run(["bash", "-lc", f"command -v {exe}"],
                          capture_output=True).returncode == 0


def parse_stat(log: str) -> dict:
    """Parse `stat` (no-flatten) into {module: {cells, subs:{name:count}}}."""
    mods: dict = {}
    cur = None
    in_subs = False
    for line in log.splitlines():
        m = re.match(r"^=== (\S+) ===", line)
        if m:
            name = m.group(1)
            if name == "design":           # "=== design hierarchy ===" -> stop
                cur = None
                continue
            cur = name.lstrip("\\")
            mods[cur] = {"cells": 0, "subs": {}}
            in_subs = False
            continue
        if cur is None:
            continue
        cm = re.match(r"^\s+(\d+)\s+cells\s*$", line)
        if cm:
            mods[cur]["cells"] = int(cm.group(1))
        if re.match(r"^\s+\d+\s+submodules\s*$", line):
            in_subs = True
            continue
        if in_subs:
            sm = re.match(r"^\s+(\d+)\s+(\S+)\s*$", line)
            if sm and not sm.group(2)[0].isdigit():
                mods[cur]["subs"][sm.group(2).lstrip("\\")] = int(sm.group(1))
            else:
                in_subs = False
    return mods


def total_instances(top: str, mods: dict) -> dict:
    """Total instance count of each module type across the whole design."""
    counts: dict = {top: 1}
    # iterate to a fixed point over the DAG (RTL hierarchies are acyclic)
    for _ in range(len(mods) + 2):
        for name, info in mods.items():
            n = counts.get(name, 0)
            if not n:
                continue
            for sub, c in info["subs"].items():
                counts[sub] = max(counts.get(sub, 0), 0)
        # recompute additively
        fresh = {top: 1}
        stack = [top]
        seen = set()
        acc: dict = {}
        def walk(mod, mult):
            for sub, c in mods.get(mod, {}).get("subs", {}).items():
                acc[sub] = acc.get(sub, 0) + mult * c
                walk(sub, mult * c)
        walk(top, 1)
        counts = {top: 1, **acc}
        break
    return counts


def recursive_size(name: str, mods: dict, memo: dict | None = None) -> int:
    """Cells in a module including all submodule instances (one instance)."""
    memo = memo if memo is not None else {}
    if name in memo:
        return memo[name]
    info = mods.get(name)
    if not info:
        return 0
    size = info["cells"]
    for sub, c in info["subs"].items():
        size += c * recursive_size(sub, mods, memo)
    memo[name] = size
    return size


def discover(top: str, mods: dict, th: dict) -> dict:
    insts = total_instances(top, mods)
    memo: dict = {}
    sizes = {m: recursive_size(m, mods, memo) for m in mods}
    top_size = sizes.get(top, 0)

    blocks = []
    for name, info in mods.items():
        if name == top:
            continue
        n = insts.get(name, 0)
        sz = sizes.get(name, 0)
        # Replication is judged on COUNT, not size: a module used many times is a
        # reuse win even when its pre-abc cell estimate is tiny (combinational
        # lookup logic like an sbox stays a compact $pmux until abc explodes it).
        # Skip only pure-wrapper modules (no logic of their own).
        is_repl = n >= th["replicate_min"] and sz >= 1
        is_band = th["block_min"] <= sz <= th["block_max"]
        if not (is_repl or is_band):
            continue
        reason = []
        if is_repl:
            reason.append(f"replicated x{n}")
        if is_band:
            reason.append("size-band")
        # flat cells this block accounts for vs. hardening one copy
        flat_cells = n * sz
        blocks.append(dict(module=name, instances=n, size_cells=sz,
                           flat_cells=flat_cells, reasons=reason))
    # rank: replicated-and-large first
    blocks.sort(key=lambda b: (-b["instances"] * b["size_cells"]))
    return dict(top=top, top_size_cells=top_size,
                needs_hierarchy=top_size > th["flat_max"],
                flat_threshold=th["flat_max"], blocks=blocks)


def report(plan: dict, th: dict) -> str:
    L = []
    L.append(f"# block-discovery plan for {plan['top']}")
    L.append("")
    gate = "ABOVE" if plan["needs_hierarchy"] else "below"
    L.append(f"top size ~= {plan['top_size_cells']} cells (RTL-op estimate); "
             f"{gate} flat threshold ({plan['flat_threshold']})")
    L.append("  -> " + ("HIERARCHY recommended" if plan["needs_hierarchy"]
                        else "flat flow OK (blocks still usable for reuse)"))
    L.append("")
    if not plan["blocks"]:
        L.append("no block candidates found (no replication, nothing in size band)")
        return "\n".join(L)
    L.append("discovered blocks (harden bottom-up, then consume as macros):")
    L.append(f"  {'module':28} {'inst':>5} {'cells/blk*':>10}  reasons")
    L.append("  " + "-" * 64)
    reuse_saved_runs = 0
    for b in plan["blocks"]:
        if b["instances"] >= th["replicate_min"]:
            reuse_saved_runs += b["instances"] - 1
        L.append(f"  {b['module']:28} {b['instances']:5} {b['size_cells']:10}  "
                 f"{', '.join(b['reasons'])}")
    L.append("")
    if reuse_saved_runs:
        L.append(f"reuse win: replicated blocks are hardened ONCE and reused -> "
                 f"{reuse_saved_runs} fewer block P&R runs than flat.")
    L.append("* cells/blk is a PRE-ABC estimate; combinational lookup logic "
             "(e.g. sboxes) is under-counted until final tech-map. Use it to rank,"
             " not to budget area. Pass --synth for generic-gate counts.")
    return "\n".join(L)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--top", help="top module name")
    ap.add_argument("files", nargs="*", help="verilog files")
    ap.add_argument("--design", help="ORFS design dir (reads config.mk for top+files)")
    ap.add_argument("--synth", action="store_true",
                    help="generic-gate pass for absolute sizes (slower)")
    ap.add_argument("--json", help="write JSON plan to this path")
    for k, v in DEFAULTS.items():
        ap.add_argument(f"--{k}", type=int, default=v)
    a = ap.parse_args()

    top, files = a.top, list(a.files)
    if a.design:
        cfg = Path(a.design) / "config.mk"
        txt = cfg.read_text()
        if not top:
            mt = re.search(r"DESIGN_NAME\s*[:?]?=\s*(\S+)", txt)
            top = mt.group(1) if mt else None
        vf = re.search(r"VERILOG_FILES\s*[:?]?=\s*(.+)", txt)
        if vf and not files:
            raw = vf.group(1).replace("$(DESIGN_HOME)", str(REPO / "designs"))
            files = [raw.strip()]
    if not top or not files:
        ap.error("need --top and verilog files (or --design with both in config.mk)")

    th = {k: getattr(a, k) for k in DEFAULTS}
    log = run_yosys_probe(top, files, a.synth)
    mods = parse_stat(log)
    plan = discover(top, mods, th)
    print(report(plan, th))
    if a.json:
        Path(a.json).write_text(json.dumps(plan, indent=2))
        print(f"\nwrote {a.json}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
