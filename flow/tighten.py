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

Importable: tighten(platform, design, ...) -> dict drives one converger and
returns structured results so a batch driver can consume data, not stdout.

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
    """SDC create_clock period is in the lib time unit: asap7=ps, the sky130-
    derived opencell platforms (opencell7, opencell5, …) are all ns. Don't
    hardcode a single opencell name — any non-asap7 platform is ns."""
    return 1000.0 if platform == "asap7" else 1.0


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
    """Return (achieved_period_ns, fmax_mhz) from the CTS report."""
    rpts = list((REPO / "build" / f"orfs_{platform}_{design}").glob(
        "reports/*/*/base/4_cts_final.rpt"))
    if not rpts:
        return None
    t = rpts[0].read_text()
    m = re.search(r"period_min\s*=\s*([\d.]+)\s+fmax\s*=\s*([\d.]+)", t)
    if not m:
        return None
    # period_min is printed in the lib time unit -> normalize to ns. asap7's lib
    # is in ps (÷1000); the sky130-derived opencell platforms (opencell7,
    # opencell5, …) are all in ns. Don't hardcode a single platform name.
    period_ns = float(m.group(1)) / (1000.0 if platform == "asap7" else 1.0)
    fmax_mhz = float(m.group(2))
    return period_ns, fmax_mhz


def tighten(platform: str, design: str, start_ns: float | None = None,
            tol: float = 0.04, iters: int = 4, step: float = 0.04,
            patience: int = 0, emit=print) -> dict:
    """Converge (platform, design) to its true fmax. Returns a result dict.

    The achieved period TRACKS the clock target downward (loose target -> lazy
    abc/place leave the critical path long), so it is NOT enough to re-target the
    achieved value: when the achieved meets the target with slack ~= 0, that is a
    FALSE fixpoint at the target, not the real floor (observed on picorv32, which
    parked at the 500ps probe while its true path was ~485ps). So we always push
    the next target a `step` BELOW the best floor seen, keeping optimization
    pressure on, and converge only when `patience` consecutive tightening steps
    fail to improve the floor. The reported fmax is the best period actually
    DEMONSTRATED -- never an un-achieved target.

    Raises RuntimeError on a failed probe/iteration so a batch driver can record
    the failure and keep going instead of killing the whole sweep.
    """
    sdc = find_sdc(platform, design)
    target = start_ns
    history: list[dict] = []

    if target is None:
        # one loose probe to learn roughly where it lands, then tighten
        set_period(sdc, 0.5, platform); clean(platform, design)
        run_cts(platform, design)
        r = read_achieved_ns(platform, design)
        if not r:
            raise RuntimeError(f"{platform}/{design}: loose probe failed "
                               f"(see build/tighten_{platform}_{design}.log)")
        target = r[0]
        emit(f"[probe] {platform}/{design}: loose-achieved {r[0]*1000:.0f} ps "
             f"({r[1]:.0f} MHz) -> tighten from there")

    best_p = None        # best (smallest) achieved period seen, in ns
    best_f = 0.0         # fmax at best_p
    converged = False
    stall = 0
    used = 0
    for i in range(iters):
        used = i + 1
        set_period(sdc, target, platform); clean(platform, design)
        run_cts(platform, design)
        r = read_achieved_ns(platform, design)
        if not r:
            raise RuntimeError(f"{platform}/{design} iter {i}: run failed "
                               f"(see build/tighten_{platform}_{design}.log)")
        ach_ns, fmax = r
        history.append({"iter": i, "target_ps": round(target * 1000, 1),
                        "achieved_ps": round(ach_ns * 1000, 1),
                        "fmax_mhz": round(fmax)})
        emit(f"[iter {i}] target {target*1000:.0f} ps -> achieved "
             f"{ach_ns*1000:.0f} ps  ({fmax:.0f} MHz)")
        improved = best_p is None or ach_ns < best_p * (1 - tol)
        if best_p is None or ach_ns < best_p:
            best_p, best_f = ach_ns, fmax      # track the genuine floor
        if improved:
            stall = 0
        else:
            stall += 1
            if stall > patience:
                converged = True
                emit(f"[converged] {platform}/{design}: fmax {best_f:.0f} MHz "
                     f"@ {best_p*1000:.0f} ps")
                break
        target = best_p * (1 - step)     # push BELOW the floor, never re-use it

    return {"platform": platform, "design": design, "fmax_mhz": round(best_f),
            "period_ps": round(best_p * 1000, 1), "converged": converged,
            "iters_used": used, "history": history}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("platform"); ap.add_argument("design")
    ap.add_argument("--start-ns", type=float, default=None,
                    help="initial target (default: derive from a loose probe)")
    ap.add_argument("--tol", type=float, default=0.04, help="improvement tol (frac)")
    ap.add_argument("--iters", type=int, default=4)
    ap.add_argument("--step", type=float, default=0.04,
                    help="fraction to push target below the best floor each step")
    ap.add_argument("--patience", type=int, default=0,
                    help="non-improving steps tolerated before converging")
    a = ap.parse_args()
    try:
        tighten(a.platform, a.design, a.start_ns, a.tol, a.iters,
                a.step, a.patience)
    except RuntimeError as e:
        sys.exit(str(e))
    return 0


if __name__ == "__main__":
    sys.exit(main())
