# correlateRC.py gcd,ibex,aes,jpeg,chameleon,riscv32i,chameleon_hier
# cap units pf/um
set_layer_rc -layer li1 -capacitance 1.499e-04 -resistance 6.064803e-01
set_layer_rc -layer met1 -capacitance 1.72375E-04 -resistance 7.546352e-03
set_layer_rc -layer met2 -capacitance 1.36233E-04 -resistance 7.546352e-03
set_layer_rc -layer met3 -capacitance 2.14962E-04 -resistance 1.324351e-03
set_layer_rc -layer met4 -capacitance 1.48128E-04 -resistance 1.324351e-03
set_layer_rc -layer met5 -capacitance 1.54087E-04 -resistance 1.505213e-04
# end correlate

set_layer_rc -via mcon -resistance 6.606479e-01
set_layer_rc -via via -resistance 3.214260e-01
set_layer_rc -via via2 -resistance 2.406256e-01
set_layer_rc -via via3 -resistance 2.690228e-02
set_layer_rc -via via4 -resistance 4.142824e-04

set_wire_rc -signal -layer met1
set_wire_rc -clock -layer met3
