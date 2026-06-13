#!/usr/bin/env bash
# Fetch sky130_fd_sc_hd and build the canonical TT + SS Liberty files.
#
# The upstream SkyWater libs repo (sky130_fd_sc_hd) ships only `.lib.json`
# intermediates. The `.lib` is produced by `liberty.py` in the parent
# `skywater-pdk` repo. We pull both, then run the builder.
#
# Outputs (under derived/sky130_libs/):
#   sky130_fd_sc_hd__tt_025C_1v80.lib   (TT 25C, 1.80V — typical)
#   sky130_fd_sc_hd__ss_n40C_1v60.lib   (SS -40C, 1.60V — slow-slow)
#
# Sky130 is Apache-2.0; attribution is preserved verbatim by scale_lib.py
# in every derived .lib.

set -euo pipefail
cd "$(dirname "$0")/.."

LIBS_DIR="reference/sky130"
TOOL_DIR="reference/skywater-pdk-parent"
OUT_DIR="derived/sky130_libs"

LIBS_REPO="https://github.com/google/skywater-pdk-libs-sky130_fd_sc_hd.git"
TOOL_REPO="https://github.com/google/skywater-pdk.git"

# Corners to build. Add others (ff_*, additional ss/tt voltages, etc.) here.
CORNERS=( tt_025C_1v80 ss_n40C_1v60 )

# 1) Clone the sc_hd library (JSON intermediates).
if [ ! -d "${LIBS_DIR}/.git" ]; then
    echo "==> Shallow-cloning ${LIBS_REPO} -> ${LIBS_DIR}"
    git clone --depth=1 "${LIBS_REPO}" "${LIBS_DIR}"
else
    echo "==> ${LIBS_DIR} already cloned"
fi

# 2) Clone the parent skywater-pdk repo for its liberty.py builder.
#    --no-recurse-submodules keeps the clone to ~13MB.
if [ ! -d "${TOOL_DIR}/.git" ]; then
    echo "==> Shallow-cloning ${TOOL_REPO} -> ${TOOL_DIR}  (no submodules)"
    git clone --depth=1 --no-recurse-submodules "${TOOL_REPO}" "${TOOL_DIR}"
else
    echo "==> ${TOOL_DIR} already cloned"
fi

# 3) Stub `dataclasses_json` (only used as a no-op decorator) to avoid
#    requiring a pip install.
SHIM="${TOOL_DIR}/scripts/python-skywater-pdk/dataclasses_json/__init__.py"
if [ ! -f "${SHIM}" ]; then
    mkdir -p "$(dirname "${SHIM}")"
    cat > "${SHIM}" <<'EOF'
def dataclass_json(cls=None, **kwargs):
    if cls is None:
        return lambda c: c
    return cls
EOF
    echo "==> Wrote dataclasses_json shim"
fi

# 4) Build a .lib for each corner.
mkdir -p "${OUT_DIR}"
for corner in "${CORNERS[@]}"; do
    LIB="${OUT_DIR}/sky130_fd_sc_hd__${corner}.lib"
    if [ -f "${LIB}" ]; then
        echo "==> ${LIB} already built"
    else
        echo "==> Building ${LIB}"
        python3 scaling/_build_lib.py "${LIBS_DIR}" "${corner}" -o "${OUT_DIR}"
    fi
done

echo ""
echo "==> Done"
echo "    sky130 libs:    ${LIBS_DIR}    ($(du -sh "${LIBS_DIR}" 2>/dev/null | awk '{print $1}'))"
echo "    builder:        ${TOOL_DIR}"
for corner in "${CORNERS[@]}"; do
    LIB="${OUT_DIR}/sky130_fd_sc_hd__${corner}.lib"
    echo "    built .lib:     ${LIB}  ($(du -sh "${LIB}" 2>/dev/null | awk '{print $1}'))"
done
echo ""
echo "Next:"
echo "    python3 scaling/scale_lib.py --corner tt \\"
echo "        --in  ${OUT_DIR}/sky130_fd_sc_hd__tt_025C_1v80.lib \\"
echo "        --out derived/opencell7_tt_0p7v_25c.lib"
echo "    python3 scaling/scale_lib.py --corner ss \\"
echo "        --in  ${OUT_DIR}/sky130_fd_sc_hd__ss_n40C_1v60.lib \\"
echo "        --out derived/opencell7_ss_0p65v_125c.lib"
