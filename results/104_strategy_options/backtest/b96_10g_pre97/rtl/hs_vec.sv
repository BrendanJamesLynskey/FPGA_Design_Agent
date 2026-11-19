// hs_vec.sv: a vector crossing between two clock domains by the XPM request/acknowledge handshake, repeated forever, so the
// destination copy is always a coherent copy of the source vector (never a mix of two values), a few clocks old. Used for the
// configuration (clk -> tx and rx domains) and for the status and counter snapshots (tx and rx domain -> clk).
// The source clock must run for a transfer to complete; until then the destination keeps its reset value.
module hs_vec #(
    parameter int W = 32
) (
    input  logic         src_clk,
    input  logic [W-1:0] src_vec,
    input  logic         dst_clk,
    output logic [W-1:0] dst_vec
);
    logic [W-1:0] sv, dv;
    logic         send = 1'b0, rcv, req, ack = 1'b0;
    always_ff @(posedge src_clk) begin
        if (!send && !rcv) begin sv <= src_vec; send <= 1'b1; end
        else if (rcv) send <= 1'b0;
    end
    xpm_cdc_handshake #(.DEST_EXT_HSK(1), .DEST_SYNC_FF(4), .INIT_SYNC_FF(0), .SIM_ASSERT_CHK(0), .SRC_SYNC_FF(4), .WIDTH(W)) u_hs (
        .src_clk, .src_in(sv), .src_send(send), .src_rcv(rcv),
        .dest_clk(dst_clk), .dest_out(dv), .dest_req(req), .dest_ack(ack));
    initial dst_vec = '0;
    always_ff @(posedge dst_clk) begin
        ack <= req;
        if (req) dst_vec <= dv;
    end
endmodule
