// C8: hand-built 4-phase handshake: data held while req/ack cross through 2-flop ASYNC_REG chains.
module cdcfx_c8 (input logic clk_a, input logic clk_b, input logic send, input logic [15:0] din, output logic busy,
                 output logic dvalid, output logic [15:0] dout);
    logic [15:0] data = '0;
    logic req = 1'b0, bsy = 1'b0;
    (* ASYNC_REG = "TRUE" *) logic [1:0] ack_s = 2'b00;
    (* ASYNC_REG = "TRUE" *) logic [1:0] req_s = 2'b00;
    logic ack = 1'b0;
    always_ff @(posedge clk_a) begin
        ack_s <= {ack_s[0], ack};
        if (!bsy) begin
            if (send && !ack_s[1]) begin data <= din; req <= 1'b1; bsy <= 1'b1; end
        end else if (req && ack_s[1]) req <= 1'b0;
        else if (!req && !ack_s[1]) bsy <= 1'b0;
    end
    assign busy = bsy;
    always_ff @(posedge clk_b) begin
        req_s <= {req_s[0], req};
        dvalid <= 1'b0;
        if (req_s[1] && !ack) begin dout <= data; dvalid <= 1'b1; ack <= 1'b1; end
        else if (!req_s[1]) ack <= 1'b0;
    end
endmodule
