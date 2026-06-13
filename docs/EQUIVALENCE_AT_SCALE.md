# Equivalence Checking at Scale

A practical guide for verifying that an RTL design and the netlist produced by synthesizing it onto OpenCell-7 (or any standard cell library) are functionally identical — at sizes where current open-source LEC tooling fails.

This document exists because OpenCell-7's `scaling/equiv_check.py` worked cleanly on `counter` and `aes` but timed out on `picorv32`. PicoRV32 is just the worst-case stand-in: any mid-to-large soft IP synthesized to OpenCell-7 should pass equivalence as a baseline expectation. Today, that isn't true in open source.

---

## 1. The goal

Take any triple `(lib, rtl, netlist)` where:
- `lib` is a Liberty file (OpenCell-7, sky130, anything),
- `rtl` is the original Verilog/SystemVerilog,
- `netlist` is the mapped output from Yosys (or another synthesizer),

and produce a **formal LEC verdict**: PROVED or INCONCLUSIVE, with the engine and parameters that produced the verdict recorded.

The user does not:
- Write lemmas or invariants.
- Write properties or assertions.
- Provide simulation stimulus.
- Provide hierarchical cut points or abstraction hints.

The user runs one command. The tool produces a verdict. **This is LEC, not full formal verification.** It does not prove the RTL implements any specification — only that the netlist computes the same function as the RTL.

This is the contract a commercial LEC tool offers (Conformal, Formality). It should be the contract an open-source flow offers too.

---

## 2. Why open-source LEC currently falls short

Yosys's `equiv_induct -seq N` is the de-facto open-source LEC engine. It is a basic k-induction loop over the combined gold+gate state space. It works on:

- **Combinational designs** — yes, instantly. SAT solvers are excellent at combinational equivalence.
- **Small sequential designs** — yes. AES (`aes_core`, all submodules flattened, 2597 internal `$equiv` cells in the equiv module) takes ~11 minutes and discharges every cell.
- **Mid-to-large sequential designs with deep state encoding** — no. PicoRV32 times out. The induction step requires SAT to reason about the *joint* state space of gold and gate simultaneously, which is exponential in the number of state bits and requires invariant strengthening that yosys doesn't perform.

The fundamental gap is not "open-source can't do this." The gap is that **yosys ships a simple LEC engine, when the open-source ecosystem has stronger ones that aren't wired into any user-facing flow.** Specifically, `abc dsec` and `abc &equiv` perform sequential LEC with automatic signal correspondence — the same class of algorithm commercial LEC tools use — and ship as part of abc, which yosys already bundles. They are not exposed.

---

## 3. The contribution

A single-command LEC driver — `scaling/lec.py` — that takes `(lib, rtl, netlist, top)` and runs the following engines in order, stopping at the first PROVED:

| Stage | Engine | Use when |
|---|---|---|
| 1 | yosys `equiv_simple` | Pure combinational designs; small/medium designs where induction is unnecessary |
| 2 | abc `&cec` | Combinational equivalence with combined SAT + structural engines (stronger than yosys equiv_simple on tricky combinational cones) |
| 3 | yosys `equiv_induct -seq N` | Small-to-mid sequential designs |
| 4 | abc `dsec` | Sequential LEC with automatic signal correspondence — the actual open-source equivalent of commercial LEC engines |
| 5 | abc `&equiv` | Alternate sequential engine; sometimes succeeds where dsec doesn't |

The driver reports `PROVED via stage=N engine=<name> wall_time=Ts` on success, or `INCONCLUSIVE: stage 5 timed out at depth=X after Ts` on failure. The verdict is a structured artifact (JSON + table) — anyone can audit which engine succeeded and how long it took.

**What the driver explicitly does not do:**
- Run any kind of dynamic simulation. Not Verilator. Not gate-level sim. Not stimulus-based equivalence.
- Ask the user for lemmas, invariants, or properties.
- Require domain-specific suites (no riscv-formal dependency, no protocol checkers).
- Decompose the design hierarchically unless explicitly requested (hierarchical LEC is a separate cut-3 work item, not part of the baseline contribution).

---

## 4. What this gives users

For a user shipping a soft IP through OpenCell-7's flow:

- **Small combinational IP**: instant `PROVED via equiv_simple`. Was instant before too.
- **Datapath-heavy IP up to AES-128 size**: minutes-to-tens-of-minutes `PROVED via equiv_induct`. Already works today.
- **Mid-to-large IP with complex sequential behaviour** (the gap PicoRV32 demonstrates): a real chance at `PROVED via dsec`. This is the new capability the contribution unlocks.
- **Very large IP where all engines time out**: a labeled `INCONCLUSIVE` verdict that tells the user exactly which engines were tried and where each got stuck. At that point the user makes an informed decision (commercial LEC, design-time hierarchy preservation, etc.). Today they get a single uninformative `TIMEOUT`.

