`timescale 1ns/1ps
// line_channel.sv: the bit-level channel between the transmit PCS's TXDATA and the receive PCS's RXDATA (brief 112). A bit FIFO that can insert
// or delete single bits (a slipped receiver alignment), with an initial fill that sets the first alignment (init_off bits), and two fault
// injectors at its input: a word XOR mask (bit errors) and a burst of corrupted sync headers (both header bits forced to 0 for hdr_cnt blocks, hdr_skip
// good blocks between two corrupted ones). The pre-stream fill is a run of valid sync headers ('01' every 66 bits), so a start-up offset of 0 mod 66
// is already block-aligned and the receiver locks with no slip.
// The stream's own bit counter starts at its first valid word, so block headers sit at bit positions 66k whatever the later slips. In line mode
// the stream comes from the line agent (drv_*); otherwise from pcs_tx, whose first word after reset is word 0 of the stream (the register's
// reset value one clock earlier is skipped).
module line_channel (
    input  logic        clk,
    input  logic        rst,
    input  logic        line_mode,
    input  int unsigned init_off,
    input  logic [63:0] tx_word,
    input  logic [63:0] drv_word,
    input  logic        drv_valid,
    input  logic        drv_first,
    input  logic [63:0] flip_mask,
    input  logic        hdr_load,
    input  logic [15:0] hdr_cnt,
    input  logic [7:0]  hdr_skip,
    input  logic        slip_ins,
    input  logic        slip_del,
    output logic [63:0] out_word
);
    localparam int PRE = 260;          // bits of pre-stream fill: valid headers only, so the receiver can lock on the fill's own grid
    logic          rst_d, tx_valid, tx_valid_d, started;
    logic [767:0]  fifo;
    int            fill, pad, absn;
    longint        bitpos;
    int            hdr_n, skip_n, skip_cfg;
    logic          cur_bad;
    logic [63:0]   w;
    logic [127:0]  nb;
    logic          in_valid, in_first;
    assign tx_valid = !rst && !rst_d;
    assign in_valid = line_mode ? drv_valid : tx_valid;
    assign in_first = line_mode ? drv_first : (tx_valid && !tx_valid_d);
    always_ff @(posedge clk) begin
        rst_d <= rst;
        tx_valid_d <= tx_valid;
        if (rst) begin
            fifo = '0; hdr_n = 0; skip_n = 0; skip_cfg = 0; cur_bad = 1'b0; bitpos = 0; started = 1'b0;
            for (int b = 0; b < PRE; b++) fifo[b] = ((b % 66) == 0);
            // the receiver's first edge after reset captures this word, word 0 of the fill; the first pop after reset gives word 1
            out_word <= fifo[63:0]; fifo = fifo >> 64; fill = PRE - 64; absn = PRE;
        end else begin
            if (hdr_load) begin hdr_n = int'(hdr_cnt); skip_cfg = int'(hdr_skip); skip_n = 0; end
            if (in_valid) begin
                if (in_first || !started) begin
                    // pad the fill so the first stream bit lands init_off bits after a multiple of 66 on the receiver's grid
                    pad = (int'(init_off % 66) - (absn % 66) + 66) % 66;
                    for (int b = 0; b < pad; b++) fifo[fill + b] = (((absn + b) % 66) == 0);
                    fill = fill + pad; absn = absn + pad; bitpos = 0; started = 1'b1;
                end
                w = (line_mode ? drv_word : tx_word) ^ flip_mask;
                for (int i = 0; i < 64; i++) begin
                    longint pos; int r;
                    pos = bitpos + i; r = int'(pos % 66);
                    if (r == 0) cur_bad = (hdr_n > 0 && skip_n == 0);
                    if (cur_bad && r < 2) w[i] = 1'b0;
                    if (r == 1) begin
                        if (cur_bad) begin hdr_n = hdr_n - 1; skip_n = skip_cfg; cur_bad = 1'b0; end
                        else if (skip_n > 0) skip_n = skip_n - 1;
                    end
                end
                bitpos = bitpos + 64;
                if (slip_ins) begin nb = {63'd0, w, 1'b0}; fifo = fifo | (768'(nb) << fill); fill = fill + 65; absn = absn + 65; end
                else if (slip_del && fill > 100) begin nb = {64'd0, w >> 1}; fifo = fifo | (768'(nb) << fill); fill = fill + 63; absn = absn + 63; end
                else begin nb = {64'd0, w}; fifo = fifo | (768'(nb) << fill); fill = fill + 64; absn = absn + 64; end
            end
            if (fill >= 64) begin out_word <= fifo[63:0]; fifo = fifo >> 64; fill = fill - 64; end
            else out_word <= '0;
        end
    end
endmodule
