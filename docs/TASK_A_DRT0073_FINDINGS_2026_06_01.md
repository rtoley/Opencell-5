# Task A — DRT-0073 root-cause analysis & partial fix (2026-06-01)

Status: **gcd × opencell-7 v0.4 NOT yet at 6_finish.** Pin-access failures
reduced from **229 → 62 (73%)** by two correct platform fixes. Residual ~17%
of pins still fail `DRT-0073 (No access point)`; root cause narrowed but not
fully closed. aes/picorv32 blocked on the same issue.

## Baseline established
- Stock `sky130hd` gcd routes cleanly to `6_final` in the same
  `openroad/orfs:latest` image (0 DRT-0073). Flow/version are fine.
- Our scaled cell geometry is **ratio-identical to stock** (verified buf_4
  pin A, dfxtp D, li1/mcon/met1 widths, site — all scale by ~7.4833).
- `designs/opencell7/gcd/config.mk` is byte-identical to stock (CORE_UTILIZATION=40).

## Fix 1 — make_tracks.tcl was at the wrong scale (LANDED, correct)
`scaling/scale_factors.json` area factor was retuned 40 → 56
(linear 6.325 → 7.4833), and the LEF was regenerated at 56, but
`make_tracks.tcl` was left at the **area-40** scale (li1 x_pitch 0.07273 =
0.46/6.325). Tracks didn't match the cell/site grid.
- Corrected to area-56: li1 0.0615, met1 0.0454, etc. — matching LEF layer
  PITCH and SITE width exactly.

## Fix 2 — row height not an integer multiple of met1 pitch (LANDED, correct)
The dominant cause. Stock row height = exactly 8 × met1 pitch
(2.72 = 8×0.34), so the met1 access track sits at a constant cell-relative Y
in every row. In ours, SIZE-snap gave row height **0.3635** while met1 pitch
rounded to **0.0454** → 8×0.0454 = **0.3632**, off by **3 DBU/row**. The met1
track drifts out of each pin's via-access window (pin height − 2×mcon_half ≈
92 DBU) after a few rows → universal failure.

Fix applied:
- Rescaled all cell-LEF **Y** coords by 3632/3635 (cells now 0.3632 / 0.7264
  tall) → `scaling/snap_lef_to_mfgrid.py` companion logic, inline.
- SITE `unithd` 0.3635→0.3632, `unithddbl` 0.7270→0.7264 in tech LEF.
- make_tracks + tech-LEF PITCH set to **exact integer DBU multiples**:
  met3 0.0908 (=2×met1), met4 0.1230 (=2×li1), met5 0.4540 (=10×met1).
- (Also floored tech-LEF `ENCLOSURE` values to the 0.0001 grid — harmless;
  TritonRoute skips these LEF58 enclosures anyway, "DRT-0349".)

Effect: 229 → 62 failures. Row-drift component eliminated.

## Residual (62 failures) — NOT yet solved
Characterised on the post-fix `4_cts.odb`:
- **Util-invariant**: util=40 → 63, util=25 → 66. Not congestion.
- **Orientation-neutral**: 32 R0 / 30 MX (∝ totals).
- **~uniform ~17% of all pins**, ~2 per (master,pin), spread across nearly
  every master (nand2/A, dfxtp/D, buf_4/A, xor2/A, …); count per row ∝ cells
  in that row.
- Failing pins **do** have met1 tracks in their Y-window and are geometrically
  identical (by ratio) to stock pins that route. A pure "li1 track must be in
  the X cut-window" model is **disproved** by stock (stock dfxtp D has no li1
  track in its X cut-window either, yet routes).

Interpretation: a marginal access-point/via-legality condition at the
aggressive absolute scale (DBM 10000, ~7.48× shrink) that fails ~17% of pins
on manufacturing-grid rounding. The exact FlexPA rejection reason was not
extracted (DRT debug level 1 gives no per-pin detail; the dbAccessPoint
swig API in this build did not expose access flags cleanly from Tcl).

## Recommended next steps (for a focused follow-up)
1. **From-stock anisotropic re-scale** of the cell + tech LEF: pick X-factor
   and Y-factor so site W and H are exact integer-DBU multiples of the li1 and
   met1 pitches respectively, and **snap each li1 pin's center to the nearest
   (li1_x_track, met1_y_track) intersection** so every pin has a guaranteed
   on-grid via access. Keep area factor ≈ 56 (7.4797 × 7.4890 = 56.02).
   This rebuilds `scale_lef.py` with grid-lock constraints rather than
   independent per-value rounding (the source of every rounding defect found).
2. Or extract the FlexPA rejection reason directly (build OpenROAD with
   `set_debug_level DRT pa N` that prints per-AP validity, or inspect
   `dbAccessPoint::getAccesses` via Python odb) to pinpoint the exact rule.
3. Verify with stock `sky130hd` extracted to `/tmp/stock130` (tlef + merged
   LEF + config.mk) — used throughout this analysis as the golden reference.

## Artifacts
- Best run: `build/orfs_opencell7_gcd_yfix/` (62 failures, reaches 4_cts).
- Backups: `platforms/opencell7/lef/*.preyfix.bak`, `*.preenc.bak`,
  `make_tracks.tcl.area40.bak` (local only, not committed).
