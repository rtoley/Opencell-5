current_design picorv32

set clk_name clk
set clk_port_name clk
# PicoRV32 canonical open-source ASIC target: ~1 GHz on 7nm-class.
# Don't push extreme; 1 ns = 1 GHz is the known-good reference point.
set clk_period 1.0
set clk_io_pct 0.2

set clk_port [get_ports $clk_port_name]
create_clock -name $clk_name -period $clk_period $clk_port

set non_clock_inputs [all_inputs -no_clocks]
set_input_delay  [expr $clk_period * $clk_io_pct] -clock $clk_name $non_clock_inputs
set_output_delay [expr $clk_period * $clk_io_pct] -clock $clk_name [all_outputs]

# High-fanout buffering trigger. The scaled lib carried default_fanout_load=0
# (inherited from sky130), so fanout contributed NO load and high-fanout nets
# were invisible to repair_design -> never buffered -> crap absolute fmax.
# Lib now sets default_fanout_load=1 (asap7-faithful); these give repair_design
# an explicit, unambiguous fanout/slew limit so buffering actually fires.
set_max_fanout 24 [current_design]
set_max_transition 0.15 [current_design]
