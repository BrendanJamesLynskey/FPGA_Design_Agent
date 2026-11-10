// C9: xpm_cdc_handshake with an external destination handshake.
module cdcfx_c9 (input logic clk_a, input logic clk_b, input logic send, input logic [15:0] din, output logic busy,
                 output logic dvalid, output logic [15:0] dout);
    logic [15:0] data = '0, d_o;
    logic snd = 1'b0, rcv, dreq, dack = 1'b0, bsy = 1'b0;
    xpm_cdc_handshake #(.DEST_EXT_HSK(1), .DEST_SYNC_FF(3), .SRC_SYNC_FF(3), .WIDTH(16))
        u_x (.src_clk(clk_a), .src_in(data), .src_send(snd), .src_rcv(rcv), .dest_clk(clk_b), .dest_out(d_o),
             .dest_req(dreq), .dest_ack(dack));
    always_ff @(posedge clk_a) begin
        if (!bsy && !rcv) begin
            if (send) begin data <= din; snd <= 1'b1; bsy <= 1'b1; end
        end else if (snd && rcv) snd <= 1'b0;
        else if (!snd && !rcv) bsy <= 1'b0;
    end
    assign busy = bsy;
    always_ff @(posedge clk_b) begin
        dvalid <= 1'b0;
        if (dreq && !dack) begin dout <= d_o; dvalid <= 1'b1; dack <= 1'b1; end
        else if (!dreq) dack <= 1'b0;
    end
endmodule
