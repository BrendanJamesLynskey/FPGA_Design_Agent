// prbs64.sv: the fabric PRBS generator and checker for the 64-bit GTH user data path (brief 56A).
//
// One sequence: the maximal-length LFSR x^n + x^k + 1 (n,k) = PRBS-7 (7,6), PRBS-15 (15,14), PRBS-23 (23,18), PRBS-31 (31,28)
// (the same polynomials as the GTH's own generator, UG576 table 3-23; the starting phase is ours). The state shifts left,
// the new bit is st[n-1] ^ st[k-1] and enters at st[0]. A 64-bit word holds 64 consecutive output bits, bit 0 first, so on
// the GTH (TXDATA[0] is sent first) the line carries the sequence in order.
//
// The checker is NOT self-synchronising: once locked it free-runs its own copy of the generator and compares word by word,
// so each line error counts as one bit error (a self-synchronising checker would count up to 3 per error, one per tap).
// SEARCH: load the state from each received word and expect the next word to continue it; CHECKER_LOCK_WORDS error-free
// words in a row lock it (an all-zero state never counts, so a dead receiver does not lock). LOCKED: count differing bits;
// LOSS_ERRS or more bad bits in a word, LOSS_WORDS words running, drops back to SEARCH. Three clocks of pipeline latency.

