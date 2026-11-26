// mac64_tx_fv_top.sv (brief 158): the proof harness: mac64_tx with free inputs (any source behaviour, any pause pattern).
module mac64_tx_fv_top (
    input logic clk, rst, adv, s_valid, s_last, s_poison,
    input logic [63:0] s_data,
    input logic [2:0]  s_nb1
);
    logic s_ready, sop, eop, underrun;
    logic [63:0] x_d;
    logic [7:0]  x_c;
    mac64_tx dut (.*);
endmodule
