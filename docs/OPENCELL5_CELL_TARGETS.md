# opencell-5 cell-area target spec + Task-C correlation matrix

The measured justification for opencell-5 and its per-family cell-area
construction targets. The gap is **structural cell topology**, not a tunable
scale factor — it cannot be closed on scaled-sky130 and *requires* opencell-5's
from-scratch (or per-family re-laid) cells.

## 1. Per-family area measurement (this repo's libs)

Dominant-cell area, opencell-7 (uniform area_factor=56 scaled sky130) vs asap7
RVT TT, µm²:

| family | opencell-7 | asap7 | ratio oc7/asap7 |
|---|---|---|---|
| INV   | 0.0670 | 0.0437 | 1.53 |
| NAND2 | 0.0670 | 0.0875 | 0.77 |
| NOR2  | 0.0670 | 0.0875 | 0.77 |
| XOR2  | 0.1564 | 0.1750 | 0.89 |
| DFF   | 0.3575 | 0.2916 | 1.23 |

- **Aggregate** ratio mean ≈ 1.04 → uniform scaling is well-centered.
- **Per-family** spread 0.77–1.53 (2×) → the mix is wrong cell-by-cell.

opencell-7 has INV = NAND2 = NOR2 = 0.0670 because sky130's basic gates share a
1-site footprint; asap7's INV is ~half its NAND2. No uniform or per-family
*divisor* on scaled-sky130 can make INV structurally smaller than NAND2 when
they start equal. The **DFF being 1.23× oversized** is the leading cause of the
flop-heavy correlation gap below.

## 2. Task-C correlation matrix (post-CTS, router-free statistical endpoint)

> **CORRECTED 2026-07-08.** The old −18 to −20% flop-chain gap (the "was" column)
> was measured 2026-06-13, *before* the xnor3 `dont_use` fix (commit 86c6210,
> 2026-06-14). That fix — abc was mis-selecting sky130's slow xnor3 to reduce
> logic depth, lengthening the critical path — closed the gap. The current
> numbers below are a fresh full-set run on HEAD.

opencell-7 vs asap7 via `flow/statppa.py`, open designs only. **Fresh HEAD run
(2026-07-08), both platforms:**

| design | character | oc7 fmax | asap7 fmax | fmax gap | (was, pre-fix) |
|---|---|---|---|---|---|
| aes | logic | 2672 | 2632 | **+1.5%** | +0.7% |
| picorv32 | logic | 1527 | 1562 | **−2.2%** | −2.2% |
| d8 | flop-chain | 7406 | 7690 | **−3.7%** | −5.9% |
| d16 | flop-chain | 6314 | 6478 | **−2.5%** | −20.1% |
| d32 | flop-chain | 5014 | 5512 | **−9.0%** | −19.6% |
| d48 | flop-chain | 4813 | 4612 | **+4.3%** | −18.8% |
| gcd | tiny (220 cells) | 2931 | 2629 | +11.5% | −15.7% |

**Pattern (corrected):** logic AND flop-chain designs now land within ~±9% (d48
even ahead; gcd a noisy +11.5% tiny-design outlier). The previously-claimed
"oversized DFF → −19% flop-heavy fmax" causal chain does **not** survive the
corrected data — opencell-7 statistically matches asap7 on fmax across the board.
The old gap's root cause was the xnor3 mis-selection, not the DFF.

**Consequence for opencell-5:** the *fmax*-recovery motivation is moot. The
remaining, still-valid driver is the §1 **area/density** gap (oversized DFF,
structural INV=NAND2=NOR2) — an area-efficiency goal, not a speed one.

Buffering note: flop chains insert 0 `repair_design` buffers on *both* platforms
(short flop-to-flop paths, no high-fanout data nets), so the comparison is
apples-to-apples; statppa's generic "NO BUFFERS — unreliable" warning is not an
opencell-7-specific under-buffering. Logic designs are properly buffered (oc7:
aes 272, picorv32 358 buffers).

## 3. opencell-5 work order

0. **Reproduce the opencell-7 baseline FIRST (before changing any cell).** In
   the fresh repo, run the opencell-7 flow as-is — `flow/statppa.py` across the
   open designs — to (a) confirm the clean checkout runs end-to-end and (b)
   reproduce the §2 baseline matrix (logic AND flop-chains within ~±9% — the
   corrected, post-xnor3-fix numbers, NOT the −18/−20% "was" column). This is the
   regression baseline every opencell-5 retune is measured against. No cell
   changes until this baseline is captured and matches §2.
1. **Sequential family first (area, not speed).** Build the DFF (and the rest of
   the SEQ family) to asap7's per-family area + characterize timing against a real
   7nm-class reference. Motivation is now **die-area/density** (§1: DFF 1.23×
   oversized), NOT fmax recovery — the flop-chain *timing* gap is already closed
   (§2, post-xnor3-fix). A right-sized DFF shrinks flop-heavy die area; whether
   that buys measurable fmax on top of today's parity is an open question to
   re-measure, not an assumption.
2. **Combinational cells** to the per-family targets in §1 (INV especially:
   structurally smaller than NAND2, which scaled-sky130 cannot express).
3. **Re-validate** with `flow/statppa.py` across the design set; bar is ±10%
   including flop-heavy designs.

## 4. What carries over from opencell-7 (proven, unchanged)

- The ORFS statistical flow + router-free post-CTS endpoint (not sign-off).
- The fanout fix (`scaling/set_fanout_load.py`, asap7-faithful
  `default_fanout_load=1`) — required for honest fmax regardless of cell areas.
- The asap7-vs-opencell correlation harness (`flow/statppa.py`).