package prbs64_pkg;
    // register mask of each polynomial (the state holds n bits)
    function automatic logic [30:0] pmask(input logic [1:0] sel);
        case (sel)
            2'd0:    return 31'h0000_007F;
            2'd1:    return 31'h0000_7FFF;
            2'd2:    return 31'h007F_FFFF;
            default: return 31'h7FFF_FFFF;
        endcase
    endfunction
    // advance the LFSR 64 bits: returns {state after, the 64 bits}. Written with whole-variable operations and variable
    // indexes only (no constant part selects), which every simulator in the flow handles inside always_comb.
    function automatic logic [94:0] step(input logic [30:0] s, input logic [1:0] sel);
        logic [30:0] st, m; logic [63:0] d; logic nb; int n, k;
        case (sel)
            2'd0: begin n = 7;  k = 6;  end
            2'd1: begin n = 15; k = 14; end
            2'd2: begin n = 23; k = 18; end
            default: begin n = 31; k = 28; end
        endcase
        m = pmask(sel);
        st = s & m; d = '0;
        for (int i = 0; i < 64; i++) begin
            nb = st[n-1] ^ st[k-1];
            st = ((st << 1) | 31'(nb)) & m;
            d[i] = nb;
        end
        return {st, d};
    endfunction
    // the state after a received word: its last n bits, newest (bit 63) in bit 0
    function automatic logic [30:0] load(input logic [63:0] w, input logic [1:0] sel);
        logic [30:0] l;
        l = '0;
        for (int j = 0; j < 31; j++) l[j] = w[63 - j];
        return l & pmask(sel);
    endfunction
endpackage

module prbs_gen64 (
    input  logic        clk,
    input  logic        rst,
    input  logic [1:0]  sel,          // 0 PRBS-7, 1 PRBS-15, 2 PRBS-23, 3 PRBS-31 (changing it restarts the sequence)
    input  logic        en,           // one word per clock while high; low holds the state
    input  logic        force_err,    // pulse: flip bit 0 of the next word (one injected line error)
    output logic [63:0] data
);
    logic [30:0] st;
    logic [1:0]  sel_q;
    logic [94:0] nx;
    logic        err_pend;
    assign nx = prbs64_pkg::step(st, sel);
    always_ff @(posedge clk) begin
        sel_q <= sel;
        if (rst || sel != sel_q) begin st <= 31'h7FFF_FFFF; data <= '0; err_pend <= 1'b0; end
        else begin
            if (force_err) err_pend <= 1'b1;
            if (en) begin
                st <= nx[94:64];
                data <= nx[63:0] ^ {63'd0, err_pend};
                if (err_pend && !force_err) err_pend <= 1'b0;
            end
        end
    end
endmodule

module prbs_chk64 #(
    parameter int CHECKER_LOCK_WORDS = 4,
    parameter int LOSS_ERRS  = 16,
    parameter int LOSS_WORDS = 4
) (
    input  logic        clk,
    input  logic        rst,
    input  logic [1:0]  sel,
    input  logic        en,           // data is valid this clock
    input  logic [63:0] data,
    input  logic        clr,          // pulse: zero the counters (the lock state is kept)
    output logic        locked,
    output logic        lost_pulse,   // one clock when a lock is dropped
    output logic [63:0] words,        // words compared while locked
    output logic [63:0] err_bits,     // bits that differed while locked
    output logic [31:0] err_words,    // words with at least one differing bit while locked
    output logic [15:0] lock_losses
);
    // Pipeline (timing at the 161 MHz user clock, brief 56A): 1 expected word from the state, 2 xor and four 16-bit popcounts,
    // 3 their sum, 4 lock logic and counters. The result reaches the counters three clocks after the data.
    // While `follow` is low the state is reloaded from every received word; once locked it free-runs. Whichever way follow
    // changes, the state is the state after the previous word, so the next expected word is right (no alignment to the lag).
    logic [30:0]  st, ld;
    logic [94:0]  nx;
    logic         follow;
    logic [63:0]  d1, e1;
    logic         v1, v2, v3, ev1, ev2, ev3;
    logic [4:0]   pc0, pc1, pc2, pc3;
    logic [6:0]   nerr;
    logic [1:0]   sel_q;
    logic [7:0]   good, bad;
    assign nx = prbs64_pkg::step(st, sel);
    assign ld = prbs64_pkg::load(data, sel);
    logic [63:0] x2;
    assign x2 = d1 ^ e1;
    always_ff @(posedge clk) begin
        lost_pulse <= 1'b0;
        sel_q <= sel;
        if (rst || sel != sel_q) begin
            locked <= 1'b0; follow <= 1'b0; good <= '0; bad <= '0; st <= '0;
            v1 <= 1'b0; v2 <= 1'b0; v3 <= 1'b0; ev1 <= 1'b0; ev2 <= 1'b0; ev3 <= 1'b0;
            words <= '0; err_bits <= '0; err_words <= '0; lock_losses <= '0;
        end else begin
            // stage 1
            v1 <= en;
            if (en) begin
                d1 <= data; e1 <= nx[63:0]; ev1 <= (st != 31'd0);
                st <= follow ? nx[94:64] : ld;
            end
            // stage 2
            v2 <= v1; ev2 <= ev1;
            pc0 <= 5'($countones(x2[15:0]));  pc1 <= 5'($countones(x2[31:16]));
            pc2 <= 5'($countones(x2[47:32])); pc3 <= 5'($countones(x2[63:48]));
            // stage 3
            v3 <= v2; ev3 <= ev2;
            nerr <= 7'(pc0) + 7'(pc1) + 7'(pc2) + 7'(pc3);
            // stage 4
            if (v3) begin
                if (!locked) begin
                    if (nerr == 7'd0 && ev3) begin
                        good <= good + 8'd1;
                        if (good + 8'd1 >= 8'(CHECKER_LOCK_WORDS)) begin locked <= 1'b1; follow <= 1'b1; good <= '0; bad <= '0; end
                    end else good <= '0;
                end else begin
                    words <= words + 64'd1;
                    err_bits <= err_bits + 64'(nerr);
                    if (nerr != 7'd0) err_words <= err_words + 32'd1;
                    if (nerr >= 7'(LOSS_ERRS)) begin
                        bad <= bad + 8'd1;
                        if (bad + 8'd1 >= 8'(LOSS_WORDS)) begin
                            locked <= 1'b0; follow <= 1'b0; bad <= '0; good <= '0; lost_pulse <= 1'b1;
                            lock_losses <= lock_losses + 16'd1;
                        end
                    end else bad <= '0;
                end
            end
        end
        if (clr) begin words <= '0; err_bits <= '0; err_words <= '0; lock_losses <= '0; end
    end
endmodule
