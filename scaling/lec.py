#!/usr/bin/env python3
"""lec.py — one-command logical equivalence checking driver.

Takes (lib, rtl, netlist, top) and runs the strongest open-source LEC
engines in order, stopping at the first PROVED. Reports verdict + engine
+ wall time. No simulation, no user lemmas, no properties.

See docs/EQUIVALENCE_AT_SCALE.md for the contract this tool implements.

Stages (run in order, stop at first PROVED):
  1. yosys equiv_simple        — combinational equivalence
  2. abc  cec                  — combinational SAT (alternate engine)
  3. yosys equiv_induct -seq N — small sequential, k-induction
  4. abc  dsec                 — sequential LEC w/ signal correspondence
  5. abc  &equiv               — GIA-based sequential LEC (alt engine)

Usage:
  scaling/lec.py --lib derived/opencell7_tt_0p7v_25c.lib \\
                 --top counter \\
                 --rtl reference/counter.v \\
                 --netlist build/poc/counter/opencell7_tt_0p7v_25c/counter_mapped.v
"""

import argparse
import json
import os
import re
import subprocess
import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent


# ---------------------------------------------------------------------------
# Shared yosys script fragments
# ---------------------------------------------------------------------------

# Normalisation applied to both gold (RTL) and gate (netlist) sides so the
# equiv engines see a uniform representation. See equiv_check.py for the
# full provenance of these passes.
def norm_block():
    return (
        "memory_collect\n"
        "memory_map\n"
        "flatten -wb\n"
        "techmap\n"
        "opt -fast\n"
        "async2sync\n"
    )


def gold_load(rtl_files, top, params):
    return (
        f"read_verilog {' '.join(rtl_files)}\n"
        f"hierarchy -top {top} {params}\n"
        f"prep -top {top}\n"
        + norm_block()
    )


def gate_load(lib, netlist, top):
    return (
        f"read_liberty -wb -ignore_miss_func -ignore_miss_dir "
        f"-ignore_miss_data_latch {lib}\n"
        f"read_verilog {netlist}\n"
        f"hierarchy -top {top}\n"
        f"prep -top {top}\n"
        + norm_block()
    )


# ---------------------------------------------------------------------------
# Process helpers
# ---------------------------------------------------------------------------

def _decode(buf):
    if buf is None:
        return ""
    if isinstance(buf, bytes):
        return buf.decode("utf-8", "replace")
    return buf


def run_cmd(cmd, timeout_s, log_path, script=None):
    """Run a command, capturing output to log_path. Returns (returncode,
    log_text, elapsed_s, timed_out_bool)."""
    start = time.time()
    log_path.parent.mkdir(parents=True, exist_ok=True)
    try:
        proc = subprocess.run(
            cmd, capture_output=True, text=True, timeout=timeout_s, cwd=REPO
        )
        elapsed = time.time() - start
        log = (
            (f"# {' '.join(cmd)}\n"
             f"# script:\n{script}\n# ---\n" if script else f"# {' '.join(cmd)}\n# ---\n")
            + proc.stdout
            + (("\n--- STDERR ---\n" + proc.stderr) if proc.stderr else "")
        )
        log_path.write_text(log)
        return proc.returncode, log, elapsed, False
    except subprocess.TimeoutExpired as e:
        elapsed = time.time() - start
        partial = (
            (f"# {' '.join(cmd)}\n# script:\n{script}\n# ---\n" if script else "")
            + _decode(e.stdout)
            + f"\n--- TIMEOUT after {timeout_s}s ---\n"
            + _decode(e.stderr)
        )
        log_path.write_text(partial)
        return None, partial, elapsed, True


# ---------------------------------------------------------------------------
# Stage 1: yosys equiv_simple (combinational)
# ---------------------------------------------------------------------------

def stage_yosys_equiv_simple(args, build):
    log = build / "stage1_yosys_equiv_simple.log"
    script = (
        gold_load(args.rtl, args.top, args.params)
        + "design -stash gold\n"
        + gate_load(args.lib, args.netlist, args.top)
        + f"design -copy-from gold -as gold {args.top}\n"
        f"equiv_make gold {args.top} equiv\n"
        f"hierarchy -top equiv\n"
        f"clean -purge\n"
        f"equiv_simple\n"
        f"equiv_status -assert\n"
    )
    rc, out, elapsed, timed_out = run_cmd(
        ["yosys", "-p", script], args.timeout_s, log, script=script
    )
    if timed_out:
        return "TIMEOUT", elapsed, log
    if rc == 0 and "Equivalence successfully proven!" in out:
        return "PROVED", elapsed, log
    if rc == 0 and "Found 0 unproven" in out:
        return "PROVED", elapsed, log
    return "INCONCLUSIVE", elapsed, log


