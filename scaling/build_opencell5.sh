#!/usr/bin/env bash
# build_opencell5.sh — assemble the opencell-5 (5nm-class) platform.
#
# opencell-5 is the opencell-7 statistical recipe re-pointed one node tighter
# (see scaling/scale_factors_5nm.json). It is a *statistical* deck for a
# representative feel of 5nm, NOT sign-off. It is built INCREMENTALLY from the
# already-scaled, grid-consistent opencell-7 deck (not from native sky130), which
# is what keeps placement legal — see scaling/gridlock_lef.py for the DB/site
# grid-lock that the naive scale_lef.py misses.
#
# Result vs opencell-7 (validated 2026-07-08, d16/d48/gcd/aes/picorv32):
#   area  ~1.64-1.79x smaller (clean one-node density step; area is the solid signal)
#   fmax  ~1.07-1.10x faster on tight-clock (flop-chain) designs; logic designs
#         need clock-tightening to measure fmax fairly (harmonized-SDC rule).
#
# Usage:  bash scaling/build_opencell5.sh
set -euo pipefail
cd "$(dirname "$0")/.."
F=scaling/scale_factors_5nm.json
SRC=platforms/opencell7
DST=platforms/opencell5
SKY_TT=derived/sky130_libs/sky130_fd_sc_hd__tt_025C_1v80.lib

echo "== 1. opencell-5 lib from sky130 (5nm factors) + fanout fix =="
mkdir -p derived
python3 scaling/scale_lib.py --corner tt --in "$SKY_TT" \
  --out derived/opencell5_tt_0p70v_25c.lib --factors "$F"
python3 scaling/set_fanout_load.py --lib derived/opencell5_tt_0p70v_25c.lib --value 1.0

echo "== 2. copy opencell-7 deck -> opencell-5 =="
rm -rf "$DST"; cp -r "$SRC" "$DST"
rm -f "$DST"/*.bak "$DST"/lef/*.bak "$DST"/lib/*.bak "$DST"/.scaled
# Drop the GDS: the copied opencell-7-scale layout is WRONG for opencell-5 and is
# never read at the post-CTS statistical endpoint (GDS is only for final routing).
rm -rf "$DST/gds"
cp derived/opencell5_tt_0p70v_25c.lib "$DST/lib/sky130_fd_sc_hd__tt_025C_1v80.lib"

echo "== 3. grid-locked LEF (SITE 0.0460x0.2720, all cells integer sites on 0.0005 DB grid) =="
python3 scaling/gridlock_lef.py "$SRC/lef/sky130_fd_sc_hd_merged.lef" "$DST/lef/sky130_fd_sc_hd_merged.lef"
python3 scaling/gridlock_lef.py "$SRC/lef/sky130_fd_sc_hd.tlef" "$DST/lef/sky130_fd_sc_hd.tlef" --tlef

echo "== 4. scale platform tcl (pdn/tracks/setRC/tapcell) by the incremental node step =="
DELTA=$(mktemp); echo '{"factors":{"area":{"value":1.7857,"operation":"divide"}}}' > "$DELTA"
python3 scaling/scale_platform.py --in "$DST" --out "$DST" --factors "$DELTA" --force
rm -f "$DELTA"

echo "== 5. wire designs/opencell5/<d> from designs/opencell7/<d> =="
for d in "$@"; do
  rm -rf "designs/opencell5/$d"; mkdir -p designs/opencell5
  cp -r "designs/opencell7/$d" "designs/opencell5/$d"
  sed -i -E 's/(export PLATFORM[[:space:]]*=[[:space:]]*)opencell7/\1opencell5/' "designs/opencell5/$d/config.mk"
done
echo "== opencell-5 built. designs wired: ${*:-<none: pass design names as args>} =="
echo "   run:  flow/run_orfs.sh opencell5 <design> cts"
