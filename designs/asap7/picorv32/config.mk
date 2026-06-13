export PLATFORM        = asap7

export DESIGN_NAME     = picorv32
export DESIGN_NICKNAME = picorv32

export VERILOG_FILES = $(DESIGN_HOME)/src/picorv32/picorv32.v
export SDC_FILE      = $(DESIGN_HOME)/$(PLATFORM)/$(DESIGN_NICKNAME)/constraint.sdc

export ABC_AREA          = 1
export CORE_UTILIZATION  = 40
export CORE_ASPECT_RATIO = 1
export CORE_MARGIN       = 2
export PLACE_DENSITY     = 0.55
export TNS_END_PERCENT   = 100
