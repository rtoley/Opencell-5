#!/usr/bin/env bash
# OpenCell-5 — end-to-end verification.
#
# Steps:
#   1. Fetch sky130 if missing.
#   2. Build the derived .lib.
#   3. Synth + STA the reference design on both libraries.
#   4. Compare fmax and area ratios to the target windows.

set -euo pipefail
cd "$(dirname "$0")"

echo "===================================================="
echo "OpenCell-5 — scaling-tool verification"
echo "===================================================="

# Tool checks
echo ""
echo "==> Checking tools"
command -v yosys   >/dev/null || { echo "FAIL: yosys not in PATH"; exit 1; }
command -v sta     >/dev/null || { echo "FAIL: sta not in PATH";   exit 1; }
command -v python3 >/dev/null || { echo "FAIL: python3 not in PATH"; exit 1; }
command -v git     >/dev/null || { echo "FAIL: git not in PATH";   exit 1; }
echo "    yosys:   $(yosys -V 2>&1 | head -1)"
echo "    sta:     $(sta -version 2>&1 | head -1)"
echo "    python:  $(python3 --version)"

echo ""
echo "==> Step 1: fetch sky130 (if missing)"
if [ ! -f reference/sky130/timing/sky130_fd_sc_hd__tt_025C_1v80.lib ]; then
    ./reference/fetch_sky130.sh
else
    echo "    sky130 already present at reference/sky130/"
fi

echo ""
echo "==> Step 2: scale -> derived/opencell5_tt_0p7v_25c.lib"
make scale

echo ""
echo "==> Step 3: validate (synth+STA both libs, compute ratios)"
python3 scaling/validate.py

echo ""
echo "===================================================="
echo "verify.sh PASSED"
echo "===================================================="
