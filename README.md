# OpenCell-5

A **5nm-class statistical SDK** — an open, IP-free standard-cell deck that gives
you a representative *feel* of a 5nm design flow when you don't have access to a
real foundry PDK. It is derived by **statistical scaling** of the
silicon-validated SkyWater **sky130** PDK (Apache-2.0), and it runs the full
open **OpenROAD/ORFS** flow: synth → floorplan → place → CTS.

**→ Just want to run it? See [`docs/QUICKSTART.md`](docs/QUICKSTART.md).** The
deck ships committed; a user never touches sky130.

```bash
docker pull openroad/orfs:latest
flow/run_orfs.sh opencell5 gcd cts          # run a design to the statistical endpoint
flow/ppa.py opencell5 gcd                    # read area / fmax / power
```

## What this is

OpenCell-5 rewrites every numeric field of the sky130 cell library — delays,
transitions, setup/hold, leakage, power, cap, area — and the physical LEF
geometry to a 5nm-class operating point, then drives real designs through
OpenROAD to a **post-CTS, router-free statistical endpoint** (a real clock tree +
RC-estimated timing). That endpoint is where the honest PPA lives; both this deck
and its 7nm sibling reach it cleanly.

The scale factors (one node tighter than the 7nm sibling; see
`scaling/scale_factors_5nm.json`, citations in `docs/SOURCES.md`):

| quantity | factor vs sky130 | direction |
|---|---|---|
| cell delay | ÷15 | faster |
| process derate | ×1.5 (composes on delay & setup) | pessimism |
| cell area | ÷100 | smaller (≈1.8× denser than 7nm) |
| dynamic power | ÷8 | lower |
| leakage / cell | ×25 | higher |
| input cap | ÷5 | lower |
| setup / hold | ÷12 (then ×1.5 derate) | tighter |

## The two decks

| deck | node feel | area vs sky130 | ships |
|---|---|---|---|
| **opencell5** | 5nm-class | ÷100 | committed — turnkey |
| **opencell7** | 7nm-class | ÷56 | committed — the 7nm sibling / build base |

opencell5 is built *from* opencell7 (one node step), so it inherits all of the
7nm deck's accumulated fixes. To study the node step itself:
`flow/statppa.py --platforms opencell7 opencell5 <design>` — expect ~1.7× smaller
area and ~1.1× higher fmax (on cleanly-measured, tight-clock designs).

## What this is NOT

- **Not sign-off.** The endpoint is post-CTS; no detailed route, no DRC/LVS-clean
  GDS. Manufacturability is not the goal — a representative statistical feel is.
- **Not foundry-correlated.** Statistically consistent with published 5nm
  scaling; not equivalent to any specific TSMC/Samsung/Intel node.
- **Not silicon-validated at 5nm.** Silicon-validated at 130nm (sky130); the
  structural correctness inherits, the numeric magnitudes are projected.
- **Not GAA.** sky130-derived FinFET-class scaling; real 5nm is still FinFET, but
  3nm/2nm gate-all-around is out of scope.

## Repository layout

```
├── README.md
├── docs/QUICKSTART.md            run it yourself (no agent, no sky130)
├── docs/RUN_ORFS.md              the containerized ORFS wrapper + gotchas
├── docs/METHODOLOGY.md           scaling theory, derate, corner derivations
├── flow/
│   ├── run_orfs.sh               drive <platform> <design> to a stage (Docker)
│   ├── ppa.py                    single-platform PPA readout
│   ├── statppa.py                correlate any two platforms (--platforms A B)
│   └── tighten.py                push a design's clock to its true fmax floor
├── scaling/
│   ├── scale_factors_5nm.json    the opencell-5 definition (5nm factors)
│   ├── build_opencell5.sh        rebuild the deck from source (maintainers)
│   ├── scale_lib.py              sky130 .lib -> node-class .lib
│   └── gridlock_lef.py           site/DB-grid-locked LEF scaler
├── platforms/
│   ├── opencell5/                the 5nm-class deck (committed)
│   └── opencell7/                the 7nm-class deck (committed)
└── designs/{opencell5,opencell7,src}/   design configs + RTL
```

## License

Apache-2.0. Upstream sky130 Apache-2.0 attribution is preserved verbatim in every
`.lib` the scaler produces. See `LICENSE`.

## Repository

github.com/rtoley/Opencell-5
