// Two-flop reset synchroniser: CPU_RESETN (async, active low) to active-high synchronous reset.
module v2_e_cmd_exec_rst_sync (
    input  logic clk,
    input  logic resetn_async,
    output logic rst
);
    (* ASYNC_REG = "TRUE" *) logic q1;
    (* ASYNC_REG = "TRUE" *) logic q2;
    always_ff @(posedge clk) begin
        q1 <= resetn_async;
        q2 <= q1;
    end
    assign rst = ~q2;
endmodule
