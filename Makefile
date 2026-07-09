# OpenCell-5 — top-level Makefile.
#
# The opencell-5 deck ships committed; you don't need make to RUN it:
#     flow/run_orfs.sh opencell5 <design> cts
#     flow/ppa.py      opencell5 <design>
# These targets only re-derive the library from the sky130 source (provenance).

PYTHON    ?= python3
SKY130_TT := derived/sky130_libs/sky130_fd_sc_hd__tt_025C_1v80.lib
SKY130_SS := derived/sky130_libs/sky130_fd_sc_hd__ss_n40C_1v60.lib
OC5_TT    := derived/opencell5_tt_0p70v_25c.lib
OC5_SS    := derived/opencell5_ss_0p65v_125c.lib
FACTORS   := scaling/scale_factors_5nm.json

.PHONY: help fetch lib clean

help:
	@echo "OpenCell-5 — statistical 5nm-class SDK"
	@echo ""
	@echo "  Run (deck ships committed):"
	@echo "    flow/run_orfs.sh opencell5 <design> cts   # design -> statistical endpoint"
	@echo "    flow/ppa.py      opencell5 <design>        # area / fmax / power"
	@echo "    flow/statppa.py  <design>                  # correlate vs asap7 (7nm ref)"
	@echo ""
	@echo "  Re-derive the library from source (optional, provenance):"
	@echo "    make fetch   — fetch the sky130 source .lib"
	@echo "    make lib     — re-derive opencell5_{tt,ss}.lib from sky130"
	@echo "    make clean"

fetch: $(SKY130_TT) $(SKY130_SS)
$(SKY130_TT) $(SKY130_SS):
	./reference/fetch_sky130.sh

lib: $(OC5_TT) $(OC5_SS)

$(OC5_TT): $(SKY130_TT) scaling/scale_lib.py $(FACTORS) scaling/set_fanout_load.py
	@mkdir -p derived
	$(PYTHON) scaling/scale_lib.py --corner tt --in $(SKY130_TT) --out $(OC5_TT) --factors $(FACTORS)
	$(PYTHON) scaling/set_fanout_load.py --lib $(OC5_TT) --value 1.0

$(OC5_SS): $(SKY130_SS) scaling/scale_lib.py $(FACTORS) scaling/set_fanout_load.py
	@mkdir -p derived
	$(PYTHON) scaling/scale_lib.py --corner ss --in $(SKY130_SS) --out $(OC5_SS) --factors $(FACTORS)
	$(PYTHON) scaling/set_fanout_load.py --lib $(OC5_SS) --value 1.0

clean:
	rm -rf build derived/opencell5_*.lib
