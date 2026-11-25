// cdc_inj_pkg.sv: the synchroniser-delay injection (brief 16). Simulation only; not synthesisable.
//
// hold(key, changing) is asked by every first-stage synchroniser flop that flow/cdc_inject.py rewrote, and by the
// first stage of every XPM stand-in in xpm_cdc_models.sv, once per destination clock edge. It answers "keep the old
// value this edge", which is one extra destination cycle of latency on that flop. Per flop (key), a hold is asked for
// only when the flop's input differs from its output, a hold is chosen with probability 1/2, and a flop never holds
// two edges in a row, so the extra delay is exactly 0 or 1 destination cycle per change.
// Skew (brief 189, idea from Edwards 2026, ch 12): +CDC_INJ_SKEW=<k> (default 1, the behaviour above) lets a flop hold up to k edges
// in a row before it must take the new value, so the bits of one bus can arrive up to k destination cycles apart (a per-bit skew,
// each bit's delay drawn on its own). With k = 1 the random stream and results are unchanged.
// Seed: plusarg +CDC_INJ_SEED=<n>. Without the plusarg hold() is always 0 and the design behaves as in a plain
// simulation (the XPM stand-ins then equal the documented macro behaviour with the default latency).
// A cycle-level model: it needs no timing information (written for Icarus and Verilator; only Icarus has been run).
package cdc_inj_pkg;
    bit          inited = 1'b0;
    bit          on     = 1'b0;
    int unsigned rng    = 32'h2545F491;
    int          seed_v = 0;
    byte         held [0:65535];
    int          skew_v = 1;
    int unsigned n_hold = 0;

    function automatic bit hold(int unsigned key, bit changing);
        if (!inited) begin
            inited = 1'b1;
            on = $value$plusargs("CDC_INJ_SEED=%d", seed_v);
            if ($value$plusargs("CDC_INJ_SKEW=%d", skew_v)) begin if (skew_v < 1) skew_v = 1; if (skew_v > 100) skew_v = 100; end
            rng = 32'h2545F491 ^ (32'(seed_v) * 32'h9E3779B1);
            if (rng == 0) rng = 32'h1;
        end
        if (!on) return 1'b0;
        if (!changing) begin held[key[15:0]] = 8'd0; return 1'b0; end
        if (int'(held[key[15:0]]) >= skew_v) begin held[key[15:0]] = 8'd0; return 1'b0; end
        rng ^= rng << 13; rng ^= rng >> 17; rng ^= rng << 5;
        if (rng[7]) begin held[key[15:0]] = held[key[15:0]] + 8'd1; n_hold++; return 1'b1; end
        held[key[15:0]] = 8'd0;
        return 1'b0;
    endfunction
endpackage
