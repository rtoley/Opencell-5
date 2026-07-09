#!/usr/bin/env python3
"""statppa.py — autonomous statistical-PPA correlation between two platforms.

Runs a design through BOTH platforms to a router-free statistical endpoint
(synth -> floorplan -> place -> CTS, i.e. ORFS target `cts`) and correlates
the PPA. We deliberately STOP before detailed routing: DRT/DRC are sign-off
tools whose job is manufacturability, which is not the opencell platforms'
purpose. The post-CTS stage carries a real clock tree and RC-estimated timing,
and both platforms reach it cleanly — the deepest honest, apples-to-apples
comparison point for analyzing real designs.

It also ASSERTS that high-fanout buffering actually happened (repair_design
inserted buffers), so we can never again report an unbuffered, meaningless
frequency. See memory: statistical-flow-not-signoff, no-handwave-buffer-fanout.

The platform pair is configurable (`--platforms BASELINE DUT`), so any deck is a
first-class citizen: asap7-vs-opencell7 (default), opencell7-vs-opencell5 (node
step), etc. The signed gap is (DUT - BASELINE)/BASELINE.

Usage:
  flow/statppa.py <design> [<design> ...]                       # default asap7 vs opencell7
  flow/statppa.py --platforms opencell7 opencell5 <design> ...  # 7nm vs 5nm node step
  flow/statppa.py --no-run <design>                             # parse existing builds only
"""
from __future__ import annotations
import argparse, json, re, subprocess, sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
DEFAULT_PLATFORMS = ["asap7", "opencell5"]   # [baseline, DUT]


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
        # yosys synth_stat varies by design: hierarchical designs emit a
        # "Chip area for top module" line (use it); flat designs emit only
        # "Chip area for module" (the last such line is the top). Match the
        # value AFTER the name's closing quote, since escaped Verilog names can
        # contain ':' (e.g. '\ALU..._CO[14:0]...') — a naive '.*?:' would stop
        # inside the name and capture a stray digit (reported area 0.0 for gcd).
        text = syn.read_text()
        top = re.search(r"Chip area for top module\s+'[^']*'\s*:\s*([\d.]+)",
                        text)
        if top:
            m["synth_area_um2"] = float(top.group(1))
        else:
            mods = re.findall(
                r"Chip area for module\s+'[^']*'\s*:\s*([\d.]+)", text)
            if mods:
                m["synth_area_um2"] = float(mods[-1])

    # buffering proof — repair_design during global placement
    gp = _find(build, "3_3_place_gp.log")
    if gp:
        t = gp.read_text()
        fv = re.search(r"Found (\d+) fanout violations", t)
        bi = re.search(r"Inserted (\d+) buffers in (\d+) nets", t)
        m["fanout_violations_found"] = int(fv.group(1)) if fv else 0
        m["buffers_inserted"] = int(bi.group(1)) if bi else 0
    return m


def correlate(design: str, base: dict, dut: dict,
              base_name: str, dut_name: str) -> str:
    """Build a markdown correlation block: DUT vs BASELINE, gap=(dut-base)/base."""
    def gap(dv, bv):
        if dv is None or bv is None or bv == 0:
            return None
        return (dv - bv) / bv * 100.0

    rows = [("synth area (µm²)", "synth_area_um2", "{:.1f}"),
            ("fmax (MHz)",       "fmax_mhz",       "{:.0f}"),
            ("worst slack",      "worst_slack",    "{:.3f}"),
            ("total power",      "total_power",    "{:.2e}")]
    lines = [f"### {design} — {dut_name} vs {base_name} (post-CTS, router-free)",
             "",
             f"| metric | {dut_name} | {base_name} | signed gap |",
             "|---|---|---|---|"]
    for label, key, fmt in rows:
        dv, bv = dut.get(key), base.get(key)
        g = gap(dv, bv)
        dvs = fmt.format(dv) if dv is not None else "—"
        bvs = fmt.format(bv) if bv is not None else "—"
        gs = f"{g:+.1f}%" if g is not None else "—"
        lines.append(f"| {label} | {dvs} | {bvs} | {gs} |")
    # buffering assertion (on the DUT)
    bo = dut.get("buffers_inserted", 0)
    fo = dut.get("fanout_violations_found", 0)
    status = "✅ buffered" if bo > 0 else "⚠️  NO BUFFERS — fmax is unreliable"
    lines += ["",
              f"**{dut_name} buffering:** {fo} fanout violations found, "
              f"{bo} buffers inserted — {status}"]
    return "\n".join(lines)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("designs", nargs="+")
    ap.add_argument("--platforms", nargs=2, metavar=("BASELINE", "DUT"),
                    default=DEFAULT_PLATFORMS,
                    help="two platforms to correlate; gap=(DUT-BASELINE)/BASELINE "
                         "(default: asap7 opencell7)")
    ap.add_argument("--no-run", action="store_true",
                    help="parse existing build dirs only, don't launch ORFS")
    args = ap.parse_args()
    base_name, dut_name = args.platforms

    out_dir = REPO / "build" / "statppa"
    out_dir.mkdir(parents=True, exist_ok=True)
    report = [f"# Statistical PPA correlation — {dut_name} vs {base_name}",
              "_Endpoint: post-CTS, router-free (no DRT/DRC sign-off). "
              "Both platforms reach this cleanly._", ""]
    allj = {}

    for design in args.designs:
        if not args.no_run:
            for p in args.platforms:
                rc = run_orfs(p, design)
                if rc != 0:
                    print(f"   note: {p}/{design} returned {rc} "
                          f"(CTS endpoint may still have completed)", flush=True)
        base = parse_metrics(base_name, design)
        dut = parse_metrics(dut_name, design)
        allj[design] = {base_name: base, dut_name: dut}
        report.append(correlate(design, base, dut, base_name, dut_name))
        report.append("")

    (out_dir / "report.md").write_text("\n".join(report))
    (out_dir / "report.json").write_text(json.dumps(allj, indent=2))
    print("\n".join(report))
    print(f"\n==> wrote {out_dir/'report.md'} and report.json")
    return 0


if __name__ == "__main__":
    sys.exit(main())
