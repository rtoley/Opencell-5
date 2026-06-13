# OpenROAD sign-off-timing attempt on macOS — notes

What was tried, what worked, what didn't, and the documented path forward.

## 1. Why we tried

The synthesis-only flow `flow/synth.tcl` + STA can't produce silicon-realistic fmax on SoC-class designs (see `docs/METHODOLOGY.md §5.4`). For PicoRV32 and `a large SoC design`, STA on the un-buffered netlist gives meaningless numbers (a single inverter showing 1.4 µs delay due to unbounded fanout). Real fmax needs physical implementation — buffer/repeater insertion, placement, CTS, parasitic extraction — which is what OpenROAD provides.

## 2. macOS native OpenROAD build: abandoned

Six retries against `OpenROAD-flow-scripts/build_openroad.sh -o`:

| Retry | What broke | Workaround tried |
|---|---|---|
| 1 | abc default script OOM'd separately (unrelated to OR) | switched to `abc -fast` for that synth |
| 2 | DepInstaller called `pip` (only `pip3` on PATH) | shim `pip` → `python3 -m pip` |
| 3 | Qt5 cmake config had broken mkspecs path | `brew reinstall qt@5` |
| 4 | Qt5 still failed (reinstall didn't fix `_qt5Core_install_prefix` resolution through brew symlinks) | patched `build_openroad.sh` to `readlink -f` the qt@5 prefix |
| 5 | Qt5Core found via the OTHER brew symlink, same prefix bug | `brew unlink qt@5` so CMake had only one Qt5 to find |
| 6 | Configure now passed; build failed at 64% on libabc linker errors | (didn't try a 7th) |

Conclusion: **OpenROAD doesn't build natively on macOS without significant per-component intervention** (qt@5 brew install issues, CUDD path, TCL path, libabc linker). The upstream project does not appear to test on Apple Silicon as a first-class platform. Time invested: ~6 hours of background compile-fail-retry. Stopped.

## 3. Docker via Colima + Rosetta: partial success

Switched to the supported Docker path. Concrete steps that worked:

```bash
# Docker daemon on Apple Silicon via lightweight VM
brew install colima
colima start --vm-type=vz --vz-rosetta --memory 12 --cpu 8 --disk 60

# Pull the (amd64-only) ORFS image, run via Rosetta
docker pull --platform=linux/amd64 openroad/orfs:latest

# Run a bundled design end-to-end
docker run -d --rm --platform=linux/amd64 \
  -v "$HOST_RESULTS_DIR:/results" openroad/orfs:latest \
  bash -c 'cd /OpenROAD-flow-scripts/flow && \
           make DESIGN_CONFIG=./designs/asap7/aes/config.mk 2>&1 | tail -200 > /results/run.log && \
           cp -r logs reports results /results/'
```

The sanity-check `aes` design on the `asap7` platform ran through:

| Step | Result |
|---|---|
| 1_synth (yosys+abc) | ✓ |
| 2_floorplan | ✓ |
| 3_global_place | ✓ |
| 3_resizer | ✓ (slack -19.63, power 146 mW) |
| 3_detailed_place | ✓ |
| **4_1_cts** | **FAILED — `child killed: illegal instruction`** |

TritonCTS (the clock-tree synthesis pass) uses x86 SIMD intrinsics that Rosetta doesn't translate cleanly. The pre-CTS metrics are real and useful, but **the full sign-off STA isn't reachable on this runtime**. This is consistent with multiple open issues on the OpenROAD GitHub for Rosetta-related crashes in CTS / routing on Apple Silicon.

`a large SoC design` (the larger target) would hit the same wall, much later. Not worth the 8-hour compute spend before the same crash.

## 4. What the EDA flow *does* prove on this runtime

- **Toolchain is correct.** The SystemVerilog synth flags (yosys-slang plugin, `--allow-use-before-declare`, bake-and-substitute for `$readmemh`, `abc -fast`) all carry through to the ORFS bundled yosys without modification.
- **ASAP7 platform integration is fine.** ORFS-bundled `aes/asap7` uses the same library structure OpenCell-7 will need in cut-3.
- **Placement-stage timing is achievable on Apple Silicon.** Useful for high-fanout-aware netlist quality checks, congestion estimation, area sanity — just not for full sign-off fmax.

## 5. What the EDA flow *doesn't* prove on this runtime

- **No sign-off fmax** — CTS + routing + extraction are unreachable until either (a) a Linux runtime or (b) Rosetta in OpenROAD's CTS path improves.

## 6. Documented path forward for sign-off timing

In order of effort:

1. **Cheap, fast** — small cloud VM (AWS / GCP / DigitalOcean Linux x86_64, 16 GB / 4 vCPU class, ~$0.30–0.60 / hr). Pull `openroad/orfs:latest` natively (no Rosetta), run the flow, terminate. **For a large SoC design: ~6–8 hours wall, ~$5 total compute.** This is the unblock path.
2. **One-time-setup, free** — any Linux box on hand (workstation, Raspberry Pi class is too small; need 16 GB+ RAM). Same Docker invocation, no Rosetta layer.
3. **Slow but local** — `colima start --vm-type=qemu` (pure QEMU emulation, no Rosetta). Full instruction coverage, but **5–10× slowdown vs Rosetta** in the steps that *were* working. AES would take hours; a large SoC design would take a working day or more.
4. **Cut-3 in OpenCell-7** — generate LEF/GDS for OpenCell-7 cells so the same Docker-via-cloud flow can target opencell-7 directly instead of ASAP7. Independent of macOS issues; this is a doc/scaler-side task.

## 7. Compact reproducibility recipe

For anyone landing on this in the future:

```bash
# === macOS Apple Silicon, sanity check only ===
brew install colima
colima start --vm-type=vz --vz-rosetta --memory 12 --cpu 8

docker pull --platform=linux/amd64 openroad/orfs:latest
docker run --rm --platform=linux/amd64 openroad/orfs:latest \
    bash -c 'cd /OpenROAD-flow-scripts/flow && \
             make DESIGN_CONFIG=./designs/asap7/gcd/config.mk'
# Will get partial result; CTS step crashes with illegal instruction.

colima stop      # free memory afterwards
```

```bash
# === Linux x86_64 (workstation or cloud) — actual sign-off path ===
docker pull openroad/orfs:latest
docker run --rm -v "$PWD/results:/results" openroad/orfs:latest \
    bash -c 'cd /OpenROAD-flow-scripts/flow && \
             make DESIGN_CONFIG=./designs/asap7/aes/config.mk && \
             cp -r logs reports results /results/'
# Full flow including CTS + routing + STA completes natively.
```

## 8. Status

**Sign-off timing for OpenCell-7-targeted designs is gated on the Linux-runtime requirement above, not on any defect in this repository's flow.** The synth-only path remains the in-repo flow for area + cell counts; sign-off fmax is parked as a cut-3-era deliverable that pairs OpenCell-7 LEF + a Linux Docker host.
