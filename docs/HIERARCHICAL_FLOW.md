# Hierarchical bottom-up flow — never fail on big designs

The flat flow (synth → place → CTS → route on the whole netlist at once) blows up
on large designs: runtime, memory, congestion, and timing-closure complexity all
grow super-linearly. This blueprint makes the flow scale by **divide and conquer**:
harden small blocks bottom-up, abstract them, and assemble the top from abstracts —
so every individual step stays a bounded-size problem.

It is built to be **zero-config**: point the tooling at RTL and it discovers the
blocks itself. No hand-written block lists.

## 1. Autonomous block discovery — `flow/discover_blocks.py`

Two questions, answered from a cheap yosys probe (read → hierarchy → proc/opt →
stat, **no flatten**, seconds):

**Q1 — does this design even need hierarchy?** (the *size gate*)
Estimate total size; if it is under the flat-feasible threshold, run flat. The
decision is measured, not guessed.

**Q2 — which sub-modules become blocks?** Primary signal is the RTL module tree.
Walk it and select on three autonomous criteria:

- **Replication** — a module instantiated many times (lanes, PEs, cores, sboxes).
  Harden it **once**, reuse the abstract N×. Biggest win, and judged on *count*,
  not size: replicated combinational lookup logic (an sbox) is a compact `$pmux`
  until abc explodes it, so size alone would miss it.
- **Size band** — modules big enough to matter, small enough to P&R cleanly
  (`[block_min, block_max]`). Too big → descend; too small → roll into parent.
- **Interface/boundary** — registered, low-pin-count boundaries partition cleanly
  and make block-level timing self-contained (reported to guide budgeting).

```
flow/discover_blocks.py --top aes_cipher_top designs/src/aes/*.v
flow/discover_blocks.py --design designs/opencell7/aes      # reads config.mk
flow/discover_blocks.py --top X *.v --synth --json plan.json # generic-gate sizes
```

Proven on **aes**: it auto-finds `aes_sbox` instantiated **×20** (16 in the
cipher + 4 in key-expand) → *harden once, reuse 20×, 19 fewer block P&R runs*.

**Caveat:** pre-abc cell counts under-count combinational lookup logic; they rank
blocks, they do not budget area. `--synth` gives generic-gate counts.

**Fallback — when RTL has no usable hierarchy.** A single giant flat module, or
blocks with terrible boundaries, can't be cut by structure. Then partition the
*synthesized netlist* by connectivity min-cut (OpenROAD **TritonPart**; Hier-RTLMP
does dataflow+connectivity autoclustering) to manufacture balanced, low-cut
synthetic blocks. Higher overhead, but it never gets stuck.

## 2. Bottom-up build (maps onto ORFS `BLOCKS` + `generate_abstract`)

```
Tier 0  Black-box hard IP (RAMs)  -> flow/synth_helpers/gen_sram_lib.py emits .lib/.lef
Tier 1  Leaf blocks               -> synth->place->CTS each block independently,
                                      `generate_abstract` -> block.lef + block_typ.lib
Tier 2  Top integration           -> top instantiates blocks as MACROS, macro-place
                                      (2_2_floorplan_macro) + top CTS over few cells
```

Why it never fails:
- Every tier is **bounded size** — an N-million-gate SoC becomes N×(small block) +
  1×(small top).
- Each tier stops at the **post-CTS router-free statistical endpoint** — the same
  proven methodology as the flat flow, no detailed-route failures.
- Blocks are **independently cacheable** — a closed block never re-runs.
- The **fanout/buffer fix** and a **tight, consistent SDC budget** apply at every
  tier; the top period budget is split into block I/O constraints and iterated if
  the top misses.

## 3. Operational guards (hard-won)

- **Clean build dirs via the container**, never host `rm -rf`: ORFS writes outputs
  as container-root, so a host-user delete silently fails and `make` reuses stale
  synth. Use `docker run --rm -v "$PWD/build:/b" <img> rm -rf /b/orfs_<p>_<d>`.
- **Constrain every design to the same tight target on both platforms** before
  comparing fmax — a loose target lets the optimizer coast and *understates* fmax
  (gcd flipped −15% → +11% from constraint alone).

## Status

- [x] Autonomous discovery tool (`flow/discover_blocks.py`), proven on aes.
- [ ] Budgeting: top→block SDC split + iteration.
- [ ] Bottom-up driver wiring discovery output into ORFS `BLOCKS`/`generate_abstract`.
- [ ] TritonPart fallback for flat RTL.
- [ ] End-to-end demo: one block + a top that consumes its abstract.
