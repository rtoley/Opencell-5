// 8-bit synchronous up-counter — smoke-test design for OpenCell-7 flow.
// Synthesizes to ~8 DFFs + some NAND/NOR/INV chains.
// If this passes through Yosys + OpenSTA on the library, the flow works.

module counter (
    input  wire        clk,
    input  wire        rst_n,
    output wire [7:0]  count
);
    reg [7:0] cnt_r;

    always @(posedge clk) begin
        if (!rst_n) cnt_r <= 8'h00;
        else        cnt_r <= cnt_r + 8'h01;
    end

    assign count = cnt_r;
endmodule
