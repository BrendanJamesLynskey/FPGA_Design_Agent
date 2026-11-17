// rst_sync: CPU_RESETN (active low, asynchronous) to an active-high reset that
// asserts asynchronously and releases synchronously. xpm_cdc_async_rst in the
// build; a behavioural twin in simulation, where the XPM library is absent.
module rst_sync (
    input  logic clk,
    input  logic rst_n_async,
    output logic rst
);
`ifdef SYNTHESIS
    xpm_cdc_async_rst #(
        .DEST_SYNC_FF(4), .INIT_SYNC_FF(0), .RST_ACTIVE_HIGH(1)
    ) u_xpm (
        .dest_arst(rst), .dest_clk(clk), .src_arst(~rst_n_async)
    );
`else
    (* ASYNC_REG = "TRUE" *) logic [3:0] q;
    always_ff @(posedge clk or negedge rst_n_async) begin
        if (!rst_n_async) q <= 4'hF;
        else              q <= {q[2:0], 1'b0};
    end
    assign rst = q[3];
`endif
endmodule
