#!/usr/bin/env python3
"""ppa.py — print the post-CTS PPA of ONE platform/design (no correlation).

A single-platform readout: run a design (flow/run_orfs.sh <platform> <design>
cts), then read its area / fmax / power / buffering here. Nothing else involved —
just the platform you name.

For a 7nm reference comparison, use:
    flow/statppa.py --platforms asap7 <platform> <design>

Usage:
    flow/ppa.py opencell5 gcd
"""
from __future__ import annotations
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import statppa  # noqa: E402  (reuse the shared, platform-generic parser)


def main() -> int:
    if len(sys.argv) != 3:
        sys.exit("usage: flow/ppa.py <platform> <design>")
    platform, design = sys.argv[1], sys.argv[2]
    m = statppa.parse_metrics(platform, design)
    if m.get("fmax_mhz") is None and m.get("synth_area_um2") is None:
        sys.exit(f"no results for {platform}/{design} — run it first:\n"
                 f"  flow/run_orfs.sh {platform} {design} cts")

    def fmt(v, f):
        return f.format(v) if v is not None else "—"

    bo = m.get("buffers_inserted", 0)
    buf = f"{bo} buffers (✅)" if bo else "0 buffers (⚠️ fmax unreliable)"
    print(f"PPA — {platform} / {design}  (post-CTS, router-free)")
    print(f"  fmax        {fmt(m.get('fmax_mhz'), '{:.0f}')} MHz")
    print(f"  min period  {fmt(m.get('period_min'), '{:.3f}')}")
    print(f"  worst slack {fmt(m.get('worst_slack'), '{:.3f}')}")
    print(f"  synth area  {fmt(m.get('synth_area_um2'), '{:.2f}')} um^2")
    print(f"  total power {fmt(m.get('total_power'), '{:.3e}')}")
    print(f"  buffering   {buf}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
