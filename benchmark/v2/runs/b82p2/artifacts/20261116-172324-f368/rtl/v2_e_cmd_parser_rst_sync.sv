// Reset synchroniser: asynchronous assert, synchronous release; output active high.
module v2_e_cmd_parser_rst_sync (
    input  logic clk,
    input  logic arstn,
    output logic rst
);
    (* ASYNC_REG = "TRUE" *) logic [1:0] q;
    always_ff @(posedge clk or negedge arstn) begin
        if (!arstn) q <= 2'b00;
        else        q <= {q[0], 1'b1};
    end
    assign rst = ~q[1];
endmodule
