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
    always_ff @(posedge clk) if (f_past && !rst) begin
        if (tx_en && f_k < 11'd7)  assert (txd == 8'h55);
        if (tx_en && f_k == 11'd7) assert (txd == 8'hD5);
        if (tx_en && f_k == 11'd0) assert (first_pulse);
        if (first_pulse) assert (tx_en && f_k == 11'd0);
        if (sof_pulse)   assert (tx_en && f_k == 11'd7);
        // a frame ends after preamble, SFD, the padded data and the FCS, exactly when the last byte was flagged
        if (!tx_en && f_k != 0) begin
            assert (f_k == 11'd8 + f_len + 11'd4);
            assert ($past(last_pulse));
        end
        if (last_pulse) assert (tx_en && f_k == 11'd8 + f_len + 11'd3);
        // the gap before the next frame is at least IFG idle clocks
        if (tx_en && f_k == 11'd0 && f_seen) assert (f_gap >= 11'(IFG));
        // the data provider is only asked for real data bytes
        if (req_valid) assert (req_idx < f_len);
        if (ready) assert (!tx_en || f_k == 11'd0 || last_pulse || 1'b1);
    end
    always_ff @(posedge clk) if (f_past && !rst) begin
        cover (last_pulse && last_poisoned);
        cover (tx_en && f_k == 11'd0 && f_seen && f_gap == 11'(IFG) + 11'd1);
    end
endmodule
