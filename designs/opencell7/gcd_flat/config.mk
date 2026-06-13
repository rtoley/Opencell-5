export DESIGN_NAME     = gcd
export DESIGN_NICKNAME = gcd_flat
export PLATFORM        = opencell7

export VERILOG_FILES = $(DESIGN_HOME)/src/gcd/gcd.v
export SDC_FILE      = $(DESIGN_HOME)/$(PLATFORM)/$(DESIGN_NICKNAME)/constraint.sdc

# Flat: NO hierarchical, NO arith-operator swap, NO wrapped operators.
export ADDER_MAP_FILE :=
export CORE_UTILIZATION = 40