# ---------------------------------------------------------------------------
# Stage 3: yosys equiv_induct (sequential, k-induction)
# ---------------------------------------------------------------------------

def stage_yosys_equiv_induct(args, build):
    log = build / "stage3_yosys_equiv_induct.log"
    script = (
        gold_load(args.rtl, args.top, args.params)
        + "design -stash gold\n"
        + gate_load(args.lib, args.netlist, args.top)
        + f"design -copy-from gold -as gold {args.top}\n"
        f"equiv_make gold {args.top} equiv\n"
        f"hierarchy -top equiv\n"
        f"clean -purge\n"
        f"equiv_simple\n"
        f"equiv_induct -seq {args.induct_seq}\n"
        f"equiv_status -assert\n"
    )
    rc, out, elapsed, timed_out = run_cmd(
        ["yosys", "-p", script], args.timeout_s, log, script=script
    )
    if timed_out:
        return "TIMEOUT", elapsed, log
    if rc == 0 and "Equivalence successfully proven!" in out:
        return "PROVED", elapsed, log
    if rc == 0 and "Found 0 unproven" in out:
        return "PROVED", elapsed, log
    return "INCONCLUSIVE", elapsed, log


# ---------------------------------------------------------------------------
# Helpers to emit AIGER files via yosys for the abc-driven stages
# ---------------------------------------------------------------------------

def _parse_subckt_pins(line):
    """Extract pins from a `.subckt CELL pin1=net1 pin2=net2 ...` line."""
    tokens = line.split()[2:]
    pins = {}
    for tok in tokens:
        if "=" in tok:
            k, v = tok.split("=", 1)
            pins[k] = v
    return pins


