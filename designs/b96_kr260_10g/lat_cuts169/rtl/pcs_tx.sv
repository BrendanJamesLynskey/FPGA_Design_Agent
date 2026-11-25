// pcs_tx.sv: 10GBASE-R transmit PCS on a 64-bit RAW GT word (brief 96): 64B/66B encode, scramble, 66-to-64 gearbox in ONE register stage.
//
// One clock in 33 the gearbox has no new block to take (32 blocks of 66 bits fill 33 words of 64): `adv` is low then, and the
// MAC (which holds its state while adv is low) must offer nothing new. Registers on the path: gt_d (the output word); the gearbox
// remainder acc and its fill n; the scrambler history. Latency from the MAC's output register: 1 clock for the first bit of a
// block, 2 for its last bit (a block always spills into the next word).
// Brief 169 (FAST = 1): `pre` (combinational, from mac64_tx with FAST_PRE) makes this clock's block the frame's start block (preamble) instead of x_d: the start
// block is a constant, so its scrambled, gearboxed form is computed beside the normal one from the registers only (scrambler history, remainder, fill) and `pre`
// only selects between the two at the registers' inputs. The MAC's own preamble register is skipped by that (one clock less). FAST = 0 (the default): the base file.
module pcs_tx #(
    parameter bit FAST = 1'b0
) (
    input  logic        clk,
    input  logic        rst,
    input  logic [63:0] x_d,       // XGMII word from the MAC (taken when adv is high)
    input  logic [7:0]  x_c,
    input  logic        pre,       // brief 169 (FAST = 1): send the start block this clock (never with adv low)
    output logic        adv,       // low for one clock in 33
    output logic [63:0] gt_d       // to the GT's TXDATA
);
    import b96_pkg::*;
    logic [57:0]  hist;
    logic [63:0]  acc;             // remainder bits, low n bits valid (n up to 64 at the pause)
    logic [6:0]   n;               // 0, 2, ... 62, 64
    logic         pause;           // n == 64
    logic [65:0]  blk;
    logic [63:0]  scr;
    logic [129:0] m;
    assign pause = n[6];           // n == 64 only (63 < n <= 64)
    assign adv = !pause;
    assign blk = enc66(x_d, x_c);
    assign scr = scr_out(hist, blk[65:2]);
    assign m   = {66'd0, acc} | ({64'd0, scr, blk[1:0]} << n);
    logic [65:0]  blk_p;
    logic [63:0]  scr_p;
    logic [129:0] m_p;
    assign blk_p = enc66({8'hD5, 8'h55, 8'h55, 8'h55, 8'h55, 8'h55, 8'h55, X_START}, 8'h01);
    assign scr_p = scr_out(hist, blk_p[65:2]);
    assign m_p   = {66'd0, acc} | ({64'd0, scr_p, blk_p[1:0]} << n);
    always_ff @(posedge clk) begin
        if (rst) begin
            hist <= '0; acc <= '0; n <= '0; gt_d <= '0;
        end else if (pause) begin
            gt_d <= acc;
            acc  <= '0;
            n    <= 7'd0;
        end else if (FAST && pre) begin
            gt_d <= m_p[63:0];
            acc  <= m_p[127:64];
            n    <= n + 7'd2;
            hist <= hist_next(scr_p);
        end else begin
            gt_d <= m[63:0];
            acc  <= m[127:64];
            n    <= n + 7'd2;
            hist <= hist_next(scr);
        end
    end
endmodule