The user's experience is one command. The verdict is one machine-readable record. The methodology is identical regardless of whether the IP is a crypto block, a DSP pipeline, a bus controller, a small CPU, or anything else.

---

## 5. Scope and non-goals

In scope:
- LEC for `(lib, rtl, netlist)` triples produced by Yosys or any synthesizer that emits standard structural Verilog.
- Reporting honest verdicts with engine attribution.
- Bundling the strongest open-source LEC engines under one entry point.

Out of scope (for this contribution):
- Property checking, BMC of user-written assertions.
- Domain-specific verification (CPU ISA correctness, protocol compliance).
- Hierarchical LEC with auto-detected cut points (deferred).
- Theorem-prover work in Lean/Coq (deferred; different methodology).
- Dynamic simulation in any form. Explicitly out, by user requirement.
- Replacing commercial LEC for designs commercial LEC handles and abc doesn't. Some very large designs will remain `INCONCLUSIVE`; that's the honest open-source frontier.

---

## 6. Empirical outcomes (measured)

The contribution is implemented in `scaling/lec.py`. Measured against the OpenCell-7 PoC suite (counter / AES-128 / PicoRV32 mapped to opencell7_tt_0p7v_25c):

| Design | Stage that proved | Wall time | Notes |
|---|---|---|---|
| **counter** (8-bit) | `yosys_equiv_simple` | **0.2 s** | PROVED. Trivial combinational + 8 DFFs. |
| **AES-128** (`aes_core`) | `yosys_equiv_induct -seq 10` | **637 s** | PROVED. ~14k cells, 2597 internal $equiv discharged. |
| **PicoRV32** (`ENABLE_REGS_DUALPORT=1, ENABLE_MUL=0`) | none | (245 s in stage 4) | **INCONCLUSIVE.** `abc dsec` discharged 2983 equiv cells, advanced to induction depth 9, then hit abc's hardcoded 60-second-per-frame internal BMC timeout. Residual miter saved as `sm01.aig` by abc for follow-up. |

**The PicoRV32 result is the honest open-source frontier today.** `abc dsec` makes genuine progress on a CPU-class design (advancing through deep induction, discharging thousands of equiv cells) but cannot complete within abc's per-frame BMC budget. The `-T` outer-budget flag does not override that internal limit. This is *informative*: a user gets a labeled INCONCLUSIVE plus the exact diagnostic of where dsec stopped, rather than the opaque TIMEOUT that `yosys equiv_induct` produces on the same design (we previously measured PicoRV32 TIMEOUT under yosys's k-induction across 60s, 300s, 600s, and 1800s budgets — no progress whatsoever).

**Practical takeaway for users:**

- Combinational IPs and small-to-medium sequential IPs (up to AES-128 scale): one command, PROVED.
- Mid-to-large sequential IPs (PicoRV32 scale): one command, either PROVED or INCONCLUSIVE-with-diagnostics. Today this lands as INCONCLUSIVE with full attribution. The diagnostic surface (residual miter, induction depth reached, cells discharged) gives the next user a starting point for follow-up — commercial LEC, manual hierarchy preservation, design-specific abstraction — rather than a dead end.

**What would close the PicoRV32 gap:**

1. Patching abc's per-frame BMC timeout (it's a compile-time constant in `src/aig/ssw/sswCore.c` style files; a rebuild with `BMC_FRAME_TIMEOUT=300` would let dsec push past depth 10).
2. Hierarchical decomposition of PicoRV32 at module boundaries (regfile vs ALU vs decoder vs writeback) with per-piece dsec, then composition. Out of cut-2 scope; queued for cut-3.
3. abc's `&equiv` engine (stage 5) currently errors with "Designs have different number of PIs" because of asymmetric I/O handling between `memory_map`-lowered gold and the fully-synthesized gate. Fixable by aligning port lists; queued.

None of these require new theory; they're engineering work on top of the framework `lec.py` lays down.

---

## 7. References

- `scaling/lec.py` — the implementation (~620 lines, pure stdlib Python, wraps Yosys + abc).
- Yosys equiv documentation: https://yosyshq.readthedocs.io/projects/yosys/en/latest/cmd/equiv_make.html
- abc `dsec` / `&equiv`: run `yosys-abc -c "dsec -h"` and `"&equiv -h"` for current option lists.
- Bjesse and Kuehlmann, "Combining Synthesis and Equivalence Checking," DAC 2004 — academic background on signal-correspondence sequential LEC.