def _patch_blif_dffs(blif_path):
    """Rewrite yosys's `.subckt $_DFF_*_ / $_SDFF_*_ / $_SDFFE_*_` lines as
    abc-native `.latch` + `.names` (mux) blocks. abc's BLIF reader does not
    know yosys's internal cell-type names; it does understand `.latch`.

    Supported flavors:
      $_DFF_P_          (rising edge, no reset, no enable)
      $_DFF_N_          (falling edge, no reset, no enable)
      $_SDFF_P[PN][01]_ (rising edge, sync reset, polarity P/N, val 0/1)
      $_SDFFE_P[PN][01][PN]_ (rising edge, sync reset, enable, four polarities)

    The rewrite logic per-cell:
      next_d = (enable polarity matches E) ? mux_for_reset(R, D) : Q  (when E)
      .latch next_d Q re C 2

    For SDFFE we model the enable by gating D with Q (hold value when E
    inactive), and the sync reset by selecting a constant per the reset
    value. Truth tables are generated for `.names` blocks per cell.
    """
    text = blif_path.read_text()
    rewritten = []
    changed = 0
    unhandled = set()
    cnt = 0  # for unique aux-wire names

    def emit_dff(pins, edge):
        """Plain DFF: emit a single .latch."""
        return [f".latch {pins['D']} {pins['Q']} {edge} {pins['C']} 2"]

    def emit_sdff(pins, edge, rst_pol, rst_val):
        """SDFF with sync reset. Build aux wire d_with_rst then .latch.
        rst_pol: 'P' (reset active when R=1) or 'N' (active when R=0).
        rst_val: '0' or '1' — value forced into Q during reset.
        """
        nonlocal cnt
        aux = f"__lec_aux_{cnt}__"
        cnt += 1
        # Truth table for d_with_rst = f(R, D)
        # When reset active: d_with_rst = rst_val
        # When reset inactive: d_with_rst = D
        lines = [f".names {pins['R']} {pins['D']} {aux}"]
        if rst_pol == "N" and rst_val == "0":
            lines.append("11 1")  # !R-active means R=0 resets. So R=1 D=1 -> 1, else 0
        elif rst_pol == "N" and rst_val == "1":
            lines += ["0- 1", "11 1"]  # R=0 (reset) -> 1; R=1 D=1 -> 1
        elif rst_pol == "P" and rst_val == "0":
            lines.append("01 1")  # R=0 (inactive) D=1 -> 1
        elif rst_pol == "P" and rst_val == "1":
            lines += ["1- 1", "01 1"]  # R=1 (reset) -> 1; R=0 D=1 -> 1
        lines.append(f".latch {aux} {pins['Q']} {edge} {pins['C']} 2")
        return lines

    def emit_sdffe(pins, edge, rst_pol, rst_val, en_pol):
        """SDFFE with sync reset + enable. Builds:
             d_after_en = enable ? D : Q     (holds Q when disabled)
             d_after_rst = reset_active ? rst_val : d_after_en
             .latch d_after_rst Q ...
        """
        nonlocal cnt
        aux1 = f"__lec_aux_{cnt}__"; cnt += 1   # after enable mux
        aux2 = f"__lec_aux_{cnt}__"; cnt += 1   # after reset mux
        lines = []
        # d_after_en truth table: f(E, D, Q)
        # If enable active: pick D. If enable inactive: pick Q.
        if en_pol == "P":
            # E=1 -> D; E=0 -> Q
            lines.append(f".names {pins['E']} {pins['D']} {pins['Q']} {aux1}")
            lines += ["11- 1", "0-1 1"]  # E=1,D=1 -> 1; E=0,Q=1 -> 1
        else:  # en_pol == "N"
            lines.append(f".names {pins['E']} {pins['D']} {pins['Q']} {aux1}")
            lines += ["01- 1", "1-1 1"]  # E=0,D=1 -> 1; E=1,Q=1 -> 1
        # d_after_rst: apply sync reset to aux1
        lines.append(f".names {pins['R']} {aux1} {aux2}")
        if rst_pol == "N" and rst_val == "0":
            lines.append("11 1")
        elif rst_pol == "N" and rst_val == "1":
            lines += ["0- 1", "11 1"]
        elif rst_pol == "P" and rst_val == "0":
            lines.append("01 1")
        elif rst_pol == "P" and rst_val == "1":
            lines += ["1- 1", "01 1"]
        lines.append(f".latch {aux2} {pins['Q']} {edge} {pins['C']} 2")
        return lines

    sdff_re   = re.compile(r"^\$_SDFF_(P|N)(P|N)([01])_$")
    sdffe_re  = re.compile(r"^\$_SDFFE_(P|N)(P|N)([01])(P|N)_$")
    sdffce_re = re.compile(r"^\$_SDFFCE_(P|N)(P|N)([01])(P|N)_$")
    dff_re    = re.compile(r"^\$_DFF_(P|N)_$")
    dffe_re   = re.compile(r"^\$_DFFE_(P|N)(P|N)_$")

    def emit_dffe(pins, edge, en_pol):
        """DFFE: DFF with enable, no reset. Pins: C, D, Q, E.
        next_d = enable_active ? D : Q (hold)."""
        nonlocal cnt
        aux = f"__lec_aux_{cnt}__"; cnt += 1
        lines = [f".names {pins['E']} {pins['D']} {pins['Q']} {aux}"]
        if en_pol == "P":
            lines += ["11- 1", "0-1 1"]
        else:  # N: enable is active when E=0
            lines += ["01- 1", "1-1 1"]
        lines.append(f".latch {aux} {pins['Q']} {edge} {pins['C']} 2")
        return lines

    def emit_sdffce(pins, edge, rst_pol, rst_val, en_pol):
        """SDFFCE: DFF with sync clear-and-enable. Pins: C, D, Q, R, E.
        Behavior at clock edge:
          if enable active:
            if reset active: q <= rst_val
            else: q <= D
          else: q <= Q (hold)
        """
        nonlocal cnt
        aux = f"__lec_aux_{cnt}__"; cnt += 1
        lines = [f".names {pins['E']} {pins['R']} {pins['D']} {pins['Q']} {aux}"]
        # Build truth table based on polarities. We want next_d=1 when:
        #   enable inactive AND Q=1 (hold)
        #   enable active AND reset active AND rst_val==1
        #   enable active AND reset inactive AND D=1
        # Encode each case as a row. Use - for don't-care.
        en_active_lit = "1" if en_pol == "P" else "0"
        en_inactive_lit = "0" if en_pol == "P" else "1"
        rst_active_lit = "1" if rst_pol == "P" else "0"
        rst_inactive_lit = "0" if rst_pol == "P" else "1"
        # case 1: enable inactive, hold Q
        lines.append(f"{en_inactive_lit}--1 1")
        # case 2: enable active, reset active, rst_val=1
        if rst_val == "1":
            lines.append(f"{en_active_lit}{rst_active_lit}-- 1")
        # case 3: enable active, reset inactive, D=1
        lines.append(f"{en_active_lit}{rst_inactive_lit}1- 1")
        lines.append(f".latch {aux} {pins['Q']} {edge} {pins['C']} 2")
        return lines

    for line in text.splitlines():
        if not line.startswith(".subckt "):
            rewritten.append(line); continue
        cell = line.split()[1]
        pins = _parse_subckt_pins(line)
        m = dff_re.match(cell)
        if m and all(k in pins for k in ("C", "D", "Q")):
            edge = "re" if m.group(1) == "P" else "fe"
            rewritten.extend(emit_dff(pins, edge))
            changed += 1; continue
        m = sdff_re.match(cell)
        if m and all(k in pins for k in ("C", "D", "Q", "R")):
            edge = "re" if m.group(1) == "P" else "fe"
            rewritten.extend(emit_sdff(pins, edge, m.group(2), m.group(3)))
            changed += 1; continue
        m = sdffe_re.match(cell)
        if m and all(k in pins for k in ("C", "D", "Q", "R", "E")):
            edge = "re" if m.group(1) == "P" else "fe"
            rewritten.extend(emit_sdffe(pins, edge, m.group(2), m.group(3), m.group(4)))
            changed += 1; continue
        m = sdffce_re.match(cell)
        if m and all(k in pins for k in ("C", "D", "Q", "R", "E")):
            edge = "re" if m.group(1) == "P" else "fe"
            rewritten.extend(emit_sdffce(pins, edge, m.group(2), m.group(3), m.group(4)))
            changed += 1; continue
        m = dffe_re.match(cell)
        if m and all(k in pins for k in ("C", "D", "Q", "E")):
            edge = "re" if m.group(1) == "P" else "fe"
            rewritten.extend(emit_dffe(pins, edge, m.group(2)))
            changed += 1; continue
        # Unhandled subckt — pass through; abc will fail loudly if it's a FF.
        if cell.startswith("$_"):
            unhandled.add(cell)
        rewritten.append(line)

    if changed or unhandled:
        blif_path.write_text("\n".join(rewritten) + "\n")
    if unhandled:
        # Surface for the caller via a sentinel side-channel: append a comment
        # the caller can grep. abc may still error, which is the right signal.
        with open(blif_path.with_suffix(".blif.unhandled"), "w") as f:
            f.write("\n".join(sorted(unhandled)) + "\n")
    return changed


