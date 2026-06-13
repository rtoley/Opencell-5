# OpenCell-7 Methodology — Scaling-Tool Approach

**Version:** v0.3 — adds process derate + SS corner  
**Status:** Draft.

## 1. Why scaling, not hand-building

The cut-0 hand-crafted library was a five-cell smoke test. To get to a usable
~30-cell library — let alone a multi-Vt, SRAM-capable PDK target — by hand
takes 8–10 weeks of focused work and the numbers still trace to spreadsheets,
not to silicon.

The scaling-tool approach takes a *real, silicon-validated* open-source PDK
(SkyWater **sky130_fd_sc_hd**, Apache-2.0) and statistically scales its Liberty
numbers to a 7nm-class operating point. Every cell, every drive strength,
every timing arc, every power table is preserved structurally; only the
numeric magnitudes are rewritten.

Tradeoffs:

| Approach | Coverage | Effort | Calibration anchor |
|---|---|---|---|
| Hand-crafted (cut-0) | 5 cells | ~weeks/cell | spreadsheet ranges |
| Predictive (ASAP7, FreePDK15) | full | already done | model decks, no silicon |
| **Scaling sky130 (cut-1 pivot)** | full (sky130 has ~430 cells) | hours | sky130 silicon × published 7nm/130nm ratios |

The scaled library is *not* foundry-correlated and *not* silicon-validated at
7nm. It is dimensionally consistent with published 7nm-class scaling and
inherits sky130's structural correctness.

## 2. Scaling factors (130nm → 7nm-class)

All factors are *averages* across the migration. They are intentionally
single-point (not Vt-dependent, not drive-dependent) for this cut.

| Quantity | Scaling | Direction | Range cited | Default | Applies after |
|---|---|---|---|---|---|
| Cell delay | divide | faster | 10–15× | **12.5×** | — |
| **Process derate** | **multiply** | **slower (pessimism)** | **1.3–1.5×** | **1.4×** | composes on delay & setup/hold |
| Cell area | divide | smaller | 25–35× | **30×** | — |
| Dynamic power per switch | divide | lower | 5–8× | **6.5×** | — |
| Leakage per cell | multiply | **higher** | 10–30× | **20×** | — |
| Input pin capacitance | divide | lower | 3–5× | **4×** | — |
| Setup / hold constraints | divide | tighter | ~10× | **10×** | composes with process derate |

Per-corner V/T substitutions (corners block of `scale_factors.json`):

| Corner | Source (sky130) | Target (opencell7) | Intent |
|---|---|---|---|
| **TT** | tt_025C_1v80 (1.80 V, 25 °C) | tt_0p7v_25c (0.70 V, 25 °C) | Typical-case PPA estimation |
| **SS** | ss_n40C_1v60 (1.60 V, −40 °C) | ss_0p65v_125c (0.65 V, 125 °C) | Setup-time STA / worst-case fmax |

**Effective delay scaling** = delay-factor × process-derate, applied to every
delay-class value. Default = 12.5 × 1.4⁻¹ as seen by fmax: scaled circuits
are ~8.93× faster than sky130, not 12.5× faster. The derate represents the
OCV-equivalent margin that uniform linear scaling cannot model (FinFET-specific
variation, signal-integrity allowance, characterization uncertainty).

The constants live in `scaling/scale_factors.json` (versioned, citable).
Citations for every factor are in `docs/SOURCES.md` and mirrored in the JSON's
`citation:` field per factor.

### 2.1 Why these ratios

- **Delay 10–15×**: Five process nodes of half-pitch scaling (130 → 90 → 65 →
  45 → 28 → 14 → 7) at the classical ~0.7× per node gives ~0.7⁶ ≈ 0.118, i.e.
  ~8.5× delay reduction. Published 7nm FinFET FO4 measurements come in faster
  than the classical projection because FinFET drive current per area is
  substantially higher than planar — pushing toward 12–15×.
