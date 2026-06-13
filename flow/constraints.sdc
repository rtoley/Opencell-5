# OpenCell-7 — generic SDC constraints, parameterized by env vars.
#
# Variables (with safe defaults):
#   CLK_PERIOD_NS    clock period in ns (default 10.0)
#   CLK_PORT         name of the clock port (default clk)
#
# Notes:
# - Input/output delays are set to 1% of the period (small relative to logic)
#   so they do not artificially bind fmax. The cut-0 SDC used 30% which made
#   the input-port path dominant.
# - Driving cell and load are deliberately omitted — different libraries map
#   to different cell names; we let STA assume the default driving cell.

set clk_period [expr {[info exists ::env(CLK_PERIOD_NS)] ? $::env(CLK_PERIOD_NS) : 10.0}]
set clk_port  [expr {[info exists ::env(CLK_PORT)]      ? $::env(CLK_PORT)      : "clk"}]

create_clock -name clk -period $clk_period [get_ports $clk_port]

set_clock_uncertainty [expr {0.005 * $clk_period}] [get_clocks clk]
set_clock_transition  [expr {0.005 * $clk_period}] [get_clocks clk]

set io_delay [expr {0.01 * $clk_period}]
set_input_delay  -clock clk $io_delay [all_inputs]
set_output_delay -clock clk $io_delay [all_outputs]
# Don't constrain the clock itself
set_input_delay  -clock clk 0 [get_ports $clk_port]
