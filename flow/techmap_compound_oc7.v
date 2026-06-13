// techmap_compound_oc7.v — expand v0.5 composite AOI/OAI cells back to sky130
// primitives after abc mapping. Used together with
// derived/opencell7_tt_0p7v_25c_v0p5.lib by synth scripts that want abc to
// see the wider compound options without growing the library's physical
// footprint.
//
// Each module here implements the boolean function that the corresponding
// .lib cell advertised, decomposed into sky130_fd_sc_hd__* primitives that
// already have full LEF/GDS coverage. After `techmap -map <this-file>`, the
// netlist contains only real sky130 cells.

`define SKY sky130_fd_sc_hd

// ============================================================================
// AOI33 family (inverting):  Y = !((A1·A2·A3) + (B1·B2·B3) + ...)
// ============================================================================

module \`SKY``__a33oi_1 (A1, A2, A3, B1, B2, B3, Y);
    input  A1, A2, A3, B1, B2, B3;
    output Y;
    wire   b_and;
    \`SKY``__and3_1 u_b   (.A(B1), .B(B2), .C(B3), .X(b_and));
    \`SKY``__a31oi_1 u_aoi (.A1(A1), .A2(A2), .A3(A3), .B1(b_and), .Y(Y));
endmodule

module \`SKY``__a33oi_2 (A1, A2, A3, B1, B2, B3, Y);
    input  A1, A2, A3, B1, B2, B3;
    output Y;
    wire   b_and;
    \`SKY``__and3_2 u_b   (.A(B1), .B(B2), .C(B3), .X(b_and));
    \`SKY``__a31oi_2 u_aoi (.A1(A1), .A2(A2), .A3(A3), .B1(b_and), .Y(Y));
endmodule

module \`SKY``__a33oi_4 (A1, A2, A3, B1, B2, B3, Y);
    input  A1, A2, A3, B1, B2, B3;
    output Y;
    wire   b_and;
    \`SKY``__and3_4 u_b   (.A(B1), .B(B2), .C(B3), .X(b_and));
    \`SKY``__a31oi_4 u_aoi (.A1(A1), .A2(A2), .A3(A3), .B1(b_and), .Y(Y));
endmodule

module \`SKY``__a331oi_1 (A1, A2, A3, B1, B2, B3, C1, Y);
    input  A1, A2, A3, B1, B2, B3, C1;
    output Y;
    wire   b_and;
    \`SKY``__and3_1 u_b   (.A(B1), .B(B2), .C(B3), .X(b_and));
    \`SKY``__a311oi_1 u_aoi (.A1(A1), .A2(A2), .A3(A3), .B1(b_and), .C1(C1), .Y(Y));
endmodule

module \`SKY``__a331oi_2 (A1, A2, A3, B1, B2, B3, C1, Y);
    input  A1, A2, A3, B1, B2, B3, C1;
    output Y;
    wire   b_and;
    \`SKY``__and3_2 u_b   (.A(B1), .B(B2), .C(B3), .X(b_and));
    \`SKY``__a311oi_2 u_aoi (.A1(A1), .A2(A2), .A3(A3), .B1(b_and), .C1(C1), .Y(Y));
endmodule

module \`SKY``__a331oi_4 (A1, A2, A3, B1, B2, B3, C1, Y);
    input  A1, A2, A3, B1, B2, B3, C1;
    output Y;
    wire   b_and;
    \`SKY``__and3_4 u_b   (.A(B1), .B(B2), .C(B3), .X(b_and));
    \`SKY``__a311oi_4 u_aoi (.A1(A1), .A2(A2), .A3(A3), .B1(b_and), .C1(C1), .Y(Y));
endmodule

// a332oi/a333oi: 3 OR-groups → use NOR3 of three AND outputs.

module \`SKY``__a332oi_1 (A1, A2, A3, B1, B2, B3, C1, C2, Y);
    input  A1, A2, A3, B1, B2, B3, C1, C2;
    output Y;
    wire   a_and, b_and, c_and;
    \`SKY``__and3_1 u_a (.A(A1), .B(A2), .C(A3), .X(a_and));
    \`SKY``__and3_1 u_b (.A(B1), .B(B2), .C(B3), .X(b_and));
    \`SKY``__and2_1 u_c (.A(C1), .B(C2),         .X(c_and));
    \`SKY``__nor3_1 u_n (.A(a_and), .B(b_and), .C(c_and), .Y(Y));
endmodule

module \`SKY``__a332oi_2 (A1, A2, A3, B1, B2, B3, C1, C2, Y);
    input  A1, A2, A3, B1, B2, B3, C1, C2;
    output Y;
    wire   a_and, b_and, c_and;
    \`SKY``__and3_2 u_a (.A(A1), .B(A2), .C(A3), .X(a_and));
    \`SKY``__and3_2 u_b (.A(B1), .B(B2), .C(B3), .X(b_and));
    \`SKY``__and2_2 u_c (.A(C1), .B(C2),         .X(c_and));
    \`SKY``__nor3_2 u_n (.A(a_and), .B(b_and), .C(c_and), .Y(Y));
endmodule

module \`SKY``__a332oi_4 (A1, A2, A3, B1, B2, B3, C1, C2, Y);
    input  A1, A2, A3, B1, B2, B3, C1, C2;
    output Y;
    wire   a_and, b_and, c_and;
    \`SKY``__and3_4 u_a (.A(A1), .B(A2), .C(A3), .X(a_and));
    \`SKY``__and3_4 u_b (.A(B1), .B(B2), .C(B3), .X(b_and));
    \`SKY``__and2_4 u_c (.A(C1), .B(C2),         .X(c_and));
    \`SKY``__nor3_4 u_n (.A(a_and), .B(b_and), .C(c_and), .Y(Y));
endmodule

module \`SKY``__a333oi_1 (A1, A2, A3, B1, B2, B3, C1, C2, C3, Y);
    input  A1, A2, A3, B1, B2, B3, C1, C2, C3;
    output Y;
    wire   a_and, b_and, c_and;
    \`SKY``__and3_1 u_a (.A(A1), .B(A2), .C(A3), .X(a_and));
    \`SKY``__and3_1 u_b (.A(B1), .B(B2), .C(B3), .X(b_and));
    \`SKY``__and3_1 u_c (.A(C1), .B(C2), .C(C3), .X(c_and));
    \`SKY``__nor3_1 u_n (.A(a_and), .B(b_and), .C(c_and), .Y(Y));
endmodule

module \`SKY``__a333oi_2 (A1, A2, A3, B1, B2, B3, C1, C2, C3, Y);
    input  A1, A2, A3, B1, B2, B3, C1, C2, C3;
    output Y;
    wire   a_and, b_and, c_and;
    \`SKY``__and3_2 u_a (.A(A1), .B(A2), .C(A3), .X(a_and));
    \`SKY``__and3_2 u_b (.A(B1), .B(B2), .C(B3), .X(b_and));
    \`SKY``__and3_2 u_c (.A(C1), .B(C2), .C(C3), .X(c_and));
    \`SKY``__nor3_2 u_n (.A(a_and), .B(b_and), .C(c_and), .Y(Y));
endmodule

module \`SKY``__a333oi_4 (A1, A2, A3, B1, B2, B3, C1, C2, C3, Y);
    input  A1, A2, A3, B1, B2, B3, C1, C2, C3;
    output Y;
    wire   a_and, b_and, c_and;
    \`SKY``__and3_4 u_a (.A(A1), .B(A2), .C(A3), .X(a_and));
    \`SKY``__and3_4 u_b (.A(B1), .B(B2), .C(B3), .X(b_and));
    \`SKY``__and3_4 u_c (.A(C1), .B(C2), .C(C3), .X(c_and));
    \`SKY``__nor3_4 u_n (.A(a_and), .B(b_and), .C(c_and), .Y(Y));
endmodule

// ============================================================================
// OAI33 family (inverting):  Y = !((A1+A2+A3) · (B1+B2+B3) · ...)
// ============================================================================

module \`SKY``__o33ai_1 (A1, A2, A3, B1, B2, B3, Y);
    input  A1, A2, A3, B1, B2, B3;
    output Y;
    wire   b_or;
    \`SKY``__or3_1   u_b   (.A(B1), .B(B2), .C(B3), .X(b_or));
    \`SKY``__o31ai_1 u_oai (.A1(A1), .A2(A2), .A3(A3), .B1(b_or), .Y(Y));
endmodule

module \`SKY``__o33ai_2 (A1, A2, A3, B1, B2, B3, Y);
    input  A1, A2, A3, B1, B2, B3;
    output Y;
    wire   b_or;
    \`SKY``__or3_2   u_b   (.A(B1), .B(B2), .C(B3), .X(b_or));
    \`SKY``__o31ai_2 u_oai (.A1(A1), .A2(A2), .A3(A3), .B1(b_or), .Y(Y));
endmodule

module \`SKY``__o33ai_4 (A1, A2, A3, B1, B2, B3, Y);
    input  A1, A2, A3, B1, B2, B3;
    output Y;
    wire   b_or;
    \`SKY``__or3_4   u_b   (.A(B1), .B(B2), .C(B3), .X(b_or));
    \`SKY``__o31ai_4 u_oai (.A1(A1), .A2(A2), .A3(A3), .B1(b_or), .Y(Y));
endmodule

module \`SKY``__o331ai_1 (A1, A2, A3, B1, B2, B3, C1, Y);
    input  A1, A2, A3, B1, B2, B3, C1;
    output Y;
    wire   b_or;
    \`SKY``__or3_1    u_b   (.A(B1), .B(B2), .C(B3), .X(b_or));
    \`SKY``__o311ai_1 u_oai (.A1(A1), .A2(A2), .A3(A3), .B1(b_or), .C1(C1), .Y(Y));
endmodule

module \`SKY``__o331ai_2 (A1, A2, A3, B1, B2, B3, C1, Y);
    input  A1, A2, A3, B1, B2, B3, C1;
    output Y;
    wire   b_or;
    \`SKY``__or3_2    u_b   (.A(B1), .B(B2), .C(B3), .X(b_or));
    \`SKY``__o311ai_2 u_oai (.A1(A1), .A2(A2), .A3(A3), .B1(b_or), .C1(C1), .Y(Y));
endmodule

module \`SKY``__o331ai_4 (A1, A2, A3, B1, B2, B3, C1, Y);
    input  A1, A2, A3, B1, B2, B3, C1;
    output Y;
    wire   b_or;
    \`SKY``__or3_4    u_b   (.A(B1), .B(B2), .C(B3), .X(b_or));
    \`SKY``__o311ai_4 u_oai (.A1(A1), .A2(A2), .A3(A3), .B1(b_or), .C1(C1), .Y(Y));
endmodule

module \`SKY``__o332ai_1 (A1, A2, A3, B1, B2, B3, C1, C2, Y);
    input  A1, A2, A3, B1, B2, B3, C1, C2;
    output Y;
    wire   a_or, b_or, c_or;
    \`SKY``__or3_1   u_a (.A(A1), .B(A2), .C(A3), .X(a_or));
    \`SKY``__or3_1   u_b (.A(B1), .B(B2), .C(B3), .X(b_or));
    \`SKY``__or2_1   u_c (.A(C1), .B(C2),         .X(c_or));
    \`SKY``__nand3_1 u_n (.A(a_or), .B(b_or), .C(c_or), .Y(Y));
endmodule

module \`SKY``__o332ai_2 (A1, A2, A3, B1, B2, B3, C1, C2, Y);
    input  A1, A2, A3, B1, B2, B3, C1, C2;
    output Y;
    wire   a_or, b_or, c_or;
    \`SKY``__or3_2   u_a (.A(A1), .B(A2), .C(A3), .X(a_or));
    \`SKY``__or3_2   u_b (.A(B1), .B(B2), .C(B3), .X(b_or));
    \`SKY``__or2_2   u_c (.A(C1), .B(C2),         .X(c_or));
    \`SKY``__nand3_2 u_n (.A(a_or), .B(b_or), .C(c_or), .Y(Y));
endmodule

module \`SKY``__o332ai_4 (A1, A2, A3, B1, B2, B3, C1, C2, Y);
    input  A1, A2, A3, B1, B2, B3, C1, C2;
    output Y;
    wire   a_or, b_or, c_or;
    \`SKY``__or3_4   u_a (.A(A1), .B(A2), .C(A3), .X(a_or));
    \`SKY``__or3_4   u_b (.A(B1), .B(B2), .C(B3), .X(b_or));
    \`SKY``__or2_4   u_c (.A(C1), .B(C2),         .X(c_or));
    \`SKY``__nand3_4 u_n (.A(a_or), .B(b_or), .C(c_or), .Y(Y));
endmodule

module \`SKY``__o333ai_1 (A1, A2, A3, B1, B2, B3, C1, C2, C3, Y);
    input  A1, A2, A3, B1, B2, B3, C1, C2, C3;
    output Y;
    wire   a_or, b_or, c_or;
    \`SKY``__or3_1   u_a (.A(A1), .B(A2), .C(A3), .X(a_or));
    \`SKY``__or3_1   u_b (.A(B1), .B(B2), .C(B3), .X(b_or));
    \`SKY``__or3_1   u_c (.A(C1), .B(C2), .C(C3), .X(c_or));
    \`SKY``__nand3_1 u_n (.A(a_or), .B(b_or), .C(c_or), .Y(Y));
endmodule

module \`SKY``__o333ai_2 (A1, A2, A3, B1, B2, B3, C1, C2, C3, Y);
    input  A1, A2, A3, B1, B2, B3, C1, C2, C3;
    output Y;
    wire   a_or, b_or, c_or;
    \`SKY``__or3_2   u_a (.A(A1), .B(A2), .C(A3), .X(a_or));
    \`SKY``__or3_2   u_b (.A(B1), .B(B2), .C(B3), .X(b_or));
    \`SKY``__or3_2   u_c (.A(C1), .B(C2), .C(C3), .X(c_or));
    \`SKY``__nand3_2 u_n (.A(a_or), .B(b_or), .C(c_or), .Y(Y));
endmodule

module \`SKY``__o333ai_4 (A1, A2, A3, B1, B2, B3, C1, C2, C3, Y);
    input  A1, A2, A3, B1, B2, B3, C1, C2, C3;
    output Y;
    wire   a_or, b_or, c_or;
    \`SKY``__or3_4   u_a (.A(A1), .B(A2), .C(A3), .X(a_or));
    \`SKY``__or3_4   u_b (.A(B1), .B(B2), .C(B3), .X(b_or));
    \`SKY``__or3_4   u_c (.A(C1), .B(C2), .C(C3), .X(c_or));
    \`SKY``__nand3_4 u_n (.A(a_or), .B(b_or), .C(c_or), .Y(Y));
endmodule
