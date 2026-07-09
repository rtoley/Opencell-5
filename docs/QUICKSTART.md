# Quickstart — opencell-5 (no agent, no sky130, no build)

**opencell-5** is a *statistical* 5nm-class SDK: it gives you a representative
*feel* of a 5nm design flow when you don't have access to a real foundry PDK. It
is **not** sign-off — the flow stops at a post-CTS, router-free statistical
endpoint (synth → floorplan → place → CTS → RC-estimated timing).

The opencell-5 deck ships **committed and ready to run**. As a user you never
touch sky130 or opencell7 — those are the build-time provenance (see the
maintainer appendix at the very bottom, which you can ignore).

---

## 0. Prerequisite (once)

Docker, to run OpenROAD/ORFS in a container:

```bash
docker pull openroad/orfs:latest
```

Then clone the repo and run everything from its root.

---

## 1. Run a design on opencell-5

```bash
flow/run_orfs.sh opencell5 gcd cts
```

`gcd` is a tiny bundled design. That's the whole run — synth through CTS, with a
real clock tree and RC-estimated timing. The PPA (area, fmax, power, buffering)
is written under `build/orfs_opencell5_gcd/`.

## 2. Read the PPA

```bash
flow/ppa.py opencell5 gcd
```

Prints area / fmax / power / buffering for the design on opencell-5. Nothing else
involved — just opencell-5.

## 3. (Optional) Compare against a 7nm reference

If you want a sanity reference, `asap7` — an open 7nm *predictive* PDK bundled in
the ORFS image — is the neutral yardstick. Nothing from sky130/opencell7 needed:

```bash
flow/statppa.py --platforms asap7 opencell5 gcd
```

You'd expect opencell-5 (5nm) to land smaller than asap7 (7nm).

---

## 4. Run your own design

1. Put the RTL under `designs/src/<yourdesign>/`.
2. Create `designs/opencell5/<yourdesign>/config.mk` — copy an existing one and
   set `DESIGN_NAME`, `VERILOG_FILES`, `SDC_FILE`, `CORE_UTILIZATION`.
3. `flow/run_orfs.sh opencell5 <yourdesign> cts`

---

## 5. Notes / gotchas

- **`LEC_CHECK=0`** is set by default (the image's formal-LEC step SIGILLs on
  non-AVX-512 CPUs). Leave it.
- **One design at a time.** Concurrent ORFS containers can race at CTS / OOM a
  small host.
- **Fair fmax = matched tight clock.** Designs shipped with loose SDCs report a
  relaxed, un-pushed frequency. For a design's true floor:
  `flow/tighten.py opencell5 <design>`.
- **Endpoint is post-CTS, router-free** by design — do not expect DRC-clean GDS.

---
---

## Appendix — provenance (how the deck was derived)

You do **not** need any of this to use opencell-5; the committed deck is the
deliverable. This is only *how it was made* — the statistical scaling of the
silicon-validated sky130 PDK (Apache-2.0) that gives opencell-5 its provenance.

- The 5nm numeric definition lives in `scaling/scale_factors_5nm.json` (factors +
  citations in `docs/SOURCES.md`, theory in `docs/METHODOLOGY.md`).
- The library is re-derivable from the sky130 source:
  ```bash
  make fetch                                                     # fetch sky130 source .lib
  python3 scaling/scale_lib.py --corner tt \
      --in derived/sky130_libs/sky130_fd_sc_hd__tt_025C_1v80.lib \
      --out derived/opencell5_tt_0p70v_25c.lib \
      --factors scaling/scale_factors_5nm.json
  python3 scaling/set_fanout_load.py --lib derived/opencell5_tt_0p70v_25c.lib --value 1.0
  ```
- The physical deck (LEF/tcl) is a committed artifact; `scaling/gridlock_lef.py`
  documents the site/DB-grid-locked scaling method used to produce it.