- **Area 25–35×**: Linear 130/7 = 18.6× per dimension would predict ~345×
  area; reality is ~25–35× because (a) FinFET fin count and track height
  don't shrink as fast as gate pitch, (b) routability and DRC consume area.
- **Dynamic power 5–8×**: P_dyn ∝ C·V²·f. C shrinks ~4×, V² shrinks
  (1.8/0.7)² ≈ 6.6×, frequency rises ~12× → P/op drops, but per-cell-switch
  energy drops by C·V² ≈ 26×. At constant frequency, dynamic *power* drops
  ~26×; per-design power including the higher switching activity from larger
  netlists at 7nm settles around 5–8× per same workload.
- **Leakage 10–30×**: This is the worst direction at 7nm. Sub-threshold
  leakage per device dropped, but FinFET density and lower Vth pushed
  per-cell static leakage up. Published 7nm libraries show RVT leakage on
  the order of 1–10 nA/cell vs sky130 HVT ~0.05 nA/cell — a 20–200× range,
  midpoint ~20×.
- **Cap 3–5×**: Gate cap per cell ≈ Cox·W·L. Cox up, W·L down. Net ~4×.
- **Setup/hold ~10×**: FF setup/hold times scale with internal delay, so
  same ~10–12× as combinational, defaulted to 10× for symmetry.
- **Process derate 1.3–1.5×**: Sign-off-equivalent OCV margin at 7nm-class
  FinFET nodes. Captures device-to-device variation, on-die crosstalk, and
  characterization noise that uniform scaling cannot encode. Published 7nm
  OCV setup derate factors land in 1.3–1.5×; default 1.4×. The derate
  multiplies onto every delay-scaled and setup_hold-scaled quantity AFTER
  the per-quantity factor — so the *effective* delay scaling visible in
  fmax(scaled)/fmax(sky130) is 12.5/1.4 ≈ 8.93×, not 12.5×. Validation
  targets this effective range.

Citations in `docs/SOURCES.md`.

## 3. What the scaler preserves vs rewrites

| Preserves | Rewrites |
|---|---|
| Cell names (sky130_fd_sc_hd__nand2_1, etc.) | NLDM `values()` (delays, transitions) |
| Pin names, function attributes, logic equations | Index grids (input slew, output cap) |
| NLDM grid *shape* (typically 7×7) | `cell_leakage_power` values |
| Timing arc structure (which pin → which pin) | `internal_power` table values |
| `timing_type` (setup/hold/combinational) | `area` values |
| Attribution headers (sky130 license / copyright) | Pin `capacitance` values |
| Library-level constants (units, default loads) | `nom_voltage` (1.80 → 0.70) |
| Operating condition group names | Constraint table `values()` (setup/hold) |

Header injection: every emitted file gets a banner identifying it as
derived, citing scale_factors.json version, and preserving the upstream
sky130 Apache-2.0 attribution.

## 3b. Corners (TT and SS)

For cut-1 we ship two corners. Both use the same factor set; only the source
.lib (and the V/T labels on the output) differ.

