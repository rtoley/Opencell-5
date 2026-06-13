#!/usr/bin/env python3
"""validate.py — synth+STA a reference design on sky130 + the scaled lib for
each corner (TT and SS), report fmax / area / ratios.

Usage:
  scaling/validate.py [--rtl reference/counter.v] [--top counter]
                      [--build-root build]

fmax inference: rather than bisecting clock periods, we run STA once at a
generous period P0 and read the worst reg-to-reg setup slack S. The minimum
achievable period is approximately (P0 - S/(1 - U)) where U is the relative
clock uncertainty. With U=0.005 (our SDC), the correction is negligible:
P_min ~= P0 - S.

For each corner we time both the upstream sky130 lib and the derived
opencell7 lib, compare the ratios, and check against the published 7nm/130nm
scaling windows from scale_factors.json. Process derate is composed onto
delays in the scaled libs but is NOT visible in fmax(sky130) — so the
fmax(scaled)/fmax(sky130) ratio target is the SCALER's effective delay
factor: divide(delay_factor) * multiply(process_derate). We compute the
effective range automatically below.
"""

import argparse
import json
import os
import re
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent


def run(cmd, env=None, cwd=None, log_path=None, check=True):
    if env is not None:
        merged = os.environ.copy()
        merged.update(env)
        env = merged
    print(f"    $ {' '.join(cmd)}")
    proc = subprocess.run(cmd, env=env, cwd=cwd, check=False, capture_output=True, text=True)
    if log_path:
        Path(log_path).parent.mkdir(parents=True, exist_ok=True)
        with open(log_path, "w") as f:
            f.write(proc.stdout)
            if proc.stderr:
                f.write("\n--- STDERR ---\n")
                f.write(proc.stderr)
    if check and proc.returncode != 0:
        print(proc.stdout[-2000:])
        print("STDERR:", proc.stderr[-2000:])
        raise SystemExit(f"command failed: {' '.join(cmd)}")
    return proc.stdout + ("\n" + proc.stderr if proc.stderr else "")


def parse_area_from_yosys(yosys_log_text):
    m = re.search(r"Chip area for (?:top )?module.*?:\s*([\d.]+)", yosys_log_text)
    if m:
        return float(m.group(1))
    m = re.search(r"Chip area .*?:\s*([\d.]+)", yosys_log_text)
    if m:
        return float(m.group(1))
    return None


def parse_cell_count_from_yosys(yosys_log_text):
    m = re.search(r"^\s*Number of cells:\s*(\d+)", yosys_log_text, re.MULTILINE)
    if m:
        return int(m.group(1))
    section = re.search(r"=== \\?[\w]+ ===.*?Chip area", yosys_log_text, re.DOTALL)
    if not section:
        return None
    total = 0
    for line in section.group(0).splitlines():
        m = re.match(r"\s*(\d+)\s+[\d.]+\s+sky130_fd_sc_hd__", line)
        if m:
            total += int(m.group(1))
    return total or None


def parse_worst_setup_slack(sta_log_text):
    section = re.search(r"reg-to-reg only =+\s*(.*?)(?:={5,}|\Z)", sta_log_text, re.DOTALL)
    if section is None:
        return None
    text = section.group(1)
    matches = re.findall(r"([-\d.]+)\s+slack \((MET|VIOLATED)\)", text)
    if not matches:
        return None
    return float(matches[-1][0])


def parse_critical_path(sta_log_text):
    section = re.search(r"reg-to-reg only =+\s*(.*?)(?:={5,}|\Z)", sta_log_text, re.DOTALL)
    if section is None:
        return "(no reg-to-reg section found)"
    text = section.group(1)
    sp = re.search(r"Startpoint:\s*(\S+)", text)
    ep = re.search(r"Endpoint:\s*(\S+)", text)
    return f"{sp.group(1) if sp else '?'} -> {ep.group(1) if ep else '?'}"


