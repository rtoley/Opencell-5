# Multi-liberty STA — for asap7 (5 split .lib files).
# LIB env var = space-separated list of .lib paths.

foreach lib $::env(LIB) {
    read_liberty $lib
}
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
