// formal_mac_tx.sv: the transmit frame FSM of rtl/mac_tx.sv. Small parameters (MIN_DATA 4,
// IFG 3) keep the proof shallow; the structure does not depend on them. Every input is free.
module formal_mac_tx (
    input logic        clk,
    input logic        start,
    input logic [10:0] len,
    input logic [7:0]  in_data,
    input logic        poison,
    input logic        ce
);
    localparam int MIN_DATA = 4, IFG = 3;
    logic rst;
    logic f_past = 1'b0;
    logic [2:0] f_n = 3'd0;
    always_ff @(posedge clk) begin f_past <= 1'b1; if (f_n != 3'd7) f_n <= f_n + 3'd1; end
    assign rst = (f_n == 3'd0);
    always_comb assume (len >= 11'd1 && len <= 11'd6);

    logic ready, req_valid, first_pulse, sof_pulse, last_pulse, last_poisoned, busy, tx_en;
    logic [10:0] req_idx;
    logic [7:0]  txd;
    // a registered index provider (like order_ctl): in_last marks byte L-1 of the frame being sent
    logic [10:0] L, ridx;
    logic        in_last;
    always_ff @(posedge clk) begin
        if (start && ready && ce) L <= len;
        ridx <= req_idx;
    end
    assign in_last = (ridx + 11'd1 == L);
    always_comb assume (ce);                            // 1000 Mb/s: a byte every clock (the frame structure is the same)
    mac_tx #(.MIN_DATA(MIN_DATA), .IFG_BYTES(IFG)) dut (.clk, .rst, .ce, .start, .ready, .req_idx, .req_valid,
        .in_data, .in_last, .poison, .txd, .tx_en, .first_pulse, .sof_pulse, .last_pulse, .last_poisoned, .busy);

    logic [10:0] f_len, f_k, f_gap;
    logic        f_seen;                // a frame has ended (the gap counter is meaningful)
    always_ff @(posedge clk) begin
        if (rst) begin f_len <= '0; f_k <= '0; f_gap <= '0; f_seen <= 1'b0; end
        else begin
            if (start && ready) f_len <= (len < 11'(MIN_DATA)) ? 11'(MIN_DATA) : len;
            if (tx_en) f_k <= f_k + 11'd1;
            else f_k <= '0;
            if (tx_en) f_gap <= '0;
            else if (f_gap != 11'h7FF) f_gap <= f_gap + 11'd1;
            if (!tx_en && f_k != 0) f_seen <= 1'b1;
        end
    end
    // Every assertion is labelled (a_*) and paired with a cover of its own antecedent (a_*__ante, below; brief 143c).
    always_ff @(posedge clk) if (f_past && !rst) begin
        if (tx_en && f_k < 11'd7)  a_preamble: assert (txd == 8'h55);
        if (tx_en && f_k == 11'd7) a_sfd: assert (txd == 8'hD5);
        if (tx_en && f_k == 11'd0) a_first_pulse: assert (first_pulse);
        if (first_pulse) a_first_only: assert (tx_en && f_k == 11'd0);
        if (sof_pulse)   a_sof_only: assert (tx_en && f_k == 11'd7);
        // a frame ends after preamble, SFD, the padded data and the FCS, exactly when the last byte was flagged
        if (!tx_en && f_k != 0) begin
            a_frame_len: assert (f_k == 11'd8 + f_len + 11'd4);
            a_frame_end_after_last: assert ($past(last_pulse));
        end
        if (last_pulse) a_last_position: assert (tx_en && f_k == 11'd8 + f_len + 11'd3);
        // the gap before the next frame is at least IFG idle clocks
        if (tx_en && f_k == 11'd0 && f_seen) a_ifg: assert (f_gap >= 11'(IFG));
        // the data provider is only asked for real data bytes
        if (req_valid) a_req_in_range: assert (req_idx < f_len);
    end
    // antecedents (same guard): the condition of each `if`
    always_ff @(posedge clk) if (f_past && !rst) begin
        a_preamble__ante: cover (tx_en && f_k < 11'd7);
        a_sfd__ante: cover (tx_en && f_k == 11'd7);
        a_first_pulse__ante: cover (tx_en && f_k == 11'd0);
        a_first_only__ante: cover (first_pulse);
        a_sof_only__ante: cover (sof_pulse);
        a_frame_end__ante: cover (!tx_en && f_k != 0);
        a_last_position__ante: cover (last_pulse);
        a_ifg__ante: cover (tx_en && f_k == 11'd0 && f_seen);
        a_req_in_range__ante: cover (req_valid);
    end
    always_ff @(posedge clk) if (f_past && !rst) begin
        c_poisoned: cover (last_pulse && last_poisoned);
        c_ifg_exact: cover (tx_en && f_k == 11'd0 && f_seen && f_gap == 11'(IFG) + 11'd1);
    end
endmodule