def synth_and_sta(lib_path, rtl_path, top, build_root, p0_ns):
    build = build_root / Path(lib_path).stem
    build.mkdir(parents=True, exist_ok=True)
    yosys_log = build / "yosys.log"
    sta_log = build / "sta.log"

    env_synth = {"LIB": str(lib_path), "RTL": str(rtl_path), "TOP": top, "BUILD": str(build)}
    print(f"--> [{Path(lib_path).name}] synthesis")
    run(
        ["yosys", "-l", str(yosys_log), "-c", "flow/synth.tcl"],
        env=env_synth, cwd=REPO, log_path=build / "yosys.stdout",
    )
    log_text = open(yosys_log).read()
    area = parse_area_from_yosys(log_text)
    cell_count = parse_cell_count_from_yosys(log_text)

    env_sta = {
        "LIB": str(lib_path), "TOP": top, "BUILD": str(build),
        "SDC": str(REPO / "flow" / "constraints.sdc"), "CLK_PERIOD_NS": str(p0_ns),
    }
    print(f"--> [{Path(lib_path).name}] STA @ P0 = {p0_ns} ns")
    run(
        ["sta", "-no_init", "-no_splash", "-exit", "flow/sta.tcl"],
        env=env_sta, cwd=REPO, log_path=sta_log,
    )
    sta_text = open(sta_log).read()
    slack = parse_worst_setup_slack(sta_text)
    crit = parse_critical_path(sta_text)
    if slack is None:
        raise SystemExit(f"could not parse setup slack from {sta_log}")
    p_min = p0_ns - slack / 0.995
    fmax_mhz = 1000.0 / p_min if p_min > 0 else float("inf")
    print(f"    area:             {area} um^2 ({cell_count} cells)")
    print(f"    setup slack (P0): {slack:.4f} ns")
    print(f"    min period:       {p_min:.4f} ns")
    print(f"    fmax:             {fmax_mhz:.1f} MHz")
    print(f"    critical path:    {crit}")
    return {
        "lib": str(lib_path), "area_um2": area, "cell_count": cell_count,
        "slack_at_p0_ns": slack, "p0_ns": p0_ns, "p_min_ns": p_min,
        "fmax_mhz": fmax_mhz, "critical_path": crit, "build_dir": str(build),
    }


def effective_delay_range(cfg):
    """Effective scaler delay ratio = delay.value * process_derate.value.

    Each side of the range scales with the corresponding side of the published
    delay range; derate widens it.
    """
    df = cfg["factors"]["delay"]
    deriv = cfg["factors"].get("process_derate", {"value": 1.0, "range": [1.0, 1.0]})
    derate_lo, derate_hi = deriv["range"]
    lo, hi = df["range"]
    # Effective sky/scaled ratio = sky_value * (delay.value * derate.value) / sky_value.
    # So scaled is slower by (delay/derate) relative to a delay-only scaling.
    # fmax(scaled)/fmax(sky) = 1 / (delay / derate) = delay / derate.
    eff_lo = lo / derate_hi
    eff_hi = hi / derate_lo
    return (eff_lo, eff_hi)


