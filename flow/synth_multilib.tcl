# Multi-liberty variant of synth.tcl — for asap7 (5 split .lib files).
# LIB env var = space-separated list of .lib paths.
# Other env vars same as synth.tcl: RTL TOP BUILD PARAMS ABC_TARGET_PS.
# abc and dfflibmap take the FIRST liberty as the primary (asap7's SIMPLE
# carries the basic gates that map best); read_liberty is called once
# per file so yosys knows all cell models.

set lib_list $::env(LIB)
set rtl      $::env(RTL)
set top      $::env(TOP)
set build    $::env(BUILD)
set params [expr {[info exists ::env(PARAMS)]        ? $::env(PARAMS)        : ""}]
set abc_d  [expr {[info exists ::env(ABC_TARGET_PS)] ? $::env(ABC_TARGET_PS) : ""}]

foreach lib $lib_list {
    yosys "read_liberty -lib $lib"
}

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

# dfflibmap and abc take one -liberty per invocation; chain them.
foreach lib $lib_list {
    yosys "dfflibmap -liberty $lib"
}

set abc_args ""
foreach lib $lib_list {
    append abc_args " -liberty $lib"
}
if {$abc_d ne ""} {
    yosys "abc $abc_args -D $abc_d"
} else {
    yosys "abc $abc_args"
}

yosys clean

yosys "write_verilog -noattr $build/${top}_mapped.v"
yosys "write_json $build/${top}_mapped.json"

# stat takes one -liberty too; use the first
yosys "stat -liberty [lindex $lib_list 0]"
