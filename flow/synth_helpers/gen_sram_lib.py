#!/usr/bin/env python3
# gen_sram_lib.py DEPTH WIDTH OUT.lib
# Emits a Liberty timing model for the 1R1W SRAM `sram_macro`
# (ports: clk, reset_n, ren, raddr, rdata, wen, waddr, wdata) so OpenSTA can
# time the per-bank read path while yosys treats the macro as a black box.
#
# Timing is a documented MODEL, anchored to the real FakeRAM subreg_bank_16x262
# characterization (ASAP7 RVT SS): read access clk->rdata = 0.218 ns and input
# setup = 0.050 ns at DEPTH=16. Access scales mildly (sub-linear, ~log2 of
# rows) with depth — the SRAM-read latency is nearly flat across bank depth,
# which is the whole point of the banked design. Units: 1 ns. Not a sign-off
# model; a representative black-box timestamp "by size" for the comparison.
import sys, math

depth = int(sys.argv[1]); width = int(sys.argv[2]); out = sys.argv[3]
aw = max(1, math.ceil(math.log2(depth)))
# Read access, anchored at 0.218 ns @ depth16, +0.025 ns per doubling of depth.
access = round(0.218 + 0.025 * (math.log2(depth) - 4.0), 4)
setup  = 0.050
minper = round(access + 0.020, 4)
DATA = f"sram_{depth}x{width}_DATA"; ADDR = f"sram_{depth}x{width}_ADDR"

def bus_type(name, w):
    return f"""    type ({name}) {{
        base_type : array ; data_type : bit ;
        bit_width : {w}; bit_from : {w-1}; bit_to : 0 ; downto : true ;
    }}"""

def out_bus(name):  # clk -> name read access
    return f"""    bus({name}) {{
        bus_type : {DATA} ; direction : output ; max_capacitance : 0.500 ;
        memory_read() {{ address : raddr ; }}
        timing() {{
            related_pin : "clk" ; timing_type : rising_edge ;
            cell_rise(delay_tmpl)  {{ index_1("0.009,0.227"); index_2("0.005,0.500"); values("{access},{access}","{access},{access}"); }}
            cell_fall(delay_tmpl)  {{ index_1("0.009,0.227"); index_2("0.005,0.500"); values("{access},{access}","{access},{access}"); }}
            rise_transition(slew_tmpl) {{ index_1("0.005,0.500"); values("0.009,0.227"); }}
            fall_transition(slew_tmpl) {{ index_1("0.005,0.500"); values("0.009,0.227"); }}
        }}
    }}"""

def in_setup_bus(name, btype):
    return f"""    bus({name}) {{
        bus_type : {btype} ; direction : input ; capacitance : 0.005 ;
        timing() {{ related_pin : clk ; timing_type : setup_rising ;
            rise_constraint(cons_tmpl) {{ index_1("0.009,0.227"); index_2("0.009,0.227"); values("{setup},{setup}","{setup},{setup}"); }}
            fall_constraint(cons_tmpl) {{ index_1("0.009,0.227"); index_2("0.009,0.227"); values("{setup},{setup}","{setup},{setup}"); }} }}
    }}"""

def in_setup_pin(name):
    return f"""    pin({name}) {{ direction : input ; capacitance : 0.005 ;
        timing() {{ related_pin : clk ; timing_type : setup_rising ;
            rise_constraint(cons_tmpl) {{ index_1("0.009,0.227"); index_2("0.009,0.227"); values("{setup},{setup}","{setup},{setup}"); }}
            fall_constraint(cons_tmpl) {{ index_1("0.009,0.227"); index_2("0.009,0.227"); values("{setup},{setup}","{setup},{setup}"); }} }}
    }}"""

lib = f"""library(sram_macro) {{
    delay_model : table_lookup ;
    time_unit : "1ns" ; voltage_unit : "1V" ; current_unit : "1mA" ;
    capacitive_load_unit (1, pf) ; pulling_resistance_unit : "1kohm" ;
    leakage_power_unit : "1uW" ;
    default_max_transition : 1.000 ;
    slew_lower_threshold_pct_rise : 20.0 ; slew_upper_threshold_pct_rise : 80.0 ;
    slew_lower_threshold_pct_fall : 20.0 ; slew_upper_threshold_pct_fall : 80.0 ;
    input_threshold_pct_rise : 50.0 ; input_threshold_pct_fall : 50.0 ;
    output_threshold_pct_rise : 50.0 ; output_threshold_pct_fall : 50.0 ;
    nom_voltage : 0.63 ; nom_temperature : 100.0 ; nom_process : 1.0 ;
    lu_table_template(delay_tmpl) {{ variable_1: input_net_transition ; variable_2: total_output_net_capacitance ; index_1("1000,1001"); index_2("1000,1001"); }}
    lu_table_template(slew_tmpl)  {{ variable_1: total_output_net_capacitance ; index_1("1000,1001"); }}
    lu_table_template(cons_tmpl)  {{ variable_1: related_pin_transition ; variable_2: constrained_pin_transition ; index_1("1000,1001"); index_2("1000,1001"); }}
{bus_type(DATA, width)}
{bus_type(ADDR, aw)}
  cell(sram_macro) {{
    area : {round(depth*width*0.02,1)} ;
    memory() {{ type : ram ; address_width : {aw} ; word_width : {width} ; }}
    pin(clk) {{ direction : input ; capacitance : 0.025 ; clock : true ; min_period : {minper} ; }}
    pin(reset_n) {{ direction : input ; capacitance : 0.005 ; }}
{in_setup_pin("ren")}
{in_setup_pin("wen")}
{in_setup_bus("raddr", ADDR)}
{in_setup_bus("waddr", ADDR)}
{in_setup_bus("wdata", DATA)}
{out_bus("rdata")}
  }}
}}
"""
open(out, "w").write(lib)
print(f"wrote {out}: depth={depth} width={width} addr_w={aw} access={access}ns setup={setup}ns")