def within_tolerance(ratio, target_range, tol=0.30):
    lo = target_range[0] * (1 - tol)
    hi = target_range[1] * (1 + tol)
    return lo <= ratio <= hi, lo, hi


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--rtl", default="reference/counter.v")
    ap.add_argument("--top", default="counter")
    ap.add_argument("--build-root", default="build")
    ap.add_argument("--sky130-p0-ns", type=float, default=10.0)
    ap.add_argument("--scaled-p0-ns", type=float, default=1.5)
    ap.add_argument("--factors", default="scaling/scale_factors.json")
    args = ap.parse_args()

    os.chdir(REPO)
    cfg = json.load(open(args.factors))

    # The four libs to compare, derived from cfg["corners"].
    pairs = []
    for cname, c in cfg["corners"].items():
        sky_path = Path("derived/sky130_libs") / c["source"]["lib_filename"]
        sc_path = Path("derived") / c["target"]["lib_filename"]
        if not sky_path.exists():
            raise SystemExit(f"missing sky130 lib for corner {cname}: {sky_path}  (run 'make fetch')")
        if not sc_path.exists():
            raise SystemExit(f"missing scaled lib for corner {cname}: {sc_path}  (run 'make scale')")
        pairs.append((cname, c, sky_path, sc_path))

    build_root = Path(args.build_root)
    build_root.mkdir(parents=True, exist_ok=True)

    runs = {}
    for cname, c, sky_path, sc_path in pairs:
        print("=" * 64)
        print(f"Corner: {cname.upper()}  ({c['source']['name']} -> {c['target']['name']})")
        print("=" * 64)
        sky_p0 = args.sky130_p0_ns if cname == "tt" else args.sky130_p0_ns * 1.5
        sc_p0 = args.scaled_p0_ns if cname == "tt" else args.scaled_p0_ns * 1.5
        r_sky = synth_and_sta(str(sky_path), args.rtl, args.top, build_root, sky_p0)
        print()
        r_sc = synth_and_sta(str(sc_path), args.rtl, args.top, build_root, sc_p0)
        print()
        runs[cname] = {"sky130": r_sky, "scaled": r_sc}

    # Compute ratios per corner
    target_area = cfg["factors"]["area"]
    eff_fmax_lo, eff_fmax_hi = effective_delay_range(cfg)

    rows = []
    for cname, c in cfg["corners"].items():
        r_sky = runs[cname]["sky130"]; r_sc = runs[cname]["scaled"]
        fmax_ratio = r_sc["fmax_mhz"] / r_sky["fmax_mhz"]
        area_ratio = r_sky["area_um2"] / r_sc["area_um2"]
        fmax_ok, fmax_lo, fmax_hi = within_tolerance(fmax_ratio, [eff_fmax_lo, eff_fmax_hi])
        area_ok, area_lo, area_hi = within_tolerance(area_ratio, target_area["range"])
        rows.append({
            "corner": cname,
            "sky130_fmax_mhz": r_sky["fmax_mhz"],
            "scaled_fmax_mhz": r_sc["fmax_mhz"],
            "sky130_area_um2": r_sky["area_um2"],
            "scaled_area_um2": r_sc["area_um2"],
            "fmax_ratio": fmax_ratio,
            "area_ratio": area_ratio,
            "fmax_pass": fmax_ok,
            "area_pass": area_ok,
            "fmax_window": [fmax_lo, fmax_hi],
            "area_window": [area_lo, area_hi],
        })

    print("=" * 64)
    print("Summary")
    print("=" * 64)
    print()
    print(f"  Effective scaler delay window (= delay / process_derate):")
    delay = cfg["factors"]["delay"]
    derate = cfg["factors"]["process_derate"]
    print(
        f"    delay {delay['range']}  *  derate {derate['range']} (multiply) "
        f"->  fmax-ratio target [{eff_fmax_lo:.2f}, {eff_fmax_hi:.2f}]"
    )
    print(f"  Tolerance band (+-30%):  [{eff_fmax_lo*0.7:.2f}, {eff_fmax_hi*1.3:.2f}]")
    print()
    print(
        f"  {'corner':6s}  {'sky130 fmax':>12s}  {'scaled fmax':>12s}  "
        f"{'sky area':>10s}  {'scaled area':>11s}  {'fmax x':>8s}  {'area x':>8s}  result"
    )
    print("  " + "-" * 100)
    for r in rows:
        fmax_tag = "PASS" if r["fmax_pass"] else "FAIL"
        area_tag = "PASS" if r["area_pass"] else "FAIL"
        print(
            f"  {r['corner']:6s}  {r['sky130_fmax_mhz']:>12.1f}  {r['scaled_fmax_mhz']:>12.1f}  "
            f"{r['sky130_area_um2']:>10.3f}  {r['scaled_area_um2']:>11.4f}  "
            f"{r['fmax_ratio']:>7.2f}x  {r['area_ratio']:>7.2f}x  "
            f"fmax {fmax_tag} / area {area_tag}"
        )
    print()
    print(f"  Area target window (+-30%): {target_area['range']}")
    print()
    all_pass = all(r["fmax_pass"] and r["area_pass"] for r in rows)

    out = {
        "factors_version": cfg["version"],
        "effective_fmax_range": [eff_fmax_lo, eff_fmax_hi],
        "target_area_range": target_area["range"],
        "rows": rows,
        "runs": runs,
    }
    report_path = build_root / "validate_report.json"
    with open(report_path, "w") as f:
        json.dump(out, f, indent=2)
    print(f"  report: {report_path}")
    sys.exit(0 if all_pass else 1)


if __name__ == "__main__":
    main()