def _make_aig(args, side, out_aig_path, timeout_s, log):
    """side: 'gold' (RTL) or 'gate' (netlist). Three-step conversion:
      (1) yosys writes BLIF after dffunmap + aigmap normalisation,
      (2) post-process the BLIF to rewrite `.subckt $_DFF_P_ ...` lines as
          `.latch d q re clk 2` (abc's BLIF reader doesn't recognise yosys's
          internal cell-type names),
      (3) abc reads the patched BLIF + strash + writes AIGER.

    Both gold and gate end up as AIG files that all the abc-driven stages
    (cec/dsec/&equiv) can read uniformly."""
    if side == "gold":
        load = gold_load(args.rtl, args.top, args.params)
    else:
        load = gate_load(args.lib, args.netlist, args.top)
    blif_path = out_aig_path.with_suffix(".blif")
    script = (
        load
        + "dffunmap\n"
        + "opt -fast\n"
        + "aigmap\n"
        + "opt -fast\n"
        + f"write_blif {blif_path}\n"
    )
    rc, out, elapsed, timed_out = run_cmd(
        ["yosys", "-p", script], timeout_s, log, script=script
    )
    if timed_out or rc != 0 or not blif_path.exists() or blif_path.stat().st_size == 0:
        return False, elapsed

    # Patch DFF subckts -> .latch
    try:
        n = _patch_blif_dffs(blif_path)
        log.write_text(log.read_text() + f"\n--- BLIF patched: {n} DFF subckts -> .latch ---\n")
    except Exception as e:
        log.write_text(log.read_text() + f"\n--- BLIF patch failed: {e} ---\n")
        return False, elapsed

    # Convert BLIF -> AIG via abc strash
    abc_log = log.with_name(log.stem + "_abc_strash.log")
    abc_cmd = f"read_blif {blif_path}; strash; write_aiger {out_aig_path}"
    rc2, out2, elapsed2, to2 = run_cmd(
        ["yosys-abc", "-c", abc_cmd], timeout_s, abc_log
    )
    if to2 or rc2 != 0:
        return False, elapsed + elapsed2
    if not out_aig_path.exists() or out_aig_path.stat().st_size == 0:
        return False, elapsed + elapsed2
    return True, elapsed + elapsed2


