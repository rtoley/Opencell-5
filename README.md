# OpenCell-7

A 7nm-class standard cell library derived by **statistical scaling** of the
silicon-validated SkyWater sky130 PDK (Apache-2.0). Built for Yosys + OpenSTA.

**Status:** v0.3 — adds slow corner + FinFET process derate. The hand-crafted
5-cell cut-0 smoke test is preserved on branch `legacy/handcrafted-cut0`.

## What this is

OpenCell-7 takes canonical sky130_fd_sc_hd `.lib` files and rewrites every
numeric field — delays, transitions, setup/hold, leakage, dynamic power,
input cap, area, voltage, temperature — to a 7nm-class operating point.
Two corners ship:

| Corner | Source (sky130) | Output (opencell7) | Use for |
|---|---|---|---|
| **TT** | tt_025C_1v80 | tt_0p7v_25c | Typical-case PPA narration |
| **SS** | ss_n40C_1v60 | ss_0p65v_125c | **Setup-time STA / fmax sign-off** |

> **Report fmax from the SS corner.** The TT corner is too optimistic — it
> matches what a typical-case synthesis report would show, not what a setup
> sign-off would. SS includes the 1.4× process derate on top of slow-corner
> sky130 numerics.

Scaling factors (defaults in `scaling/scale_factors.json`, citations in
`docs/SOURCES.md`):

| Quantity | Factor | Direction |
|---|---|---|
| Cell delay | divide 12.5× | faster |
| **Process derate** | **multiply 1.4× (composes on delay & setup/hold)** | **slower** (pessimism) |
| Cell area | divide 30× | smaller |
| Dynamic power | divide 6.5× | lower |
| Leakage per cell | multiply 20× | **higher** |
| Input pin cap | divide 4× | lower |
| Setup / hold | divide 10× (then ×1.4 derate) | tighter |
| TT voltage / temp | 1.80 V → 0.70 V / 25 °C → 25 °C | substitute |
| SS voltage / temp | 1.60 V → 0.65 V / −40 °C → 125 °C | substitute |

Effective delay scaling (what shows up in fmax(scaled)/fmax(sky130)) =
12.5 / 1.4 ≈ **8.93×**. The validation target window is the full effective
range: **[10/1.5, 15/1.3] = [6.67×, 11.54×]**.

Full theory + citations: [`docs/METHODOLOGY.md`](docs/METHODOLOGY.md).

## What this is NOT

- **Not foundry-correlated.** Statistically consistent with published 7nm
  scaling; not equivalent to TSMC N7, Samsung 7LPP, or Intel 7.
- **Not silicon-validated at 7nm.** Silicon-validated at 130nm (sky130);
  the structural correctness inherits, the numeric magnitudes don't.
- **Not multi-Vt.** Single Vt mix from sky130 sc_hd.
- **Not full OCV.** Process derate is a single uniform multiplier; cut-2
  splits launch vs capture.
- **Not a physical PDK.** No LEF, no GDS, no DRC/LVS.
- **Not for tape-out.**

## Repository layout

```
opencell-7/
├── README.md
├── LICENSE                       Apache-2.0 (matches sky130 upstream)
├── docs/
│   ├── METHODOLOGY.md            scaling theory, derate, corner derivations
│   └── SOURCES.md                citation roster per factor
├── scaling/
│   ├── scale_factors.json        versioned factors + corners block
│   ├── scale_lib.py              sky130 .lib  ->  derived 7nm-class .lib
│   ├── _build_lib.py             wrapper around SkyWater liberty.py
│   └── validate.py               4-way synth+STA driver
├── derived/                      generated outputs (gitignored)
│   ├── sky130_libs/              built sky130 .lib per corner
│   ├── opencell7_tt_0p7v_25c.lib
│   └── opencell7_ss_0p65v_125c.lib
├── reference/
│   ├── counter.v                 validation RTL (preserved from cut-0)
│   ├── fetch_sky130.sh           builds both sky130 corner libs
│   └── sky130/, skywater-pdk-parent/   fetched deps (gitignored)
└── flow/
    ├── synth.tcl                 parameterized Yosys script
    ├── sta.tcl                   parameterized OpenSTA script
    └── constraints.sdc           parameterized SDC (CLK_PERIOD_NS, CLK_PORT)
```

## Prerequisites

- Yosys 0.40+
- OpenSTA (`sta` on PATH)
- Python 3.8+
- GNU Make, Bash, Git

No additional Python packages (the scaler and the SkyWater liberty.py wrapper
are stdlib-only after the dataclasses_json shim).

## Quickstart

```bash
make fetch        # clones sky130 libs + skywater-pdk; builds TT and SS .lib
make scale        # emits opencell7_tt_0p7v_25c.lib + opencell7_ss_0p65v_125c.lib
make validate     # synth+STA the counter on all 4 libs, print ratios
```

`make validate` writes `build/validate_report.json` with the full result set.

## Validation methodology

Both corners use identical factors, so both ratio targets are the same.
A pass requires the empirically measured ratios to land within ±30% of:

| Ratio | Target window |
|---|---|
| fmax(scaled) / fmax(sky130) | [10/1.5, 15/1.3] = **6.67× – 11.54×** (effective delay) |
| area(sky130) / area(scaled) | **25× – 35×** (area factor — derate doesn't apply) |

Off-target results signal that `scaling/scale_factors.json` needs adjusting,
not that the scaler is broken. Re-run `make validate` after any factor change.

## Equivalence verification

`scaling/lec.py` is a one-command tiered LEC driver for any
`(lib, rtl, netlist, top)` triple. Runs the strongest open-source LEC
engines in order (yosys `equiv_simple` → abc `cec` → yosys
`equiv_induct` → abc `dsec` → abc `&equiv`), stops at the first
PROVED, reports verdict + engine + wall time. No simulation, no user
lemmas. See [`docs/EQUIVALENCE_AT_SCALE.md`](docs/EQUIVALENCE_AT_SCALE.md).

Results against the PoC suite (sky130 TT and scaled TT, RTL ↔ mapped):

| Design | Verdict | Engine | Wall time |
|---|---|---|---|
| **counter** (8-bit) | **PROVED** | `yosys_equiv_simple` | 0.2 s |
| **AES-128** (`aes_core`) | **PROVED** | `yosys_equiv_induct` | 637 s |
| **PicoRV32** (no MUL, dualport regs) | **PARTIAL** (depth 9, 2983/3149 cells discharged) | `abc dsec` | 245 s |

PicoRV32 is at the open-source LEC frontier today — `abc dsec` proves
94.7% of register-pair equivalence at induction depth 9, then hits abc's
hardcoded per-frame BMC timeout. The residual miter and continuation
paths (riscv-formal, hierarchical decomposition, commercial LEC) are
preserved at [`build/equiv/picorv32_residual/`](build/equiv/picorv32_residual/).
See METHODOLOGY §8 for the precise framing.

## License

Apache-2.0. Upstream sky130 Apache-2.0 attribution is preserved verbatim in
every `.lib` produced by `scale_lib.py`. See `LICENSE`.

## Repository

github.com/rtoley/opencell-7