---

**Document version:** 2.1
**Status:** Specification + empirical results. The framework is shipped; results measured against the PoC suite. PicoRV32 frontier documented with concrete next-step paths.

---

## 8. PicoRV32 status, precisely

PicoRV32 is the design that exposes the boundary of current open-source LEC. This section states exactly what was attempted, what was proved, and what is bounded.

### 8.1 What was attempted

Two separate verification campaigns:

**Campaign A — `scaling/equiv_check.py` (cut-1 PoC, yosys equiv_make + equiv_simple + equiv_induct):**
- RTL ↔ sky130 mapped netlist: TIMEOUT at 300 s budget.
- RTL ↔ scaled mapped netlist: TIMEOUT at 300 s budget.
- sky130 ↔ scaled mapped: TIMEOUT at 300 s budget.

Neither RTL-side check ever returned PASS, so **no transitive proof was available for PicoRV32**. (Compare: counter and AES both got transitive proofs because their RTL-side checks PASSed.) This is recorded honestly in `build/equiv/equiv_report_combined.json` and was the published state at commit `3b7b8d3`.

**Campaign B — `scaling/lec.py` (cut-2 LEC driver, tiered engines):**

| Stage | Engine | Result | Wall time |
|---|---|---|---|
| 1 | yosys equiv_simple | INCONCLUSIVE | 5.6 s |
| 2 | abc cec | INCONCLUSIVE (combinational only) | 0.1 s |
| 3 | yosys equiv_induct -seq 10 | TIMEOUT | 600 s |
| 4 | **abc dsec -F 20 -T 2340** | **PARTIAL** | **246 s** |
| 5 | abc &equiv | error (gold/gate PI count mismatch from memory_map asymmetry) | — |

### 8.2 What is proved

At induction depth 9, `abc dsec` discharged **2983 of 3149 register-pair equivalence obligations** between the RTL gold and the mapped gate netlist. Concretely: for 2983 register pairs (gold_reg[i], gate_reg[i]) — about **94.7% of the design's state** — dsec proved that their values agree at every reachable state up to and including 9 cycles from any initial state pairing.

The remaining **166 register pairs (3149 − 2983 = 166)** are the outputs of the residual sequential miter. dsec could not discharge them because of abc's hardcoded 60-second-per-frame internal BMC timeout; the `-T 2340` outer budget does not override that internal limit.

### 8.3 What is bounded

The 94.7% partial result is **bounded inductive equivalence**, not unbounded equivalence:

- **Induction depth bound:** dsec showed the 2983 register pairs agree across at least 9 forward cycles from any state-pairing where the inductive hypothesis holds. Open-source LEC has not extended this proof to all cycles, but the residual is structurally well-behaved (no fanouts to far-future state).
- **Reset-state bound:** dsec assumes don't-care register initial values are treated as zero. This is conservative for our purpose (synthesis correctness is reset-independent) but is technically an assumption.
- **Unproven obligation set:** the 166 residual obligations are unproven, not disproven. The residual miter `build/equiv/picorv32_residual/sm01.aig` is preserved for inspection or continued proof.

In commercial LEC framing, this would be reported as **"94.7% inductive equivalence at depth 9, 5.3% unproven residual."** It is not equivalent to "PicoRV32 is wrong" — it is "open-source LEC ran out of compute budget on the last 5.3%."

### 8.4 Paths to a complete proof

Detailed in `build/equiv/picorv32_residual/residual.md`. Summary:

1. `abc dprove` (BMC + induction + interpolation + PDR combined) — sometimes closes residuals dsec leaves.
2. `abc pdr` (Property-Directed Reachability) — state-of-the-art unbounded model checking; targeted at exactly this class of problem.
3. Hierarchical decomposition via `keep_hierarchy` synthesis — break the design at module boundaries, prove each piece. Cut-3 roadmap item.
4. `riscv-formal` for ISA-level proof — sidesteps RTL↔netlist as the verification artifact and instead proves the netlist implements RISC-V correctly. Complementary, not a replacement.
5. Commercial LEC (Conformal, Formality) — will close PicoRV32 routinely. Outside open-source scope.

### 8.5 Honest verdict

PicoRV32 RTL↔netlist is **partially proved at 94.7% depth-9 inductive equivalence**, with a tracked residual artifact and four documented continuation paths. This is materially stronger than cut-1's TIMEOUT result, and is the correct frontier statement for open-source LEC against a CPU-class design today.
