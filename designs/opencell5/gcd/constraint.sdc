current_design gcd

set clk_name core_clock
set clk_port_name clk
# opencell-7 cells ~9x faster than sky130; target 0.5 ns (2 GHz) — leaves
# headroom over the synth-only fmax we measured (1.76 GHz at 30x, 2.18 GHz
# at 40x).
set clk_period 0.31
set clk_io_pct 0.2

set clk_port [get_ports $clk_port_name]
create_clock -name $clk_name -period $clk_period $clk_port

set non_clock_inputs [all_inputs -no_clocks]
set_input_delay  [expr $clk_period * $clk_io_pct] -clock $clk_name $non_clock_inputs
set_output_delay [expr $clk_period * $clk_io_pct] -clock $clk_name [all_outputs]