# ---------------------------------------------------------------------------
# Stage 2: abc cec (combinational equivalence)
# ---------------------------------------------------------------------------

def stage_abc_cec(args, build):
    log = build / "stage2_abc_cec.log"
    gold_aig = build / "gold.aig"
    gate_aig = build / "gate.aig"
    aigemit_log = build / "stage2_aigemit.log"

    ok_g, _ = _make_aig(args, "gold", gold_aig, args.timeout_s, aigemit_log)
    if not ok_g:
        return "INCONCLUSIVE", 0.0, log
    ok_n, _ = _make_aig(args, "gate", gate_aig, args.timeout_s, aigemit_log)
    if not ok_n:
        return "INCONCLUSIVE", 0.0, log

    abc_script = f"read {gold_aig}; cec {gate_aig}"
    rc, out, elapsed, timed_out = run_cmd(
        ["yosys-abc", "-c", abc_script], args.timeout_s, log
    )
    if timed_out:
        return "TIMEOUT", elapsed, log
    # abc cec output patterns
    if "Networks are equivalent" in out:
        return "PROVED", elapsed, log
    if "Networks are equivalent after structural hashing" in out:
        return "PROVED", elapsed, log
    if "Networks are NOT EQUIVALENT" in out or "are NOT equivalent" in out:
        return "INCONCLUSIVE", elapsed, log
    return "INCONCLUSIVE", elapsed, log


# ---------------------------------------------------------------------------
# Stage 4: abc dsec (sequential equivalence with auto signal correspondence)
# ---------------------------------------------------------------------------

def stage_abc_dsec(args, build):
    log = build / "stage4_abc_dsec.log"
    gold_aig = build / "gold.aig"
    gate_aig = build / "gate.aig"
    if not gold_aig.exists() or not gate_aig.exists():
        aigemit_log = build / "stage4_aigemit.log"
        ok_g, _ = _make_aig(args, "gold", gold_aig, args.timeout_s, aigemit_log)
        ok_n, _ = _make_aig(args, "gate", gate_aig, args.timeout_s, aigemit_log)
        if not (ok_g and ok_n):
            return "INCONCLUSIVE", 0.0, log

    # -F 20: allow induction depth up to 20 (default 4 is too shallow for CPUs).
    # -T <secs>: total dsec runtime budget; pass most of our outer timeout
    # to dsec's own scheduler so it can rebalance across frames.
    inner_T = max(60, args.timeout_s - 60)
    abc_script = f"read {gold_aig}; dsec -F 20 -T {inner_T} {gate_aig}"
    rc, out, elapsed, timed_out = run_cmd(
        ["yosys-abc", "-c", abc_script], args.timeout_s, log
    )
    if timed_out:
        return "TIMEOUT", elapsed, log
    if "Networks are equivalent" in out:
        return "PROVED", elapsed, log
    if "are equivalent" in out and "NOT" not in out:
        return "PROVED", elapsed, log
    if "NOT EQUIVALENT" in out or "NOT equivalent" in out:
        return "INCONCLUSIVE", elapsed, log
    return "INCONCLUSIVE", elapsed, log


# ---------------------------------------------------------------------------
# Stage 5: abc &equiv (GIA-based sequential LEC)
# ---------------------------------------------------------------------------

def stage_abc_eequiv(args, build):
    log = build / "stage5_abc_eequiv.log"
    gold_aig = build / "gold.aig"
    gate_aig = build / "gate.aig"
    if not gold_aig.exists() or not gate_aig.exists():
        aigemit_log = build / "stage5_aigemit.log"
        ok_g, _ = _make_aig(args, "gold", gold_aig, args.timeout_s, aigemit_log)
        ok_n, _ = _make_aig(args, "gate", gate_aig, args.timeout_s, aigemit_log)
        if not (ok_g and ok_n):
            return "INCONCLUSIVE", 0.0, log

    # &miter -s builds a sequential miter; &equiv2 then runs sequential
    # equivalence with signal correspondence on the GIA representation.
    abc_script = (
        f"&read {gold_aig}; "
        f"&miter -s {gate_aig}; "
        f"&equiv2; "
        f"&ps"
    )
    rc, out, elapsed, timed_out = run_cmd(
        ["yosys-abc", "-c", abc_script], args.timeout_s, log
    )
    if timed_out:
        return "TIMEOUT", elapsed, log
    if "Networks are equivalent" in out:
        return "PROVED", elapsed, log
    if re.search(r"All\s+\d+\s+POs\s+proved\s+equivalent", out):
        return "PROVED", elapsed, log
    if "Miter is equivalent" in out:
        return "PROVED", elapsed, log
    if "NOT equivalent" in out or "Disproved" in out:
        return "INCONCLUSIVE", elapsed, log
    return "INCONCLUSIVE", elapsed, log


