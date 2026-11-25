// xpm_cdc_sync_rst stand-in (lint only): a plain synchroniser of the same ports.
module xpm_cdc_sync_rst #(parameter int DEST_SYNC_FF = 4, parameter int INIT = 1, parameter int INIT_SYNC_FF = 0, parameter int SIM_ASSERT_CHK = 0) (
    input logic src_rst, input logic dest_clk, output logic dest_rst
);
    logic [3:0] q;
    always_ff @(posedge dest_clk) q <= {q[2:0], src_rst};
    assign dest_rst = q[3];
    logic unused;
    assign unused = &{1'b0, DEST_SYNC_FF[0], INIT[0], INIT_SYNC_FF[0], SIM_ASSERT_CHK[0]};
endmodule
