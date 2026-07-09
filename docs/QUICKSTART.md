# Quickstart — run it yourself (no agent required)

This is a **statistical** SDK: it gives you a representative *feel* of an
advanced-node (7nm / 5nm-class) design flow when you don't have access to a real
foundry PDK. It is **not** sign-off — the flow stops at a post-CTS, router-free
statistical endpoint (synth → floorplan → place → CTS → RC-estimated timing).
Everything below is plain shell/`make`/`python` — no agent, no magic.

Both decks are open, derived by scaling the silicon-validated SkyWater **sky130**
PDK (Apache-2.0):

| deck | node feel | ships in the repo? |
|---|---|---|
| **opencell7** | 7nm-class | yes — turnkey, run immediately |
| **opencell5** | 5nm-class | built in one command (below) |

---

## 0. Prerequisites (once)

- **Docker** — the flow runs OpenROAD/ORFS in a container:
  ```bash
  docker pull openroad/orfs:latest
  ```
- **Python 3**, **make**, **git**. On a memory-constrained host see
  `docs/RUN_ORFS.md` (run one design at a time; cap synth memory).

Clone the repo and `cd` into it. All commands are run from the repo root.

---

## 1. Run opencell-7 (turnkey — no build needed)

The opencell-7 deck is committed, so a fresh clone runs it directly. Drive any
design to the statistical endpoint:

```bash
flow/run_orfs.sh opencell7 gcd cts        # gcd is a tiny bundled design
```

Read its PPA (area, fmax, power, buffering) — correlated against asap7 (a 7nm
predictive PDK bundled in the ORFS image):

```bash
flow/statppa.py gcd                        # default: asap7 vs opencell7
```

---

## 2. Build opencell-5 (5nm-class) — one command

opencell-5 is the same recipe one node tighter (see
`scaling/scale_factors_5nm.json`). It is built *from* opencell-7, so it inherits
all of opencell-7's fixes.

```bash
make fetch                                 # one-time: fetch the sky130 source .lib
bash scaling/build_opencell5.sh gcd d16 picorv32   # build deck + wire these designs
```

`build_opencell5.sh` scales the lib, grid-locks the LEF (`scaling/gridlock_lef.py`
— required so placement stays legal at the tighter site pitch), scales the PDN /
track / RC tcl, and wires each named design under `designs/opencell5/`.

---

## 3. Run opencell-5 and see the node step

```bash
flow/run_orfs.sh opencell5 gcd cts                       # run a design on 5nm-class
flow/statppa.py --platforms opencell7 opencell5 gcd      # correlate 5nm vs 7nm
```

The correlation reports the signed gap `(opencell5 − opencell7)/opencell7`.
Expect **~1.7× smaller area** and (on tight-clock, cell-dominated designs)
**~1.1× higher fmax** — a clean one-node step. Area is the trustworthy signal;
for a fair fmax you must compare at a matched *tight* clock (see §5).

---

## 4. Add your own design

1. Put the RTL under `designs/src/<yourdesign>/`.
2. Create `designs/opencell7/<yourdesign>/config.mk` (copy an existing one; set
   `DESIGN_NAME`, `VERILOG_FILES`, `SDC_FILE`, `CORE_UTILIZATION`).
3. Wire it for opencell-5 too:
   ```bash
   bash scaling/build_opencell5.sh <yourdesign>          # (re)wires designs/opencell5/<yourdesign>
   ```
4. Run and correlate exactly as above.

The two bundled reference cores — `picorv32` (RISC-V) and `aes` — need their RTL
fetched first: `make fetch-designs`.

---

## 5. Notes / gotchas

- **`LEC_CHECK=0`** is set by default (the image's formal-LEC step SIGILLs on
  non-AVX-512 CPUs). Leave it. See `docs/RUN_ORFS.md`.
- **One design at a time.** Concurrent ORFS containers can race at CTS and can
  OOM a small host.
- **Fair fmax = matched tight clock.** Designs shipped with loose SDCs (e.g.
  picorv32 at 1 ns) report a relaxed, un-pushed fmax. To measure a design's true
  frequency floor: `flow/tighten.py opencell5 <design>` (and the same on
  opencell7), then compare the floors.
- **Endpoint is post-CTS, router-free** by design — do not expect DRC-clean GDS.
  The statistics (area, fmax, power) live at CTS; both decks reach it cleanly.

That's the whole flow: `make fetch` → `build_opencell5.sh` → `run_orfs.sh` →
`statppa.py`. No agent involved.
