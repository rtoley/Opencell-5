#!/usr/bin/env python3
"""tighten.py — drive a (platform, design) to its true fmax (slack ~= 0).

Why: fmax is only a fair cross-platform comparison when each platform is pushed
to its OWN limit. A loose clock target makes abc lazy (it uses -D=target to set
effort) and lets place/resize coast, UNDERSTATING fmax. Proof: gcd at a loose
500ps target achieved 450ps; at a tight 310ps target it achieved 340ps.

This converges the clock target to the achievable period: set target := achieved,
re-run, repeat until the target stops moving. The fixpoint is the true fmax.

It edits the design's host SDC in place (the tightened value IS the harmonized
constraint we want to keep), cleans the build via the container (host rm -rf
silently fails on root-owned ORFS outputs), runs to the CTS endpoint, and reads
the achieved period.

Usage:
  flow/tighten.py <platform> <design> [--start-ns 0.2] [--tol 0.04] [--iters 4]
"""
from __future__ import annotations
import argparse, re, subprocess, sys, os
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
IMAGE = os.environ.get("ORFS_IMAGE", "openroad/orfs:latest")


def find_sdc(platform: str, design: str) -> Path:
    p = REPO / "designs" / platform / design / "constraint.sdc"
    if p.exists():
        return p
    cands = list((REPO / "designs" / platform / design).glob("*.sdc"))
    if not cands:
        sys.exit(f"no host SDC for {platform}/{design} (image built-in not "
                 f"editable; add a host SDC to harmonize it)")
    return cands[0]


def sdc_unit(platform: str) -> float:
    """SDC create_clock period is in the lib time unit: opencell7=ns, asap7=ps."""
    return 1.0 if platform == "opencell7" else 1000.0


def set_period(sdc: Path, period_ns: float, platform: str) -> None:
    txt = sdc.read_text()
    val = period_ns * sdc_unit(platform)
    vs = f"{val:.4f}".rstrip("0").rstrip(".")
    if re.search(r"^\s*set\s+clk_period\s+", txt, re.M):
        txt = re.sub(r"(^\s*set\s+clk_period\s+)\S+", rf"\g<1>{vs}", txt, 1, re.M)
    elif re.search(r"create_clock[^\n]*-period\s+\S+", txt):
        txt = re.sub(r"(create_clock[^\n]*-period\s+)\S+", rf"\g<1>{vs}", txt, 1)
    else:
        sys.exit(f"{sdc}: no editable clk_period / create_clock -period found")
    sdc.write_text(txt)


def clean(platform: str, design: str) -> None:
    subprocess.run(["docker", "run", "--rm", "-v", f"{REPO}/build:/b", IMAGE,
                    "rm", "-rf", f"/b/orfs_{platform}_{design}"], check=False)


def run_cts(platform: str, design: str) -> None:
    env = {**os.environ, "LEC_CHECK": "0"}
    log = REPO / "build" / f"tighten_{platform}_{design}.log"
    with open(log, "w") as f:
        subprocess.run([str(REPO / "flow" / "run_orfs.sh"), platform, design,
                        "cts"], cwd=REPO, env=env, stdout=f, stderr=subprocess.STDOUT)


def read_achieved_ns(platform: str, design: str) -> tuple[float, float] | None:
    """Return (achieved_period_ns, slack_ns) from the CTS report."""
    rpts = list((REPO / "build" / f"orfs_{platform}_{design}").glob(
        "reports/*/*/base/4_cts_final.rpt"))
    if not rpts:
        return None
    t = rpts[0].read_text()
    m = re.search(r"period_min\s*=\s*([\d.]+)\s+fmax\s*=\s*([\d.]+)", t)
    if not m:
        return None
    # period_min is printed in the lib time unit (opencell7=ns, asap7=ps) -> ns
    period_ns = float(m.group(1)) / (1.0 if platform == "opencell7" else 1000.0)
    fmax_mhz = float(m.group(2))
    return period_ns, fmax_mhz


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("platform"); ap.add_argument("design")
    ap.add_argument("--start-ns", type=float, default=None,
                    help="initial target (default: derive from a loose probe)")
    ap.add_argument("--tol", type=float, default=0.04, help="convergence tol (frac)")
    ap.add_argument("--iters", type=int, default=4)
    a = ap.parse_args()

    sdc = find_sdc(a.platform, a.design)
    target = a.start_ns
    if target is None:
        # one loose probe to learn roughly where it lands, then tighten
        set_period(sdc, 0.5, a.platform); clean(a.platform, a.design)
        run_cts(a.platform, a.design)
        r = read_achieved_ns(a.platform, a.design)
        if not r:
            sys.exit("probe failed")
        target = r[0]
        print(f"[probe] {a.platform}/{a.design}: loose-achieved {r[0]*1000:.0f} ps "
              f"({r[1]:.0f} MHz) -> tighten from there")

    last = None
    for i in range(a.iters):
        set_period(sdc, target, a.platform); clean(a.platform, a.design)
        run_cts(a.platform, a.design)
        r = read_achieved_ns(a.platform, a.design)
        if not r:
            sys.exit(f"iter {i}: run failed (see build/tighten_*.log)")
        ach_ns, fmax = r
        print(f"[iter {i}] target {target*1000:.0f} ps -> achieved "
              f"{ach_ns*1000:.0f} ps  ({fmax:.0f} MHz)")
        if last is not None and abs(ach_ns - last) / last < a.tol:
            print(f"[converged] {a.platform}/{a.design}: fmax {fmax:.0f} MHz "
                  f"@ {ach_ns*1000:.0f} ps")
            break
        last = ach_ns
        target = ach_ns      # set target := achieved, push again
    return 0


if __name__ == "__main__":
    sys.exit(main())
