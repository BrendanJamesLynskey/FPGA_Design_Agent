// Reset synchroniser: asynchronous assert, synchronous release; active-high output.
module v2_e_cmd_exec_reset_sync (
    input  logic clk,
    input  logic rst_n_async,
    output logic rst
);
    (* ASYNC_REG = "TRUE" *) logic s1;
    (* ASYNC_REG = "TRUE" *) logic s2;
    always_ff @(posedge clk or negedge rst_n_async) begin
        if (!rst_n_async) begin
            s1 <= 1'b1;
            s2 <= 1'b1;
        end else begin
            s1 <= 1'b0;
            s2 <= s1;
        end
    end
    assign rst = s2;
endmodule
