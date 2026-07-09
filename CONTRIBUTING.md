# Contributing to OpenCell-5

Thanks for helping. OpenCell-5 is meant to get **better over time through
community fixes** — that's the whole idea.

## First, the mission (read this — it sets the bar)

OpenCell-5 is a **statistical** 5nm-class SDK: it gives people a representative
*feel* of a 5nm design flow when they don't have access to a real foundry PDK.

**It is explicitly NOT sign-off.** The flow stops at a post-CTS, router-free
statistical endpoint. So please **don't** aim contributions at:

- DRC/LVS-clean geometry or detailed-route (DRT) closure,
- foundry-exact correlation to any specific TSMC/Samsung/Intel node,
- tapeout accuracy.

Those are sign-off goals this project deliberately doesn't chase. A PR is judged
on whether it makes the *statistical feel* more representative, more robust, or
more useful — not on manufacturability.

## Good contributions

- **More designs.** Broaden the correlation set — add real open RTL under
  `designs/src/` + a config (see below). More coverage = more trust.
- **Factor calibration.** Tune `scaling/scale_factors_5nm.json` against published
  5nm data (add citations to `docs/SOURCES.md`). Keep factors defensible.
- **Better cells / physical deck.** Improvements to the LEF/site grid, buffering,
  or (a big one) real from-scratch cell layout to hit tighter per-family areas.
- **Tooling robustness.** e.g. `flow/tighten.py`'s clock-tightening is unreliable
  on some logic designs — a fix there is very welcome.
- **Docs.** Clearer QUICKSTART, methodology, examples.

## Run it (what a reviewer will do to your PR)

Prereq: Docker + `docker pull openroad/orfs:latest`. Then, from the repo root:

```bash
flow/run_orfs.sh opencell5 <design> cts     # run a design to the statistical endpoint
flow/ppa.py      opencell5 <design>          # area / fmax / power / buffering
flow/statppa.py  <design>                    # correlate opencell5 vs asap7 (7nm ref)
```

See [`docs/QUICKSTART.md`](docs/QUICKSTART.md) for the full walkthrough and
[`docs/METHODOLOGY.md`](docs/METHODOLOGY.md) for the scaling theory.

## Add a design

1. RTL → `designs/src/<yourdesign>/`.
2. `designs/opencell5/<yourdesign>/config.mk` — copy an existing one and set
   `DESIGN_NAME`, `PLATFORM=opencell5`, `VERILOG_FILES`, `SDC_FILE`,
   `CORE_UTILIZATION`.
3. `flow/run_orfs.sh opencell5 <yourdesign> cts` and confirm it reaches CTS.

## Notes that will save you time

- **Fair fmax needs a matched tight clock.** Designs with loose SDCs report a
  relaxed frequency; use `flow/tighten.py opencell5 <design>` for the true floor.
- **`LEC_CHECK=0`** is set by default (the image's formal-LEC step SIGILLs on
  non-AVX-512 CPUs). Leave it.
- **One design at a time** — concurrent ORFS containers can race at CTS / OOM a
  small host.
- Cell names are `sky130_fd_sc_hd__*` — OpenCell-5's cells are *scaled sky130*
  cells; that naming is honest provenance, not a bug.

## PR flow

Fork → branch → change → open a PR against `main`. Keep PRs focused; describe
what you changed and paste the before/after `flow/statppa.py` (or `ppa.py`)
numbers for any affected design. By contributing you agree your work is licensed
under **Apache-2.0** (this repo's license).
