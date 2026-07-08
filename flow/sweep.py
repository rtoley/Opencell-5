#!/usr/bin/env python3
"""sweep.py — autonomous fmax-harmonization sweep over (platform, design) pairs.

This is the committed, reproducible replacement for the ad-hoc shell loop that
produced the d-sweep table. It drives flow/tighten.py over a design set, writes
a machine-readable CSV + a markdown summary (the result artifact), and can
ASSERT the run against a reference and/or its own repeat (the match check) so
"the flow and the results both match" is verified by the tool, not by eye.

Two validation modes the opencell-5 migration depends on:

  faithfulness  --reference <csv>   each design's fmax must match the reference
                                    within --match-tol (proves automated flow ==
                                    the manual flow on a KNOWN design)
  reproducibility  --repeat 2       each design is run N times; the runs must
                                    agree within --match-tol (proves the flow is
                                    deterministic on an UNSEEN design)

Exit code is non-zero if any run fails or any assertion fails, so it is safe to
gate CI / a migration on it.

Usage:
  flow/sweep.py --designs d8 --reference results/reference_dsweep.csv
  flow/sweep.py --designs picorv32 --repeat 2
  flow/sweep.py --designs d8 d16 d32 d48 --platforms opencell7 asap7
"""
from __future__ import annotations
import argparse, csv, json, sys, time
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "flow"))
import tighten as T  # noqa: E402


def load_reference(path: Path) -> dict[tuple[str, str], float]:
    ref: dict[tuple[str, str], float] = {}
    with open(path) as f:
        for row in csv.DictReader(f):
            ref[(row["platform"], row["design"])] = float(row["fmax_mhz"])
    return ref


def run_one(platform: str, design: str, tol: float, iters: int) -> dict:
    """Run one converger; never raises — failures come back as status=FAIL."""
    t0 = time.time()
    try:
        r = T.tighten(platform, design, start_ns=None, tol=tol, iters=iters)
        r["status"] = "OK"
        r["error"] = ""
    except Exception as e:  # RuntimeError from tighten, or anything unexpected
        r = {"platform": platform, "design": design, "fmax_mhz": 0,
             "period_ps": 0, "converged": False, "iters_used": 0,
             "history": [], "status": "FAIL", "error": str(e)}
    r["wall_s"] = round(time.time() - t0, 1)
    return r


def write_csv(rows: list[dict], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    cols = ["platform", "design", "run", "fmax_mhz", "period_ps", "converged",
            "iters_used", "wall_s", "status", "error"]
    with open(path, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=cols, extrasaction="ignore")
        w.writeheader()
        for r in rows:
            w.writerow(r)


def summarize(rows: list[dict]) -> str:
    """Cross-platform fmax gap table (oc7 vs asap7) over run-1 results."""
    by = {(r["platform"], r["design"]): r for r in rows if r.get("run", 1) == 1}
    designs = sorted({d for (_, d) in by})
    out = ["| design | opencell7 (MHz) | asap7 (MHz) | gap vs asap7 |",
           "|--------|-----------------|-------------|--------------|"]
    for d in designs:
        oc = by.get(("opencell7", d))
        a7 = by.get(("asap7", d))
        oc_s = f"{oc['fmax_mhz']}" if oc and oc["status"] == "OK" else "—"
        a7_s = f"{a7['fmax_mhz']}" if a7 and a7["status"] == "OK" else "—"
        gap = "—"
        if oc and a7 and oc["status"] == "OK" and a7["status"] == "OK" and a7["fmax_mhz"]:
            g = (oc["fmax_mhz"] - a7["fmax_mhz"]) / a7["fmax_mhz"] * 100
            gap = f"{g:+.1f}%"
        out.append(f"| {d} | {oc_s} | {a7_s} | {gap} |")
    return "\n".join(out)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--designs", nargs="+", required=True)
    ap.add_argument("--platforms", nargs="+", default=["opencell7", "asap7"])
    ap.add_argument("--tol", type=float, default=0.04, help="converge tol (frac)")
    ap.add_argument("--iters", type=int, default=4)
    ap.add_argument("--repeat", type=int, default=1,
                    help="run each pair N times; assert runs match (reproducibility)")
    ap.add_argument("--reference", type=Path, default=None,
                    help="CSV of expected fmax; assert each run matches it")
    ap.add_argument("--match-tol", type=float, default=0.03,
                    help="max frac deviation allowed for a match (default 0.03)")
    ap.add_argument("--out", type=Path, default=REPO / "results" / "sweep.csv")
    a = ap.parse_args()

    ref = load_reference(a.reference) if a.reference else {}
    rows: list[dict] = []
    failures: list[str] = []

    for design in a.designs:
        for platform in a.platforms:
            for run in range(1, a.repeat + 1):
                tag = f"{platform}/{design} run{run}/{a.repeat}"
                print(f"\n===== {tag} =====", flush=True)
                r = run_one(platform, design, a.tol, a.iters)
                r["run"] = run
                rows.append(r)
                if r["status"] != "OK":
                    failures.append(f"{tag}: RUN FAILED — {r['error']}")
                    continue
                # faithfulness: compare to reference
                key = (platform, design)
                if key in ref and ref[key]:
                    dev = abs(r["fmax_mhz"] - ref[key]) / ref[key]
                    verdict = "PASS" if dev <= a.match_tol else "FAIL"
                    print(f"[match:reference] {tag}: {r['fmax_mhz']} vs ref "
                          f"{ref[key]:.0f} MHz  dev {dev*100:.1f}%  -> {verdict}")
                    if verdict == "FAIL":
                        failures.append(f"{tag}: fmax {r['fmax_mhz']} != ref "
                                        f"{ref[key]:.0f} ({dev*100:.1f}% > "
                                        f"{a.match_tol*100:.0f}%)")

    # reproducibility: runs of the same (platform, design) must agree
    if a.repeat > 1:
        from collections import defaultdict
        groups = defaultdict(list)
        for r in rows:
            if r["status"] == "OK":
                groups[(r["platform"], r["design"])].append(r["fmax_mhz"])
        for (platform, design), vals in groups.items():
            lo, hi = min(vals), max(vals)
            dev = (hi - lo) / lo if lo else 1.0
            verdict = "PASS" if dev <= a.match_tol else "FAIL"
            print(f"[match:repeat] {platform}/{design}: runs={vals} "
                  f"spread {dev*100:.1f}%  -> {verdict}")
            if verdict == "FAIL":
                failures.append(f"{platform}/{design}: repeat spread "
                                f"{dev*100:.1f}% > {a.match_tol*100:.0f}% {vals}")

    write_csv(rows, a.out)
    summary = summarize(rows)
    md = a.out.with_suffix(".md")
    md.write_text(f"# fmax sweep\n\n{summary}\n\n"
                  f"```json\n{json.dumps(rows, indent=2)}\n```\n")
    print(f"\nartifact: {a.out}\nsummary : {md}\n\n{summary}")

    if failures:
        print("\n".join(["", "FAILURES:"] + [f"  - {x}" for x in failures]))
        return 1
    print("\nALL MATCH ✓")
    return 0


if __name__ == "__main__":
    sys.exit(main())
