// fanout_stress.v — high-fanout-net stress test for the buffering flow.
//
// Models the "RAM read-enable" pathology: a single registered control signal
// (read_en) whose load distribution is very heavy — it fans out to the enable
// of N flops. If repair_design does NOT balance this net with a buffer tree,
// the lone driver fights N loads and the launch-FF -> read_en -> enable-pin
// path blows past any tight period. The question this test answers: with the
// fanout fix in place, can the flow buffer read_en well enough to hit 300 ps?
//
// Only read_en is high-fanout. din is a 1-deep shift input (fanout 1); the
// data flops form a shift register so none get constant-pruned, and q observes
// both ends so the whole bank stays live. There is no deep combinational cone,
// so the critical path is read_en's distribution — exactly what we want to test.

module fanout_stress (
    input  wire clk,
    input  wire read_en_in,
    input  wire din,
    output wire q
);
    localparam N = 512;

    reg            read_en;     // registered -> THE high-fanout source (fanout N)
    reg  [N-1:0]   data;

    always @(posedge clk)
        read_en <= read_en_in;

    always @(posedge clk)
        if (read_en)                      // one enable net -> N flop enables
            data <= {data[N-2:0], din};   // shift keeps every bit live

    assign q = data[0] ^ data[N-1];       // observe both ends -> 1 output pin
endmodule
