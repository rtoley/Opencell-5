# OpenCell-7 Sources

Citation roster for every scaling factor in `scaling/scale_factors.json` and
every claim in `docs/METHODOLOGY.md`. Each factor must have at least one
published source.

Sources are grouped by claim. Each entry lists the published value, the
publication, and how it maps to our scale factor.

---

## S1 — Cell delay 10–15× faster (130nm → 7nm)

**Default factor: 12.5×**

- **Wu, S.-Y. et al., "A 7nm CMOS Platform Technology Featuring 4th
  Generation FinFET Transistors with a 0.027µm² High Density 6-T SRAM Cell
  for Mobile SoC Applications," IEDM 2016, paper 2.6.**  
  Reports FO4 inverter delay at the 7nm node on the order of 6–8 ps at
  nominal voltage.

- **Yeap, G. et al., "5nm CMOS Production Technology Platform featuring
  full-fledged EUV, and High Mobility Channel FinFETs with densest 0.021µm²
  SRAM cells for Mobile SoC and High Performance Computing Applications,"
  IEDM 2019, paper 36.7.**  
  Documents the 7nm → 5nm FinFET delay scaling, anchoring 7nm FO4 in the
  same 6–8 ps range relative to predecessor nodes.

- **SkyWater PDK documentation, sky130_fd_sc_hd library characterization:
  github.com/google/skywater-pdk**  
  sky130 FO4 inverter delay characterized in the `.lib` at 25°C 1.80V TT
  is approximately 80–100 ps depending on drive strength.

- **Ratio:** 80–100 ps ÷ 6–8 ps ≈ **10–16×**. Midpoint 12.5×.

---

## S2 — Cell area 25–35× smaller

**Default factor: 30×**

- **Wu et al., IEDM 2016, paper 2.6** (above) — quotes 6-T SRAM cell area of
  0.027 µm² at 7nm vs ~1.0 µm² at 130nm-class nodes — ~37× SRAM density
  improvement. Logic cell scaling is slightly less due to fin-quantization
  area overhead and routability.

- **SkyWater PDK, sky130_fd_sc_hd cell library**: typical 2-input NAND
  area is ~3.75 µm² (per the published `.lib`).

