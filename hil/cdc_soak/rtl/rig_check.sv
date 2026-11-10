`timescale 1ns / 1ps
// rig_check.sv: per-copy sources, checkers and the saturating record (design section 4).
//
// Every checker lives in the copy's destination domain and gives one-cycle pulses: err, ev (event), lock (lock-up)
// and relock (an allowed resynchronisation after a reset; not an error). rec_cnt counts them. Its 73-bit record
// {errors 24, events 32, lockups 8, relocks 8, sat 1} doubles as one link of a rotating shift chain: while the
// domain is frozen, each sh pulse moves the whole chain one bit, and after 73 x (copies in the chain) pulses every
// record is back where it was.

module rec_cnt #(
    parameter int EW = 24,                 // errors (saturating)
    parameter int VW = 32,                 // events (wrapping; the host differences epochs)
    parameter int LW = 8,                  // lock-ups (saturating)
    parameter int RW = 8                   // relocks (saturating)
) (
    input  logic clk,
    input  logic frz,
    input  logic sh,
    input  logic sin,
    output logic sout,
    input  logic e_err,
    input  logic e_ev,
    input  logic e_lock,
    input  logic e_relock
);
    localparam int N = EW + VW + LW + RW + 1;
    logic [N-1:0] r = '0;
    wire  [EW-1:0] err = r[N-1 -: EW];
    wire  [VW-1:0] ev  = r[N-1-EW -: VW];
    wire  [LW-1:0] lk  = r[N-1-EW-VW -: LW];
    wire  [RW-1:0] rl  = r[RW:1];
    wire           sat = r[0];
    always_ff @(posedge clk)
        if (sh) r <= {r[N-2:0], sin};
        else if (!frz) begin
            if (e_err && !(&err)) r[N-1 -: EW]       <= err + 1'b1;
            if (e_ev)             r[N-1-EW -: VW]    <= ev + 1'b1;
            if (e_lock && !(&lk)) r[N-1-EW-VW -: LW] <= lk + 1'b1;
            if (e_relock && !(&rl)) r[RW:1]          <= rl + 1'b1;
            if (e_err && (&err))  r[0]               <= 1'b1;
        end
    assign sout = r[N-1];
endmodule

// Source of events for the single-bit crossings: an event every MINGAP + (0..63) source cycles while run.
// tog toggles on each event, pls is high for the event cycle, cnt counts events (for the Gray reference).
module src_ev #(
    parameter logic [15:0] SEED   = 16'h1D0F,
    parameter int          MINGAP = 16
) (
    input  logic       clk,
    input  logic       rst,
    input  logic       run,
    output logic       tog,
    output logic       pls,
    output logic [7:0] cnt
);
    logic [15:0] lf;
    logic [7:0]  gap = 8'(MINGAP);
    logic        t = 1'b0, p = 1'b0;
    logic [7:0]  c = '0;
    lfsr16 #(.SEED(SEED)) u_lf (.clk(clk), .rst(1'b0), .en(1'b1), .q(lf));
    always_ff @(posedge clk)
        if (rst) begin
            gap <= 8'(MINGAP); t <= 1'b0; p <= 1'b0; c <= '0;
        end else begin
            p <= 1'b0;
            if (gap != 0) gap <= gap - 1'b1;
            else if (run) begin
                t <= ~t; p <= 1'b1; c <= c + 1'b1;
                gap <= 8'(MINGAP) + {2'b00, lf[5:0]};
            end
        end
    assign tog = t;
    assign pls = p;
    assign cnt = c;
endmodule

// Event checker (level and pulse crossings): the source's event count arrives through a correct xpm_cdc_gray
// (ref). At each quiet point (QUIET destination cycles with no event and no change of ref) the destination's own
// event count must match ref; a mismatch is one error and is then absorbed, so a lost or extra event counts once.
// glitch: a level that changes again within GLITCH cycles of its last change is an error too (level crossings).
module chk_events #(
    parameter int QUIET  = 16,
    parameter int GLITCH = 2
) (
    input  logic       clk,
    input  logic       ev,            // an event seen in the destination (one cycle)
    input  logic [7:0] ref_cnt,
    input  logic       lvl_chk,       // 1: ev is a level change, check its spacing
    output logic       e_err,
    output logic       e_ev
);
    logic [7:0] cnt = '0, offs = '0, refp = '0;
    logic [7:0] q = '0;
    logic [3:0] rl = 4'hF;
    logic       done = 1'b0;
    wire  [7:0] diff = ref_cnt - (cnt + offs);
    always_ff @(posedge clk) begin
        e_err <= 1'b0;
        e_ev  <= ev;
        refp  <= ref_cnt;
        if (ev) cnt <= cnt + 1'b1;
        if (ev || ref_cnt != refp) begin
            q <= '0; done <= 1'b0;
        end else if (q != 8'(QUIET)) q <= q + 1'b1;
        else if (!done) begin
            done <= 1'b1;
            if (diff != 0) begin e_err <= 1'b1; offs <= offs + diff; end
        end
        if (ev) begin
            rl <= '0;
            if (lvl_chk && rl < 4'(GLITCH)) e_err <= 1'b1;
        end else if (rl != 4'hF) rl <= rl + 1'b1;
    end
endmodule

// Gray / binary counter checker: the decoded value never goes backwards and never steps by more than MAXSTEP;
// with RAWCHK the raw Gray bus also changes by at most one bit between destination samples.
module chk_count #(
    parameter int MAXSTEP = 2,
    parameter bit RAWCHK  = 1'b0
) (
    input  logic        clk,
    input  logic [11:0] v,
    input  logic [11:0] raw,
    output logic        e_err,
    output logic        e_ev
);
    logic [11:0] vp = '0, rp = '0;
    wire  [11:0] step = v - vp;
    always_ff @(posedge clk) begin
        vp    <= v;
        rp    <= raw;
        e_ev  <= step != 0;
        e_err <= (step > 12'(MAXSTEP)) || (RAWCHK && rig_pkg::popcount12(raw ^ rp) > 1);
    end
endmodule

// Word checker (handshakes and FIFOs): each word must be the PRBS-16 successor of the last. A mismatch is a relock
// if the budget allows (one per reset event, armed by arm; one at power-up), otherwise an error. The watchdog counts
// a lock-up when no word arrives for 2^WDB destination cycles while not held (quiesce).
module chk_words #(
    parameter int WDB = 16
) (
    input  logic        clk,
    input  logic        valid,
    input  logic [15:0] w,
    input  logic        arm,
    input  logic        hold,
    output logic        e_err,
    output logic        e_ev,
    output logic        e_relock,
    output logic        e_lock
);
    logic [15:0]  prev = '0;
    logic         budget = 1'b1;
    logic [WDB-1:0] wd = '0;
    always_ff @(posedge clk) begin
        e_err <= 1'b0; e_ev <= 1'b0; e_relock <= 1'b0; e_lock <= 1'b0;
        if (valid) begin
            e_ev <= 1'b1;
            prev <= w;
            if (w != rig_pkg::prbs16_next(prev)) begin
                if (budget) begin e_relock <= 1'b1; budget <= 1'b0; end
                else e_err <= 1'b1;
            end
        end
        if (arm) budget <= 1'b1;
        if (hold || valid) wd <= '0;
        else if (&wd) begin wd <= '0; e_lock <= 1'b1; end
        else wd <= wd + 1'b1;
    end
endmodule

// Release-coherence checker (C12/M10): the 32 toggling flops must agree at every cycle. One error per release at
// most (re-armed while the reset request is seen); an event per release.
module chk_coh (
    input  logic        clk,
    input  logic [31:0] q,
    input  logic        rqs,          // the reset request, synchronised (measurement only)
    output logic        e_err,
    output logic        e_ev
);
    logic rep = 1'b0, rqp = 1'b0;
    always_ff @(posedge clk) begin
        e_err <= 1'b0;
        rqp   <= rqs;
        e_ev  <= rqp && !rqs;
        if (rqs) rep <= 1'b0;
        else if ((|q) && !(&q) && !rep) begin e_err <= 1'b1; rep <= 1'b1; end
    end
endmodule

// Pair checker (M2, M7): two copies of one signal must agree; one error per disagreement episode.
module chk_pair (
    input  logic clk,
    input  logic a,
    input  logic b,
    output logic e_err,
    output logic e_ev
);
    logic ap = 1'b0, mp = 1'b0;
    always_ff @(posedge clk) begin
        ap    <= a;
        mp    <= a ^ b;
        e_ev  <= a != ap;
        e_err <= (a ^ b) && !mp;
    end
endmodule
