// Reg -> exactly N XOR2 gates in a serial chain -> Reg. Depth = N logic levels.
module dut #(parameter N=32) (input clk, input [63:0] din, output reg dout);
  reg [63:0] r;
  always @(posedge clk) r <= din;          // input register
  wire [N:0] node;
  assign node[0] = r[0];
  genvar i;
  generate for (i=0;i<N;i=i+1) begin : L
    (* keep = "true" *) wire g;
    assign g = node[i] ^ r[(i+1) & 63];     // one XOR2 per level, kept
    assign node[i+1] = g;
  end endgenerate
  always @(posedge clk) dout <= node[N];   // output register
endmodule
module d8  (input clk, input [63:0] din, output dout); dut #(8)  u(clk,din,dout); endmodule
module d16 (input clk, input [63:0] din, output dout); dut #(16) u(clk,din,dout); endmodule
module d32 (input clk, input [63:0] din, output dout); dut #(32) u(clk,din,dout); endmodule
module d48 (input clk, input [63:0] din, output dout); dut #(48) u(clk,din,dout); endmodule
