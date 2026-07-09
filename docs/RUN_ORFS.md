# Reproducible ORFS runs — `flow/run_orfs.sh`

One tracked, parameterized entry point for running a design end-to-end
(synth → floorplan → place → CTS → route → final post-route STA) through the
`openroad/orfs` container. Replaces ad-hoc hand-typed `docker run` invocations
so every design/platform runs the *same* way — the reproducibility artifact the
opencell-5 open-source carve-out depends on.

## Usage

```bash
flow/run_orfs.sh <platform> <design_nickname> [extra make args/targets]

flow/run_orfs.sh asap7     gcd          # full flow to final STA
flow/run_orfs.sh opencell5 gcd          # opencell-5 platform
flow/run_orfs.sh asap7     picorv32 finish   # stop at a named make target
```

Output lands in `build/orfs_<platform>_<design>/{logs,results,reports,objects,run.log}`.

## How it works (additive mounts)

The container image already ships `asap7`, `nangate45`, `sky130hd`, … and baked
reference RTL (e.g. `designs/src/gcd`). The launcher overlays **only** what we
add, so it never hides the image's built-ins:

- `platforms/<platform>` — mounted **only if it has a `config.mk`** (so the
  `opencell5` platform overlays, and a stray/empty `platforms/asap7/` can't
  shadow the image's complete one).
- `designs/<platform>/<design>` — mounted per-design (not the whole platform
  dir); falls through to the image's built-in design if we don't ship one.
- `designs/src/<sub>` — mounted per-subdir so our RTL overrides without hiding
  the image's baked designs.
- output dirs are bind-mounted back to the host build dir; stale root-owned
  dirs from prior runs are re-chowned to the host user first.

## Three operating rules (all load-bearing)

1. **`LEC_CHECK=0`** (set by default). The image bundles `kepler-formal`, whose
   `libnaja_*.so` use AVX-512; on CPUs without it the LEC step SIGILLs at CTS.
   This env var skips it. Authoritative equivalence checking is done synth-time.
2. **Run designs SERIALLY.** Running multiple ORFS containers at once
   oversubscribes the CPU and triggers an intermittent
   `cts.tcl … child killed: illegal instruction` threading race at
   `repair_timing` — *even with* `LEC_CHECK=0`. It is not a real block; solo
   runs complete. One design at a time.
3. **Cap synthesis memory — don't co-run heavy jobs.** yosys synth of the large
   designs peaks in the tens of GiB. On a memory-constrained host, a synth that
   grows near the available RAM *while another P&R container is also running*
   can trigger a global OOM that takes down the whole build environment — not
   just the job. Run synth alone, and/or wrap the heavy step in a memory cgroup
   so OOM kills only that process cleanly instead of destabilizing the host:
   ```bash
   systemd-run --user --scope -p MemoryMax=20G -p MemorySwapMax=2G \
     flow/run_orfs.sh <platform> <design>
   ```

## Env knobs

| Var | Default | Meaning |
|---|---|---|
| `ORFS_IMAGE` | `openroad/orfs:latest` | container image |
| `LEC_CHECK` | `0` | formal LEC on/off |
| `ORFS_TIMEOUT` | `5400` | seconds before the run is killed |

## Validated baseline (asap7, this CPU, serial)

| design | fmax | worst slack |
|---|---|---|
| aes | 2619 MHz | −1.79 ps |
| gcd | 2540 MHz | −83.66 ps |
| picorv32 | 1608 MHz | +378.11 ps |

opencell-5 currently reaches global route then stops at **DRT-0073**
(scaled-PDK pin-access residual) — the open platform task.
