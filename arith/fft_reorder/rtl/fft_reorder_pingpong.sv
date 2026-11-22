// fft_reorder_pingpong: bit-reverse reorder buffer, two banks (arith brief 148, variant "pingpong").
//
// Function (arith/fft_reorder/spec.md): a frame of N = 2**LOGN words arrives in N consecutive clocks (in_valid, the first word marked by in_sof) and the same words
// leave in N consecutive clocks in bit-reversed order of their position: the word that arrived at position p leaves at position bitrev(p) (LOGN bits). Applied to a
// bit-reversed stream it gives natural order and the reverse (bit reversal is its own inverse). Frames may follow each other with no gap: the words of one frame are
// written into one bank while the previous frame is read from the other. Latency, from the clock of in_sof to the clock of out_sof: N + 1.
//
// Rules: in_sof is asserted with the first word and the next N-1 clocks all have in_valid (a gap inside a frame is not allowed); a new in_sof inside a frame restarts the frame.
// rst clears the control state (valid flags and counters); the bank contents are data and are not reset.
//
// Intended primitive use (stated before any Vivado run; not yet measured): two RAMs of N x WD bits with one write and one read port each (RAMB36/RAMB18, or distributed RAM for N <= 64),
// 2 * N * WD bits in all (for example 2 * 1024 * 32 = 64 Kbit = 2 RAMB36 at N = 1024, WD = 32); about 4 * LOGN LUTs of control.
module fft_reorder_pingpong #(
    parameter int LOGN = 6,
    parameter int WD   = 32
) (
    input  logic            clk,
    input  logic            rst,
    input  logic            in_valid,
    input  logic            in_sof,
    input  logic [WD-1:0]   in_d,
    output logic            out_valid,
    output logic            out_sof,
    output logic [WD-1:0]   out_d
);
    localparam int N = 1 << LOGN;
    logic [WD-1:0] mem0 [N];
    logic [WD-1:0] mem1 [N];
    logic [LOGN-1:0] wc, wpos;            // write counter, position of the word arriving now
    logic            wb;                  // bank being written
    logic            rd_on, rd_bank;      // reading, and the bank being read
    logic [LOGN-1:0] rc;
    logic [LOGN-1:0] ra;
    logic            last_in;
    logic            v1, s1, b1;          // read data valid, first word, bank, one clock after the address
    logic [WD-1:0]   rd0, rd1;
    fft_bitrev #(.LOGN(LOGN)) u_rev (.a(rc), .y(ra));
    always_comb begin
        wpos    = in_sof ? '0 : wc;
        last_in = in_valid && (wpos == LOGN'(N - 1));
    end
    always_ff @(posedge clk) begin
        if (in_valid) begin
            if (wb) mem1[wpos] <= in_d;
            else    mem0[wpos] <= in_d;
        end
        rd0 <= mem0[ra];
        rd1 <= mem1[ra];
    end
    always_ff @(posedge clk) begin
        if (rst) begin
            wc <= '0; wb <= 1'b0; rd_on <= 1'b0; rc <= '0; rd_bank <= 1'b0; v1 <= 1'b0; s1 <= 1'b0; b1 <= 1'b0;
        end else begin
            if (in_valid) wc <= wpos + 1'b1;
            if (last_in) begin
                wb      <= ~wb;
                rd_bank <= wb;
            end
            // the read of a finished frame starts in the clock after its last word and takes N clocks
            if (last_in) begin
                rd_on <= 1'b1;
                rc    <= '0;
            end else if (rd_on) begin
                rc <= rc + 1'b1;
                if (rc == LOGN'(N - 1)) rd_on <= 1'b0;
            end
            v1 <= rd_on;
            s1 <= rd_on && (rc == '0);
            b1 <= rd_bank;
        end
    end
    always_comb begin
        out_valid = v1;
        out_sof   = s1;
        out_d     = b1 ? rd1 : rd0;
    end
endmodule