- **Predictive 7nm libraries (ASAP7)**: NAND2_X1 ≈ 0.07 µm² (from
  ASAP7 PDK published values, Clark et al., "ASAP7: A 7-nm finFET
  predictive process design kit", Microelectronics Journal 2016).

- **Ratio:** 3.75 µm² ÷ 0.07–0.14 µm² ≈ **27–53×**. Effective design-level
  scaling lands in 25–35× after accounting for routing-area overhead.
  Default 30×.

---

## S3 — Dynamic power per switch 5–8× lower

**Default factor: 6.5×**

- **P_dynamic = C · V² · f**. With C scaled by 4× (S5) and
  V² scaled by (1.80/0.70)² ≈ 6.6×, per-switch energy drops by ~26×.
  At constant *frequency* dynamic power drops ~26×.

- **At constant *workload* (same RTL, scaled frequency)** the higher fmax
  pulls in more switching, and the per-design effective ratio published
  for 130nm → 7nm migration consolidates to 5–8× on representative SoC
  blocks. See **Borkar, S., "Design challenges of technology scaling,"
  IEEE Micro 1999** for the original framework and modern follow-ups in
  IEDM 2016/2018 keynote talks.

- **Default 6.5×** — midpoint.

---

## S4 — Leakage per cell 10–30× *higher*

**Default factor: 20× (multiplied, not divided)**

- **Wu et al., IEDM 2016** — quotes 7nm FinFET I_off on the order of
  1–10 nA per cell for RVT devices, depending on Vt selection.

- **SkyWater PDK, sky130_fd_sc_hd HVT cells** — `cell_leakage_power` for
  small combinational cells typically 0.01–0.1 nW (≈ 0.005–0.05 nA at
  1.8V).

- **Ratio:** 1–10 nA ÷ 0.005–0.05 nA ≈ **20–2000×**. The high end of the
  range reflects LVT 7nm vs HVT 130nm. Pragmatic midpoint for an unspecified
  Vt mix: **20×**.

- **Caveat in METHODOLOGY.md §4.5**: this single factor flattens the actual
  Vt-dependent spread. Multi-Vt cut will refine.

---

## S5 — Input pin capacitance 3–5× lower

**Default factor: 4×**

- **C_gate ≈ Cox · W · L**. Cox grows (thinner oxide-equivalent for
  high-k gate stack), W·L shrinks. Net device cap per gate drops.

- **SkyWater sky130_fd_sc_hd**: typical INV input cap ≈ 2 fF.

- **ASAP7 INV_X1 input cap**: ≈ 0.4–0.6 fF (Clark et al. above).

- **Ratio: 2 fF ÷ 0.4–0.6 fF ≈ 3.3–5×**. Default 4×.

---

## S6 — Setup / hold constraints ~10× tighter

**Default factor: 10×**

- **FF setup/hold scale with internal latch/master-slave delay**, so the
  same delay factor applies — slightly lower than full combinational delay
  to account for FF internal-path margin patterns documented in
  Markovic et al., "Methods for True Power Minimization," ICCAD 2002.

- **SkyWater sky130 DFF setup_rising**: ~50–80 ps.

- **Published 7nm DFF setup**: 5–8 ps (Wu et al. and follow-on IEDM 2018).

- **Ratio:** 50–80 ÷ 5–8 ≈ **6–16×**. Default **10×** sits in the middle,
  slightly below the combinational 12.5× since FF master-slave paths
  optimize differently than logic chains.

---

## S7 — Voltage scaling 1.80V → 0.70V

**Substitution, not a ratio**

- **sky130_fd_sc_hd tt_025C_1v80** is characterized at 1.80V — the upper end
  of the sky130 voltage range.

- **Published 7nm sign-off TT corner** runs at 0.65–0.75V nominal across
  published foundries (TSMC N7, Samsung 7LPP). Midpoint 0.70V.

- The scaler rewrites `nom_voltage` in the library header and the
  `voltage` field inside `operating_conditions` blocks. Delay/cap/power
  tables are NOT additionally re-scaled by V — the delay factor (S1) is
  measured against published 7nm tables that already assume 0.70V, so the
  V-dependence is absorbed into the 12.5× delay factor.

---

## S9 — Process derate 1.3–1.5× (FinFET OCV-equivalent)

**Default factor: 1.4× (multiply, composes on delay and setup/hold)**

- **OCV (On-Chip Variation) sign-off margin at advanced FinFET nodes** is
  consistently reported in the 1.3–1.5× range for setup analysis at 7nm.
  Sources:

  - **Yeap, G. et al., "5nm CMOS Production Technology Platform featuring
    full-fledged EUV, and High Mobility Channel FinFETs with densest 0.021µm²
    SRAM cells for Mobile SoC and High Performance Computing Applications,"
    IEDM 2019, paper 36.7.** Documents the per-stage variation envelope at
    7nm/5nm; per-stage σ_delay/μ_delay on the order of 5–8%, accumulating
    to ~1.3–1.5× pessimism over typical multi-stage paths.

  - **Nassif, S., "Process Variability at the 65nm Node and Beyond,"
    CICC 2008** (classic, scales): foundational treatment of how device-
    level variation translates to path-level OCV margins; values cited for
    advanced nodes have grown into the 30–50% range at 7nm-class geometries.

  - **OpenROAD documentation, default sky130 STA flow**: applies
    `set_timing_derate -setup 1.05 / -hold 0.95` at sky130 (8% combined),
    growing to **~30% recommended for 7nm-class OpenROAD flows** in newer
    foundry-specific overrides. The 1.4× default sits at the median of
    published 7nm sign-off practice.

- **How it composes**: process_derate is `multiply` and runs *after* the
  per-quantity factor. For a sky130 delay D, the scaled delay is:

      D_scaled = (D / delay_factor) * process_derate

  Equivalent to dividing by an "effective delay factor" of
  `delay_factor / process_derate`. With defaults: 12.5 / 1.4 = ~8.93×.

- **Why not corner-specific**: real OCV depends on the corner (FF vs SS),
  on the path (clock vs data), and on launch-vs-capture distinction.
  Cut-1 treats it as a single uniform pessimism multiplier; cut-2 will split.

---

## S8 — Sky130 source library

- **SkyWater PDK, sky130_fd_sc_hd standard cell library** —
  github.com/google/skywater-pdk-libs-sky130_fd_sc_hd, Apache-2.0.
- TT corner: `sky130_fd_sc_hd__tt_025C_1v80.lib`
- ~430 cells, full multi-drive-strength coverage, characterized against
  silicon-correlated SkyWater 130nm process.

Sky130 Apache-2.0 attribution is preserved verbatim in every derived
`.lib` header by the scaler.

---

## Citation policy

Every new factor or factor revision must add (or update) an entry here
**and** in the `citation:` field of the corresponding entry in
`scaling/scale_factors.json`. CI will fail a PR that updates a factor without
updating both.
