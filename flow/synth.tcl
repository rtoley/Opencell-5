# OpenCell-7 — generic Yosys synthesis script (TCL).
#
# Run via:  yosys -c flow/synth.tcl
#
# Env vars:
#   LIB             path to Liberty file
#   RTL             space-separated list of Verilog source files
#   TOP             top module name
#   BUILD           output directory
#   PARAMS          (optional) extra arguments appended to `hierarchy`,
#                   e.g. "-chparam ENABLE_REGS_DUALPORT 1 -chparam ENABLE_MUL 0"
#   ABC_TARGET_PS   (optional) target period in picoseconds passed to abc -D
#                   for delay-driven mapping. If unset, abc runs with no
#                   target (area-driven default).
#
# Pipeline:
#   read_liberty -> read_verilog -> hierarchy -> proc/opt/fsm/opt/memory/opt
#   -> techmap -> opt -> flatten -wb -> dfflibmap -> abc [-D <ps>] -> clean
#
# `flatten -wb` collapses module boundaries (including whitebox-attributed
# cells) so abc sees the full critical path across submodules. `abc -D`
# tells the technology mapper a target period; cell sizes are chosen with
# that target in mind. Both are essential for getting realistic synthesis
# fmax on multi-module designs like PicoRV32 and AES.

set lib    $::env(LIB)
set rtl    $::env(RTL)
set top    $::env(TOP)
set build  $::env(BUILD)
set params [expr {[info exists ::env(PARAMS)]        ? $::env(PARAMS)        : ""}]
set abc_d  [expr {[info exists ::env(ABC_TARGET_PS)] ? $::env(ABC_TARGET_PS) : ""}]

yosys "read_liberty -lib $lib"
yosys "read_verilog $rtl"
yosys "hierarchy -check -top $top $params"

yosys proc
yosys opt
yosys fsm
yosys opt
yosys memory
yosys opt
yosys techmap
yosys opt

yosys "flatten -wb"
yosys opt

yosys "dfflibmap -liberty $lib"

# Note: we deliberately do NOT pass -dff to abc. abc with -dff makes
# library-dependent retime decisions (cell-area vs FF-area cost ratios
# differ between sky130 and the 30x-smaller scaled lib), which produced
# asymmetric mapping choices on AES — sky130 regressed while scaled
# improved, inflating the scaled/sky130 ratio from 6.7x to 12.6x.
# Without -dff, abc treats FFs as I/O boundaries; -D still drives
# combinational delay-aware mapping. This gives consistent cross-library
# ratios across all PoC designs. See docs/METHODOLOGY.md §5.5.
if {$abc_d ne ""} {
    yosys "abc -liberty $lib -D $abc_d"
} else {
    yosys "abc -liberty $lib"
}

yosys clean

yosys "write_verilog -noattr $build/${top}_mapped.v"
yosys "write_json $build/${top}_mapped.json"

yosys "stat -liberty $lib"
