#!/usr/bin/env python3
"""set_fanout_load.py — bake default_fanout_load into a scaled .lib.

WHY THIS EXISTS (the fanout fix): sky130 ships `default_fanout_load : 0.0`,
and scale_lib.py passes it through unchanged. With fanout_load=0, STA
accumulates ZERO load from a net's fanout, so the max_fanout / max_capacitance
checks can never fire on a high-fanout net — repair_design inserts no buffers,
the lone driver fights all its loads, and fmax is garbage (the long-standing
"crap frequency" on opencell-7). asap7 ships default_fanout_load=1.

This is the pipeline step that makes opencell-7 asap7-faithful: run it on the
scaled lib (after scale_lib.py) so repair_design actually buffers high-fanout
nets. Validated: picorv32 358 buffers, aes 278 buffers, a 512-fanout read_en
test closing 300 ps. See memory: no-handwave-buffer-fanout.

Idempotent. Default value 1.0 (matches asap7).

Usage:
  scaling/set_fanout_load.py --lib <path/to/scaled.lib> [--value 1.0]
"""
from __future__ import annotations
import argparse, re
from pathlib import Path


def set_fanout_load(text: str, value: float) -> tuple[str, int]:
    pat = re.compile(r'(default_fanout_load\s*:\s*)([0-9.]+)(\s*;)')
    new, n = pat.subn(rf'\g<1>{value:.10f}\g<3>', text, count=1)
    if n == 0:
        # No library-level default present — inject after the library( ... ) {  line.
        m = re.search(r'(library\s*\([^)]*\)\s*\{\s*\n)', text)
        if m:
            inject = f'    default_fanout_load : {value:.10f};\n'
            new = text[:m.end()] + inject + text[m.end():]
            n = 1
    return new, n


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--lib", required=True, type=Path)
    ap.add_argument("--value", type=float, default=1.0)
    a = ap.parse_args()
    text = a.lib.read_text()
    new, n = set_fanout_load(text, a.value)
    if n == 0:
        raise SystemExit("ERROR: could not set or inject default_fanout_load")
    a.lib.write_text(new)
    print(f"==> set default_fanout_load = {a.value} in {a.lib}")


if __name__ == "__main__":
    main()
