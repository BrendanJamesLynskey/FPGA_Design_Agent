// Reset synchroniser: asynchronous assert, synchronous release. Output active high.
module v2_e_tlm_pacer_rst_sync (
    input  logic clk,
    input  logic arst_n,
    output logic rst
);
    (* ASYNC_REG = "TRUE" *) logic q1;
    (* ASYNC_REG = "TRUE" *) logic q2;
    always_ff @(posedge clk or negedge arst_n) begin
        if (!arst_n) begin
            q1 <= 1'b0;
            q2 <= 1'b0;
        end else begin
            q1 <= 1'b1;
            q2 <= q1;
        end
    end
    assign rst = ~q2;
endmodule
