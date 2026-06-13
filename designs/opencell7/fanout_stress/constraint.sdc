current_design fanout_stress

set clk_name   clk
set clk_port_name clk
# RAM-read-enable analogy: target 300 ps (3.33 GHz). read_en fans out to 512
# flop enables; only a balanced buffer tree from repair_design makes this path
# meet 300 ps. This SDC is the stress: tight period + an explicit fanout limit.
set clk_period 0.30
set clk_io_pct 0.2

set clk_port [get_ports $clk_port_name]
create_clock -name $clk_name -period $clk_period $clk_port

set non_clock_inputs [all_inputs -no_clocks]
set_input_delay  [expr $clk_period * $clk_io_pct] -clock $clk_name $non_clock_inputs
set_output_delay [expr $clk_period * $clk_io_pct] -clock $clk_name [all_outputs]

# High-fanout buffering trigger (the fix under test).
set_max_fanout 24 [current_design]
set_max_transition 0.15 [current_design]
