// adder_tree8.sv: a balanced tree summing eight 8-bit unsigned values (brief 101's adder-tree block). Combinational between
// its ports; the wrapper registers both ends. Three levels of two-input adds, so Vivado and Yosys are free to merge them
// (ternary adders, carry chains) as they choose. (Eight inputs: the 16 x 12-bit tree of the first attempt could not be
// proved by eqy within an hour, see docs/oss_synth_eqy.md.)
`default_nettype none
module adder_tree8 (
    input  wire logic [63:0] a,        // eight 8-bit values, value 0 in the low bits
    output logic [10:0]      s
);
    logic [8:0]  l1 [4];
    logic [9:0]  l2 [2];
    always_comb begin
        for (int i = 0; i < 4; i++) l1[i] = 9'(a[16 * i +: 8]) + 9'(a[16 * i + 8 +: 8]);
        for (int i = 0; i < 2; i++) l2[i] = 10'(l1[2 * i]) + 10'(l1[2 * i + 1]);
        s = 11'(l2[0]) + 11'(l2[1]);
    end
endmodule
