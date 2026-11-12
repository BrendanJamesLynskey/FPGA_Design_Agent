// axis_tx_source (and axis_tx_sink.sv): the transactor's AXI4-Stream ends (brief 59A).
//
// Source: one packet per start. Beat k carries the 32-bit word first + k (replicated across wider TDATA); TKEEP (and TSTRB,
// equal to it) is all ones except on the last beat, which carries keep_last; TLAST on the last beat unless no_last.
// Before raising TVALID for each beat it waits another cycle while thr[7:0] < valid_p.
//
// Sink: TREADY is high in a cycle when thr[15:8] <= ready_p. The sequencer pushes what each packet should look like
// (the same fields as the source's) into a 16-entry expectation FIFO; every received beat is compared with it:
// data (kept bytes only), TKEEP, TLAST position, and beats with nothing expected. A packet that ends early (TLAST before
// its length) or late (no TLAST on its last beat) counts one TLAST mismatch and the sink moves to the next expectation.
/* verilator lint_off UNUSEDSIGNAL */   // each end uses one byte of the throttle LFSR
module axis_tx_source #(
    parameter int DATA_W = 32
) (
    input  logic                clk,
    input  logic                rst,
    input  logic                start,
    input  logic [15:0]         len,
    input  logic [31:0]         first,
    input  logic [DATA_W/8-1:0] keep_last,
    input  logic                no_last,
    input  logic [31:0]         thr,
    input  logic [7:0]          valid_p,
    output logic                busy,
    output logic [DATA_W-1:0]   tdata,
    output logic [DATA_W/8-1:0] tkeep,
    output logic [DATA_W/8-1:0] tstrb,
    output logic                tlast,
    output logic                tvalid,
    input  logic                tready
);
    localparam int KW = DATA_W / 8;
    logic        active = 1'b0, v = 1'b0, nl = 1'b0;
    logic [15:0] n = '0, k = '0;
    logic [31:0] w0 = '0;
    logic [KW-1:0] kl = '0;
    wire last_beat = (k == n - 1'b1);
    wire go = (thr[7:0] >= valid_p);
    assign busy   = active;
    assign tvalid = v;
    assign tdata  = {(DATA_W / 32){w0 + 32'(k)}};
    assign tkeep  = last_beat ? kl : {KW{1'b1}};
    assign tstrb  = tkeep;
    assign tlast  = last_beat && !nl;
    always_ff @(posedge clk) begin
        if (rst) begin
            active <= 1'b0; v <= 1'b0;
        end else if (!active) begin
            if (start) begin active <= 1'b1; n <= (len == 0) ? 16'd1 : len; k <= '0; w0 <= first; kl <= keep_last; nl <= no_last; end
        end else if (!v) begin
            if (go) v <= 1'b1;
        end else if (tready) begin
            if (last_beat) begin active <= 1'b0; v <= 1'b0; end
            else begin k <= k + 1'b1; v <= go; end          // the next beat back to back when the draw allows
        end
    end
endmodule
/* verilator lint_on UNUSEDSIGNAL */
