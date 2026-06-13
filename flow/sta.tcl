# OpenCell-7 — generic OpenSTA timing analysis script.
#
# Driven via environment variables:
#   LIB         path to the Liberty file
#   TOP         name of the top module
#   BUILD       directory containing $TOP_mapped.v
#   SDC         path to the SDC constraints file
#
# Emits: report_checks, report_wns, report_tns, report_power.

read_liberty $::env(LIB)
read_verilog $::env(BUILD)/$::env(TOP)_mapped.v
link_design $::env(TOP)
read_sdc $::env(SDC)

puts ""
puts "==================== Setup timing (max) ===================="
report_checks -path_delay max -format full_clock_expanded -digits 4

puts ""
puts "==================== Setup timing reg-to-reg only =========="
report_checks -path_delay max -from [all_registers] -to [all_registers] -digits 4

puts ""
puts "==================== Slack summary ========================="
report_wns
report_tns

puts ""
puts "==================== Power estimate ========================"
report_power -digits 4
