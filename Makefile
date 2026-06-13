# OpenCell-7 — top-level Makefile (scaling-tool architecture).
#
# Quickstart:
#   make fetch         # clone sky130 + build .lib for TT and SS corners
#   make scale         # produce derived/opencell7_{tt,ss}_*.lib
#   make validate      # synth+STA on all four libraries, print ratios

YOSYS  ?= yosys
STA    ?= sta
PYTHON ?= python3

# Defaults — overridable from CLI
LIB      ?= derived/opencell7_tt_0p7v_25c.lib
RTL      ?= reference/counter.v
TOP      ?= counter
SDC      ?= flow/constraints.sdc
BUILD    ?= build/$(notdir $(basename $(LIB)))

SKY130_TT  := derived/sky130_libs/sky130_fd_sc_hd__tt_025C_1v80.lib
SKY130_SS  := derived/sky130_libs/sky130_fd_sc_hd__ss_n40C_1v60.lib
SCALED_TT  := derived/opencell7_tt_0p7v_25c.lib
SCALED_SS  := derived/opencell7_ss_0p65v_125c.lib

.PHONY: all fetch fetch-designs scale scale-tt scale-ss validate \
        poc poc-counter poc-picorv32 poc-aes synth sta clean check help

help:
	@echo "OpenCell-7 — scaling-tool flow"
	@echo ""
	@echo "  make fetch          — clone sky130 + build .lib for TT and SS"
	@echo "  make fetch-designs  — clone PicoRV32 + AES reference designs"
	@echo "  make scale          — emit both scaled libs"
	@echo "  make scale-tt       — emit only the TT scaled lib"
	@echo "  make scale-ss       — emit only the SS scaled lib"
	@echo "  make validate       — synth+STA counter on sky130+scaled, print ratios"
	@echo "  make poc            — run PoC sweep on all designs x all libs"
	@echo "  make poc-counter    — PoC sweep limited to counter"
	@echo "  make poc-picorv32   — PoC sweep limited to picorv32"
	@echo "  make poc-aes        — PoC sweep limited to aes"
	@echo "  make synth LIB=<lib> RTL=<rtl> TOP=<name>"
	@echo "  make sta   LIB=<lib>              TOP=<name>"
	@echo "  make clean"

fetch: $(SKY130_TT) $(SKY130_SS)

$(SKY130_TT) $(SKY130_SS):
	./reference/fetch_sky130.sh

scale: scale-tt scale-ss

scale-tt: $(SCALED_TT)
scale-ss: $(SCALED_SS)

$(SCALED_TT): $(SKY130_TT) scaling/scale_lib.py scaling/scale_factors.json
	@mkdir -p derived
	$(PYTHON) scaling/scale_lib.py --corner tt --in $(SKY130_TT) --out $(SCALED_TT)

$(SCALED_SS): $(SKY130_SS) scaling/scale_lib.py scaling/scale_factors.json
	@mkdir -p derived
	$(PYTHON) scaling/scale_lib.py --corner ss --in $(SKY130_SS) --out $(SCALED_SS)

validate: scale
	$(PYTHON) scaling/validate.py

fetch-designs:
	./reference/fetch_designs.sh

reference/picorv32/picorv32.v reference/aes/src/rtl/aes_core.v:
	./reference/fetch_designs.sh

poc: scale reference/picorv32/picorv32.v reference/aes/src/rtl/aes_core.v
	$(PYTHON) scaling/poc_compare.py

poc-counter: scale
	$(PYTHON) scaling/poc_compare.py --only counter

poc-picorv32: scale reference/picorv32/picorv32.v
	$(PYTHON) scaling/poc_compare.py --only picorv32

poc-aes: scale reference/aes/src/rtl/aes_core.v
	$(PYTHON) scaling/poc_compare.py --only aes

$(BUILD):
	@mkdir -p $(BUILD)

synth: | $(BUILD)
	@echo "==> Yosys synthesis  LIB=$(LIB) RTL=$(RTL) TOP=$(TOP)"
	@LIB=$(LIB) RTL=$(RTL) TOP=$(TOP) BUILD=$(BUILD) \
		$(YOSYS) -l $(BUILD)/yosys.log -c flow/synth.tcl

sta: | $(BUILD)
	@echo "==> OpenSTA timing  LIB=$(LIB) TOP=$(TOP) SDC=$(SDC)"
	@LIB=$(LIB) TOP=$(TOP) BUILD=$(BUILD) SDC=$(SDC) \
		$(STA) -no_init -no_splash -exit flow/sta.tcl 2>&1 | tee $(BUILD)/sta.log

clean:
	rm -rf build derived/*.lib

check:
	@echo "Yosys:   $$($(YOSYS) -V 2>/dev/null || echo NOT FOUND)"
	@echo "OpenSTA: $$($(STA) -version 2>/dev/null || echo NOT FOUND)"
	@echo "Python:  $$($(PYTHON) --version 2>/dev/null || echo NOT FOUND)"
