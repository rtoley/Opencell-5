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

opencell-7 vs asap7 via `flow/statppa.py`, open designs only:

| design | character | oc7 fmax | asap7 fmax | fmax gap |
|---|---|---|---|---|
| aes | logic | 2651 | 2632 | **+0.7%** |
| picorv32 | logic | 1527 | 1562 | **−2.2%** |
| d8 | flop-chain | 7221 | 7671 | −5.9% |
| gcd | tiny (220 cells) | 2216 | 2629 | −15.7% |
| d48 | flop-chain | 3762 | 4634 | **−18.8%** |
| d32 | flop-chain | 4424 | 5500 | **−19.6%** |
| d16 | flop-chain | 5117 | 6408 | **−20.1%** |

**Pattern:** logic-dominated designs land within ±3%; flop-dominated designs
(the d-sweep is literally flop chains) sit at a consistent **−18 to −20%**. Two
independent measurements, one root cause: the oversized DFF (§1) inflates
flop-heavy die area → longer wires → ~−19% fmax (§2). gcd is a noisy outlier
(220 cells; tiny-design variance + a config-target mismatch).

## 3. opencell-5 work order

0. **Reproduce the opencell-7 baseline FIRST (before changing any cell).** In
   the fresh repo, run the opencell-7 flow as-is — `flow/statppa.py` across the
   open designs — to (a) confirm the clean checkout runs end-to-end and (b)
   reproduce the §2 baseline matrix (logic within ±3%, flop-dominated −18 to
   −20%). This is the regression baseline every opencell-5 retune is measured
   against. No cell changes until this baseline is captured and matches §2.
1. **Sequential family first.** Build the DFF (and the rest of the SEQ family)
   to asap7's per-family area + characterize timing against a real 7nm-class
   reference. This single family closes most of the flop-heavy gap — moving the
   −19% cohort toward the logic cohort's ±3%.
2. **Combinational cells** to the per-family targets in §1 (INV especially:
   structurally smaller than NAND2, which scaled-sky130 cannot express).
3. **Re-validate** with `flow/statppa.py` across the design set; bar is ±10%
   including flop-heavy designs.

## 4. What carries over from opencell-7 (proven, unchanged)

- The ORFS statistical flow + router-free post-CTS endpoint (not sign-off).
- The fanout fix (`scaling/set_fanout_load.py`, asap7-faithful
  `default_fanout_load=1`) — required for honest fmax regardless of cell areas.
- The asap7-vs-opencell correlation harness (`flow/statppa.py`).
