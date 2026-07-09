current_design aes_cipher_top

set clk_name clk
set clk_port_name clk
# Mirrors asap7 aes constraint (clk_period 380 ps). opencell-7 scaled timing
# operates on the same time-unit (ns in lib), so 0.38 ns is the apples-to-apples
# target. SDC unit is platform-default (ns for opencell-7).
set clk_period 0.38
set clk_io_pct 0.2

set clk_port [get_ports $clk_port_name]
create_clock -name $clk_name -period $clk_period $clk_port

set non_clock_inputs [all_inputs -no_clocks]
set_input_delay  [expr $clk_period * $clk_io_pct] -clock $clk_name $non_clock_inputs
set_output_delay [expr $clk_period * $clk_io_pct] -clock $clk_name [all_outputs]

# High-fanout buffering trigger (clk handled by CTS; rst/heavy nets by repair_design)
set_max_fanout 24 [current_design]
set_max_transition 0.15 [current_design]