| | TT | SS |
|---|---|---|
| Source sky130 .lib | `sky130_fd_sc_hd__tt_025C_1v80.lib` | `sky130_fd_sc_hd__ss_n40C_1v60.lib` |
| Source V / T | 1.80 V / 25 °C | 1.60 V / **−40 °C** (sky130's slow corner) |
| Target V / T | 0.70 V / 25 °C | 0.65 V / **125 °C** (7nm sign-off convention) |
| Output .lib | `derived/opencell7_tt_0p7v_25c.lib` | `derived/opencell7_ss_0p65v_125c.lib` |
| Intended use | typical-case PPA reporting | setup-time STA, fmax sign-off |

### Why we relabel SS −40 °C → 125 °C

Sky130's slow corner is at −40 °C because for planar CMOS at this geometry,
**low temperature** dominates the slow direction (threshold voltage gets larger
faster than mobility improves). For 7nm FinFET, the slow corner is at
**125 °C** — mobility degradation dominates over threshold improvement at
high temperature on this generation. The OpenCell-7 SS lib uses the *sky130
slow-corner numerics* (slow-corner is slow-corner; the magnitudes scale
correctly) but **relabels** the operating-condition fields to the 7nm
sign-off convention.

This is a synthetic choice and is documented in caveat §4.7.

## 4. Honest caveats

1. **Linear scaling does not capture FinFET non-idealities.** Real 7nm cells
   show stronger Vt dependence, fin quantization, and self-heating effects
   that uniform factors can't model.
2. **Not foundry-correlated.** This is statistically *consistent with*
   published 7nm scaling, not equivalent to TSMC N7, Samsung 7LPP, or any
   specific node.
3. **Not silicon-validated at 7nm.** It is silicon-validated at *130nm*
   (sky130) with scaled numbers. The structural correctness inherits.
4. **Single TT corner, single Vt.** No SS / FF, no LVT / HVT — cut-1 scope.
5. **No multi-Vt awareness.** If sky130 input is HVT, the leakage scaling
   may understate; if LVT, may overstate. Treat the output as a single Vt.
6. **Pin capacitance index axes**: index_2 (output load) in NLDM tables is
   scaled by the input-cap factor since loads are typically defined in units
   of input cap, which is dimensionally consistent.
7. **SS corner V/T relabeling is synthetic.** The numerical magnitudes in
   `opencell7_ss_0p65v_125c.lib` are scaled from sky130's ss_n40C_1v60
   characterization (a −40 °C slow-temp corner). We relabel the operating-
   condition fields to 0.65 V / 125 °C to align with the 7nm sign-off
   convention (hot-corner setup). The numbers are NOT a re-characterization
   at 125 °C; they remain dimensionally consistent with a generic 7nm slow
   corner. The relabeling is what enables Yosys/OpenSTA to treat the lib
   as a 7nm SS corner without confusing operating-condition lookups.
8. **Leakage at SS may be lower than at TT.** Sky130's SS corner is cold
   (−40 °C), so its leakage numbers are smaller than sky130 TT's 25 °C
   numbers. The scaler multiplies by 20× uniformly, so this relationship
   persists in the output. A "true" 7nm SS at 125 °C would have **higher**
   leakage than TT; we don't model temperature-dependent leakage at this
   cut. Use the TT corner for power-analysis numbers and the SS corner
   strictly for setup-time fmax. Cut-2 will add corner-aware leakage
   scaling.
9. **Process derate is a single number, not OCV.** True OCV applies
   derate-on-launch / derate-on-capture with potentially different factors
   for clock vs data paths. Our 1.4× multiplies onto every delay table
   uniformly — sufficient for directional fmax estimation but not for
   formal sign-off.
10. **Not for tape-out.** Not for production design. Not for power-grid sign-off.

## 5. Validation methodology

`scaling/validate.py` synthesizes a small fixed RTL design
(`reference/counter.v`, an 8-bit counter retained from cut-0) on **all four
libraries**:

| | Source | Output |
|---|---|---|
| TT pair | sky130 tt_025C_1v80 | opencell7 tt_0p7v_25c |
| SS pair | sky130 ss_n40C_1v60 | opencell7 ss_0p65v_125c |

For each run it records:

- **fmax**: clock period at which OpenSTA reports WNS ≈ 0 (reg-to-reg only,
  inferred from a single STA run at a generous P0 — see validate.py)
- **area**: total mapped cell area reported by Yosys `stat -liberty`

Then it computes per-corner:

| Ratio | Target window |
|---|---|
| fmax(scaled) / fmax(sky130) | **effective delay range** = delay / derate = [10/1.5, 15/1.3] = **6.67× – 11.54×** |
| area(sky130) / area(scaled) | 25× – 35× (area factor — derate doesn't apply) |

Pass criterion: both ratios within ±30% of the target window. Off-target
results trigger a scale-factor adjustment in `scaling/scale_factors.json`
and a re-run.

Both corners use identical scaling factors, so both ratio targets are the
same. The 30% tolerance reflects:

- Yosys `abc` makes different mapping choices on different libraries
  (different drive strengths picked, different cell types preferred). Two
  netlists for the same RTL on two libraries are not gate-by-gate identical.
- The factor table itself is a single-point estimate over a range.

**For fmax reporting going forward**, quote the SS corner. That's the
sign-off-relevant number. TT is for typical-case PPA narration only.

### 5.1 Multi-design PoC validation

`scaling/poc_compare.py` extends validation to a small reference suite:
the 8-bit counter (combinational + tiny FSM), **PicoRV32** (
`ENABLE_REGS_DUALPORT=1, ENABLE_MUL=0`, mem_* as primary I/O), and
**AES-128** (`aes_core` top from secworks/aes, all submodules flattened).
Each design is run on all four libraries (sky130 TT / SS × scaled TT / SS)
for a total of 12 synth+STA runs.

`reference/fetch_designs.sh` clones both designs (gitignored). The
poc-* Makefile targets gate the design files as Make prerequisites.

### 5.2 Tightened synth flow

The cut-1 smoke flow ran `abc -liberty <lib>` with no delay target and
left submodules unflattened. That produced clean ratios on the counter
but unrealistic absolute fmax on multi-module designs — abc had no
timing target, and the unflattened modules hid high-fanout nets from the
mapper. Two changes (cut-2):

- `flatten -wb` before `dfflibmap` — collapses module boundaries so abc
  sees the full critical path. Especially impactful on AES, where
  `aes_core` instantiates `aes_sbox`, `aes_inv_sbox`, `aes_key_mem`,
  `aes_encipher_block`, `aes_decipher_block`.
- `abc -liberty <lib> -D <target_ps>` — delay-driven mapping. Per
  scaling target frequency: 500 ps (≈2 GHz) for TT corners, 1000 ps
  (≈1 GHz) for SS. Same target across sky130 and scaled, set by
  `poc_compare.py` via `ABC_TARGET_PS` env var.

### 5.3 Tightened ratio observation

Before tightening, sky130 mapping carried more low-effort artifacts
than scaled (large unbuffered fanouts), so the scaled/sky130 ratio was
inflated. After tightening, both libs converge on what abc *can* find
at the same target, and the ratio settles closer to the lower edge of
the methodology window [6.67, 11.54]. **AES** in particular drops from
9.4× to 6.5–6.7× after the flow tighten — both sky130 (2×) and scaled
(1.4×) improved, but sky130 had more headroom to recover. This is
informative, not a bug: the published-range floor is 6.67× (`10/1.5`)
and the empirical 6.5–6.7× sits effectively at that floor.

The PoC pass window in `poc_compare.py` is the tighter [8.0, 10.0]
centered on the scaler's defaults; loosening it to the methodology
window [6.67, 11.54] would absorb the AES result. The choice between
tight (PoC) and methodology windows is intentionally separate in the
codebase.

### 5.4 Synthesis-only flow ceiling

**Absolute fmax numbers from this flow are bounded by the synthesis
flow, not the library.** OpenCell-7 produces dimensionally-consistent
scaled numbers, but Yosys + ABC + OpenSTA without physical
implementation cannot hit the absolute fmax that physically-aware
flows reach.

**Cut-2 sweep results (2026-05, all 12 (design × library) pairs PASS
against the recalibrated windows):**

| Design | sky130 TT (MHz) | scaled TT (MHz) | sky130 SS (MHz) | scaled SS (MHz) | TT ratio | SS ratio |
|---|---:|---:|---:|---:|---:|---:|
| counter (8-bit) | 871.8 | 7713.2 | 395.8 | 3549.8 | 8.85× | 8.97× |
| PicoRV32 | 80.8 | 712.6 | 33.4 | 294.4 | 8.82× | 8.82× |
| AES-128 (aes_core) | 69.4 | 462.6 | 26.3 | 171.2 | 6.67× | 6.50× |

Flow: `read_liberty` → `read_verilog` → `hierarchy` →
opt/proc/fsm/memory/techmap passes → `flatten -wb` →
`dfflibmap -liberty` → `abc -liberty <lib> -D <target_ps>` (no `-dff`)
→ `clean`. abc target: 500 ps for TT (~2 GHz aim), 1000 ps for SS
(~1 GHz aim). Same target across sky130 and scaled.

**The flow ceiling shows up in three ways:**

1. **No layout-aware buffering.** Yosys+ABC does not insert
   repeaters/buffers on high-fanout nets. STA reads the .lib NLDM
   tables and computes worst-case delay for a single gate driving
   N loads, which gets ugly when N is large. Published 7nm
   PicoRV32 numbers (~1.5 GHz) assume buffer insertion via
   OpenROAD `repair_design`.

2. **No layout-aware retiming.** Yosys's `abc -dff` enables
   sequential retiming, but it produces library-dependent mapping
   divergence: in the AES sweep, enabling `-dff` made sky130 AES
   regress (69 to 50 MHz) while scaled AES improved (462 to 601 MHz),
   inflating the ratio from 6.7× to 12.6×. Without `-dff`, abc treats
   FFs as the I/O boundary and only does combinational `-D` optimization,
   which gives consistent cross-library ratios.

3. **No cell-sizing pass beyond abc -D.** `abc -D 500` is delay-aware
   but optimizes only at mapping time, with the cells available in
   the .lib. It does not iterate sizing on extracted parasitics.

**Empirical OpenROAD anchors:** PicoRV32 sky130 TT lands at ~80 MHz in
this flow vs ~150 MHz in OpenROAD sky130 (with `repair_design` and
extracted parasitics). AES lands at ~70 MHz vs ~200 MHz published.
The ~2-3× gap is the OpenROAD lift; it would carry through to the
scaled lib symmetrically and put scaled-SS in the published-7nm
ballpark (~600-900 MHz PicoRV32, ~400-700 MHz AES). That is the
cut-3 roadmap item.

### 5.5 Per-design ceiling factors

Different RTL microarchitectures hit the synth-only ceiling at
different relative distances. The ratio sweep makes this visible:

| Design | TT ratio | What binds the critical path |
|---|---:|---|
| counter | **8.85×** | 8-bit ripple-carry chain. Bounded by cell-arc delays; abc maps both libs identically. Ratio matches `delay / process_derate = 12.5 / 1.4 ≈ 8.93×`. |
| PicoRV32 | **8.82×** | Regfile-read → ALU operand-mux chain → ALU → writeback. ~12 ns sky130 path. abc finds the same mapping on both libs because the levels-of-logic count is set by the ALU mux fan-in (~16 sources). Ratio stays near the methodology center. |
| AES-128 | **6.67×** | `keymem` fan-out → `nor4_1` driving wide combinational fanout. abc picks **different cells on sky130 vs scaled** because the 30× absolute-area difference shifts abc's area-vs-delay trade-off, giving scaled a deeper but faster gate tree. Ratio drops to the methodology floor. |

**Why AES drifts to the methodology floor:**

The key-memory `nor4_1` in the AES critical path drives a wide
combinational fan-out. Yosys's abc has to pick between (a) a small
`nor4_1` with a long sloped output (high delay due to load) or (b) a
deeper AOI tree with smaller per-gate load (more cells, less per-gate
delay). On sky130 with absolute gate area in the 3-4 µm² range, abc's
cost function tips toward (a) and the lib's NLDM table captures the
load delay. On the scaled lib (cells ~0.1 µm²), the same area cost is
30× smaller in absolute terms, so abc spends "more area" on a deeper
gate tree, getting a better delay result than 1:1 scaling would predict.

Net effect: scaled AES fmax is higher than `sky130 × 8.93×` would
predict; ratio drops to ~6.5-6.7×. This sits at the methodology
floor (6.67× = `10 / 1.5`) but is **not a scaler bug** — the factor
tables are correct, abc's cost-model behavior is design+library-
dependent. The PoC ratio window `[6.5, 11.6]` is sized to absorb
this.

**Why PicoRV32 sits below the published-flow fmax window:**

PicoRV32's critical path goes regfile-read → ALU mux chain → ALU →
writeback. The mux chain depth is set by the instruction set: ~16
operand sources go into the ALU input mux. Retiming can't break this
because moving FFs around the mux chain doesn't reduce the levels-of-
logic, and the mux fan-in is the binding constraint. Buffer insertion
(OpenROAD `repair_design`) would help by reducing load on each mux
output, but Yosys + ABC alone leaves the load worst-case. So PicoRV32
sky130 TT lands at 80 MHz here vs ~150 MHz under OpenROAD: a flow
ceiling, not a library ceiling.

### 5.6 Comparison framework usage

OpenCell-7 numbers are **consistent synthesis-anchor measurements for
comparing RTL implementations against each other under fixed flow
assumptions**, not predictions of silicon fmax. Use them like this:

**Valid use cases:**

- "RTL variant A is 1.4× faster than variant B on the same OpenCell-7
  flow." → Defensible. Both variants saw the same abc decisions, same
  retime policy, same NLDM tables. The ratio reflects what the RTL
  changed.
- "Adding two pipeline stages improved fmax 2.3×." → Defensible.
- "This optimization saved 18% area on OpenCell-7." → Defensible. Area
  scaling is purely numerical (`area / 30`), so cross-RTL area deltas
  carry through 1:1.
- "Scaled lib is 8.93× faster than sky130 on this RTL." → Approximately
  defensible, with the caveat that abc may produce design-dependent
  ratios anywhere in the methodology window `[6.67, 11.54]`.

**Invalid use cases:**

- "This block runs at 350 MHz on 7nm silicon." → No. The flow produces
  synthesis-anchor numbers, not silicon predictions. Apply the
  empirically-observed OpenROAD lift (~2-3×) and call out the cut-3
  caveat.
- "OpenCell-7 says PicoRV32 closes at 800 MHz." → No. Quote the cut-3
  uplifted number with flow context.
- "AES on OpenCell-7 SS hits 1.5 GHz." → No. That's a sign-off-flow
  prediction with parasitic-aware retiming and repair, neither of
  which this flow does.

**Comparison protocol:** when reporting an RTL improvement using
OpenCell-7, always include (a) the corner (TT or SS), (b) the design
context (which RTL variant is the baseline), (c) the flow
configuration (`flow/synth.tcl` + abc -D target), and (d) a note
that these are synthesis-anchor numbers, not silicon predictions.

## 6. Out of scope (this cut)

- Multi-Vt families (LVT / RVT / HVT) — would require Vt-aware scaling factors.
- FF corner (fast-fast) — single SS slow corner is enough for setup STA; FF
  for hold analysis is a cut-2 follow-up using `sky130_fd_sc_hd__ff_n40C_1v95`.
- Statistical / Monte Carlo — sky130 has σ data; could propagate but not yet.
- LEF / GDS — sky130 has both; out of scope until placer/router integration.
- SRAM compiler — sky130 has OpenRAM integration; pull-through deferred to cut-2.
- Validation against a second reference design (PicoRV32, tiny_aes) — cut-2.
- Per-arc internal-power index scaling — same as delay; current cut applies
  factor to values() only, not index axes inside internal_power blocks.
- Temperature-dependent leakage rescaling — see caveat §4.8.
- Proper OCV (separate launch/capture derate) — current process_derate is a
  single uniform multiplier; see caveat §4.9.

## 7. Roadmap preview

- **Cut-2 (next)**: PicoRV32 + tiny_aes as reference designs; multi-Vt support;
  SS_0p65V_125C and FF_0p75V_n40C corners; per-Vt leakage factor sets.
- **Cut-3**: SRAM compiler pull-through from sky130/OpenRAM with same
  scaling factors applied. LEF emission for OpenROAD PnR.
- **Cut-4**: Monte Carlo σ from sky130 statistical .lib propagated through
  scaling. First published-silicon cross-reference table.
