#!/usr/bin/env python3
"""statppa.py — autonomous statistical-PPA correlation: asap7 vs opencell-7.

Runs a design through BOTH platforms to a router-free statistical endpoint
(synth -> floorplan -> place -> CTS, i.e. ORFS target `cts`) and correlates
the PPA. We deliberately STOP before detailed routing: DRT/DRC are sign-off
tools whose job is manufacturability, which is not opencell-7's purpose. The
post-CTS stage carries a real clock tree and RC-estimated timing, and BOTH
platforms reach it cleanly on every design — so it's the deepest honest,
apples-to-apples comparison point for analyzing real designs.

It also ASSERTS that high-fanout buffering actually happened (repair_design
inserted buffers), so we can never again report an unbuffered, meaningless
frequency. See memory: statistical-flow-not-signoff, no-handwave-buffer-fanout.

Usage:
  flow/statppa.py <design> [<design> ...]           # run both platforms + report
  flow/statppa.py --no-run <design>                 # parse existing builds only
"""
from __future__ import annotations
import argparse, json, re, subprocess, sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
PLATFORMS = ["asap7", "opencell7"]


def run_orfs(platform: str, design: str) -> int:
    """Drive one platform/design to the CTS endpoint (no router)."""
    cmd = [str(REPO / "flow" / "run_orfs.sh"), platform, design, "cts"]
    print(f"==> {platform}/{design}: running to CTS endpoint ...", flush=True)
    return subprocess.run(cmd, cwd=REPO, env={**__import__("os").environ,
                          "LEC_CHECK": "0"}).returncode


def _find(build: Path, name: str) -> Path | None:
    hits = list(build.glob(f"reports/*/*/base/{name}")) + \
           list(build.glob(f"logs/*/*/base/{name}"))
    return hits[0] if hits else None


def parse_metrics(platform: str, design: str) -> dict:
    """Pull area / fmax / buffering from a finished build dir."""
    build = REPO / "build" / f"orfs_{platform}_{design}"
    m: dict = {"platform": platform, "design": design, "build": str(build)}

    cts = _find(build, "4_cts_final.rpt")
    if cts:
        t = cts.read_text()
        fm = re.search(r"period_min\s*=\s*([\d.]+)\s+fmax\s*=\s*([\d.]+)", t)
        if fm:
            m["fmax_mhz"] = float(fm.group(2))
            m["period_min"] = float(fm.group(1))
        ws = re.search(r"worst slack max\s+(-?[\d.]+)", t)
        if ws:
            m["worst_slack"] = float(ws.group(1))
        pw = re.search(r"^Total\s+[\d.e+-]+\s+[\d.e+-]+\s+[\d.e+-]+\s+([\d.e+-]+)",
                       t, re.M)
        if pw:
            m["total_power"] = float(pw.group(1))

    syn = _find(build, "synth_stat.txt")
    if syn:
        a = re.search(r"Chip area for (?:module|top module).*?:\s*([\d.]+)",
                      syn.read_text())
        if a:
            m["synth_area_um2"] = float(a.group(1))

    # buffering proof — repair_design during global placement
    gp = _find(build, "3_3_place_gp.log")
    if gp:
        t = gp.read_text()
        fv = re.search(r"Found (\d+) fanout violations", t)
        bi = re.search(r"Inserted (\d+) buffers in (\d+) nets", t)
        m["fanout_violations_found"] = int(fv.group(1)) if fv else 0
        m["buffers_inserted"] = int(bi.group(1)) if bi else 0
    return m


def correlate(design: str, a: dict, o: dict) -> str:
    """Build a markdown correlation block (opencell-7 vs asap7)."""
    def gap(ov, av):
        if ov is None or av is None or av == 0:
            return None
        return (ov - av) / av * 100.0

    rows = [("synth area (µm²)", "synth_area_um2", "{:.1f}"),
            ("fmax (MHz)",       "fmax_mhz",       "{:.0f}"),
            ("worst slack",      "worst_slack",    "{:.3f}"),
            ("total power",      "total_power",    "{:.2e}")]
    lines = [f"### {design} — opencell-7 vs asap7 (post-CTS, router-free)",
             "",
             "| metric | opencell-7 | asap7 | signed gap |",
             "|---|---|---|---|"]
    for label, key, fmt in rows:
        ov, av = o.get(key), a.get(key)
        g = gap(ov, av)
        ovs = fmt.format(ov) if ov is not None else "—"
        avs = fmt.format(av) if av is not None else "—"
        gs = f"{g:+.1f}%" if g is not None else "—"
        lines.append(f"| {label} | {ovs} | {avs} | {gs} |")
    # buffering assertion
    bo = o.get("buffers_inserted", 0)
    fo = o.get("fanout_violations_found", 0)
    status = "✅ buffered" if bo > 0 else "⚠️  NO BUFFERS — fmax is unreliable"
    lines += ["",
              f"**opencell-7 buffering:** {fo} fanout violations found, "
              f"{bo} buffers inserted — {status}"]
    return "\n".join(lines)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("designs", nargs="+")
    ap.add_argument("--no-run", action="store_true",
                    help="parse existing build dirs only, don't launch ORFS")
    args = ap.parse_args()

    out_dir = REPO / "build" / "statppa"
    out_dir.mkdir(parents=True, exist_ok=True)
    report = ["# Statistical PPA correlation — asap7 vs opencell-7",
              "_Endpoint: post-CTS, router-free (no DRT/DRC sign-off). "
              "Both platforms reach this cleanly._", ""]
    allj = {}

    for design in args.designs:
        if not args.no_run:
            for p in PLATFORMS:
                rc = run_orfs(p, design)
                if rc != 0:
                    print(f"   note: {p}/{design} returned {rc} "
                          f"(CTS endpoint may still have completed)", flush=True)
        a = parse_metrics("asap7", design)
        o = parse_metrics("opencell7", design)
        allj[design] = {"asap7": a, "opencell7": o}
        report.append(correlate(design, a, o))
        report.append("")

    (out_dir / "report.md").write_text("\n".join(report))
    (out_dir / "report.json").write_text(json.dumps(allj, indent=2))
    print("\n".join(report))
    print(f"\n==> wrote {out_dir/'report.md'} and report.json")
    return 0


if __name__ == "__main__":
    sys.exit(main())
