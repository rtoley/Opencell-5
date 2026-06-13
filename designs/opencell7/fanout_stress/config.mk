export PLATFORM        = opencell7

export DESIGN_NAME     = fanout_stress
export DESIGN_NICKNAME = fanout_stress

export VERILOG_FILES = $(DESIGN_HOME)/src/fanout_stress/fanout_stress.v
export SDC_FILE      = $(DESIGN_HOME)/$(PLATFORM)/$(DESIGN_NICKNAME)/constraint.sdc

export CORE_UTILIZATION  = 40
export PLACE_DENSITY     = 0.55
export TNS_END_PERCENT   = 100
