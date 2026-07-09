#!/usr/bin/env bash
# flow/run_orfs.sh — reproducible OpenROAD-flow-scripts launcher.
#
# Drives a design end-to-end (synth -> floorplan -> place -> CTS -> route ->
# final post-route STA) inside the openroad/orfs container. Replaces the lost
# ad-hoc `docker run` invocations: ONE tracked, parameterized entry point so
# every design runs the same way. This is the reproducibility artifact the
# opencell-5 open-source carve-out depends on.
#
# Mounts are ADDITIVE over the image so the image's baked-in reference RTL
# (e.g. designs/src/gcd/gcd.v) stays intact while our opencell5 platform and
# design configs are layered on top.
#
# Usage:
#   flow/run_orfs.sh <platform> <design_nickname> [extra make args/targets...]
#   flow/run_orfs.sh opencell5 gcd                 # full flow to final STA
#   flow/run_orfs.sh opencell5 gcd finish          # stop at a named target
#
# Env:
#   ORFS_IMAGE   container image            (default: openroad/orfs:latest)
#   LEC_CHECK    formal LEC on/off          (default: 0 — kepler-formal crashes
#                                            CTS on non-AVX-512 CPUs)
#   ORFS_TIMEOUT seconds before the run is killed (default: 5400)
#
# Output (host): build/orfs_<platform>_<design>/{logs,results,reports,objects,run.log}
set -euo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
IMAGE="${ORFS_IMAGE:-openroad/orfs:latest}"
FLOW=/OpenROAD-flow-scripts/flow

PLATFORM="${1:?usage: run_orfs.sh <platform> <design> [make args]}"
DESIGN="${2:?usage: run_orfs.sh <platform> <design> [make args]}"
shift 2 || true
MAKE_ARGS="$*"

CFG="designs/${PLATFORM}/${DESIGN}/config.mk"

BUILD="$REPO/build/orfs_${PLATFORM}_${DESIGN}"
# A prior run writes outputs as container-root; reclaim ownership so the host
# user can write run.log and reruns don't spuriously fail on a permission error.
if [ -d "$BUILD" ] && [ ! -w "$BUILD" ]; then
  docker run --rm -v "$REPO/build:/b" "${ORFS_IMAGE:-openroad/orfs:latest}" \
    chown -R "$(id -u):$(id -g)" "/b/orfs_${PLATFORM}_${DESIGN}" 2>/dev/null || true
fi
mkdir -p "$BUILD"/{logs,results,reports,objects}

NAME="orfs_${PLATFORM}_${DESIGN}"
docker rm -f "$NAME" >/dev/null 2>&1 || true

# --- assemble additive bind mounts ---
M=()
# Platform: opencell5 is NOT in the image (additive overlay); built-ins like
# asap7/nangate45 already exist. Only overlay a host platform that is REAL
# (has a config.mk) — guarding against a stray/empty host platform dir
# shadowing the image's complete one (e.g. an empty platforms/asap7/).
if [ -f "$REPO/platforms/$PLATFORM/config.mk" ]; then
  M+=( -v "$REPO/platforms/$PLATFORM:$FLOW/platforms/$PLATFORM:ro" )
  echo "    platform: host overlay"
else
  echo "    platform: image built-in"
fi
# Design config: mount ONLY this one design dir (not the whole platform designs
# dir) so we never hide the image's built-in configs (e.g. asap7/gcd). If the
# host has no config for it, fall through to the image's built-in design.
if [ -f "$REPO/$CFG" ]; then
  M+=( -v "$REPO/designs/$PLATFORM/$DESIGN:$FLOW/designs/$PLATFORM/$DESIGN:ro" )
  echo "    design : host config (overlay)"
else
  echo "    design : image built-in ($CFG not on host)"
fi
# Our RTL subdirs, mounted per-subdir so we never hide the image's baked RTL.
if [ -d "$REPO/designs/src" ]; then
  for d in "$REPO/designs/src"/*/; do
    [ -d "$d" ] && M+=( -v "${d%/}:$FLOW/designs/src/$(basename "${d%/}"):ro" )
  done
fi
# Capture outputs back to the host build dir.
M+=( -v "$BUILD/logs:$FLOW/logs" \
     -v "$BUILD/results:$FLOW/results" \
     -v "$BUILD/reports:$FLOW/reports" \
     -v "$BUILD/objects:$FLOW/objects" )

echo "==> ORFS run  platform=$PLATFORM  design=$DESIGN"
echo "    config : $CFG"
echo "    output : $BUILD"
echo "    image  : $IMAGE   LEC_CHECK=${LEC_CHECK:-0}"
[ -n "$MAKE_ARGS" ] && echo "    extra  : $MAKE_ARGS"

timeout "${ORFS_TIMEOUT:-5400}" \
  docker run --rm --name "$NAME" "${M[@]}" -w "$FLOW" \
    -e "LEC_CHECK=${LEC_CHECK:-0}" \
    "$IMAGE" \
    bash -lc "make DESIGN_CONFIG=$CFG $MAKE_ARGS" 2>&1 | tee "$BUILD/run.log"
rc=${PIPESTATUS[0]}

if [ "$rc" -eq 124 ]; then
  echo "==> TIMEOUT after ${ORFS_TIMEOUT:-5400}s — killing container $NAME" >&2
  docker rm -f "$NAME" >/dev/null 2>&1 || true
fi
echo "==> exit $rc  (log: $BUILD/run.log)"
exit "$rc"