# ---------------------------------------------------------------------------
# Driver
# ---------------------------------------------------------------------------

STAGES = [
    ("yosys_equiv_simple", stage_yosys_equiv_simple),
    ("abc_cec",            stage_abc_cec),
    ("yosys_equiv_induct", stage_yosys_equiv_induct),
    ("abc_dsec",           stage_abc_dsec),
    ("abc_eequiv",         stage_abc_eequiv),
]


def main():
    ap = argparse.ArgumentParser(description="One-command LEC driver.")
    ap.add_argument("--lib", required=True, help="path to Liberty file")
    ap.add_argument("--rtl", required=True, nargs="+",
                    help="one or more RTL source files")
    ap.add_argument("--netlist", required=True, help="mapped netlist Verilog")
    ap.add_argument("--top", required=True, help="top module name")
    ap.add_argument("--params", default="",
                    help="extra hierarchy args, e.g. "
                         "'-chparam ENABLE_REGS_DUALPORT 1'")
    ap.add_argument("--timeout-s", type=int, default=300,
                    help="per-stage timeout in seconds (default 300)")
    ap.add_argument("--induct-seq", type=int, default=10,
                    help="equiv_induct -seq depth (default 10)")
    ap.add_argument("--build-dir", default="build/lec",
                    help="output directory for logs + AIG artifacts")
    ap.add_argument("--skip", default="",
                    help="comma-separated stages to skip, e.g. 'abc_cec,abc_dsec'")
    args = ap.parse_args()

    os.chdir(REPO)
    for f in args.rtl + [args.netlist, args.lib]:
        if not Path(f).exists():
            raise SystemExit(f"file not found: {f}")

    build = Path(args.build_dir)
    build.mkdir(parents=True, exist_ok=True)

    skip = {s.strip() for s in args.skip.split(",") if s.strip()}

    print(f"==> LEC: top={args.top}  lib={Path(args.lib).name}")
    print(f"    rtl:     {args.rtl}")
    print(f"    netlist: {args.netlist}")
    print(f"    timeout per stage: {args.timeout_s}s")
    print()

    results = []
    proved_stage = None
    for stage_name, stage_fn in STAGES:
        if stage_name in skip:
            print(f"  [{stage_name}]  SKIPPED")
            results.append({"stage": stage_name, "status": "SKIPPED",
                            "wall_time_s": 0.0, "log": None})
            continue
        print(f"  [{stage_name}]  running (timeout {args.timeout_s}s)...")
        status, elapsed, log = stage_fn(args, build)
        print(f"  [{stage_name}]  {status}  ({elapsed:.1f}s)  log={log.name}")
        results.append({"stage": stage_name, "status": status,
                        "wall_time_s": elapsed, "log": str(log)})
        if status == "PROVED":
            proved_stage = stage_name
            break

    print()
    if proved_stage:
        verdict = "PROVED"
        elapsed = next(r["wall_time_s"] for r in results if r["stage"] == proved_stage)
        print(f"  VERDICT: PROVED via stage={proved_stage}  wall_time={elapsed:.1f}s")
    else:
        verdict = "INCONCLUSIVE"
        print(f"  VERDICT: INCONCLUSIVE — no stage proved equivalence")
        print("  Attempted:")
        for r in results:
            print(f"    - {r['stage']:24s} {r['status']:14s} {r['wall_time_s']:6.1f}s")

    report = {
        "verdict": verdict,
        "engine": proved_stage,
        "top": args.top,
        "lib": str(Path(args.lib).resolve()),
        "rtl": [str(Path(f).resolve()) for f in args.rtl],
        "netlist": str(Path(args.netlist).resolve()),
        "timeout_s_per_stage": args.timeout_s,
        "induct_seq": args.induct_seq,
        "stages": results,
    }
    report_path = build / "lec_report.json"
    report_path.write_text(json.dumps(report, indent=2))
    print(f"  report: {report_path}")

    sys.exit(0 if verdict == "PROVED" else 1)


if __name__ == "__main__":
    main()
