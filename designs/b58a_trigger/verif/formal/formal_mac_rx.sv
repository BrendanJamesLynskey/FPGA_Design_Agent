// formal_mac_rx.sv: the receive frame FSM of rtl/mac_rx.sv. The byte stream is free (any bytes,
// errors, end tokens and gaps); MIN_FRAME 5 and MAX_FRAME 8 keep it shallow.
module formal_mac_rx (
    input logic       clk,
    input logic       in_valid, in_eof, in_er,
    input logic [7:0] in_data
);
    localparam int MINF = 5, MAXF = 8;
    logic rst;
    logic f_past = 1'b0;
    logic [2:0] f_n = 3'd0;
    always_ff @(posedge clk) begin f_past <= 1'b1; if (f_n != 3'd7) f_n <= f_n + 3'd1; end
    assign rst = (f_n == 3'd0);

    logic sof_pulse, out_valid, out_sof, end_valid, end_good, end_fcs_err, end_runt, end_giant, end_er, ev_bad_pre;
    logic [7:0] out_data;
    logic [10:0] out_idx, end_len;
    mac_rx #(.MIN_FRAME(MINF), .MAX_FRAME(MAXF)) dut (.clk, .rst, .in_valid, .in_eof, .in_er, .in_data, .sof_pulse,
        .out_valid, .out_sof, .out_data, .out_idx, .end_valid, .end_good, .end_fcs_err, .end_runt, .end_giant,
        .end_er, .end_len, .ev_bad_pre);

    logic        f_in;                  // between an SFD and its end token
    logic [10:0] f_cnt;                 // bytes put out in this frame
    logic        f_er;
    always_ff @(posedge clk) begin
        if (rst) begin f_in <= 1'b0; f_cnt <= '0; f_er <= 1'b0; end
        else begin
            if (sof_pulse) begin f_in <= 1'b1; f_cnt <= '0; f_er <= 1'b0; end
            if (out_valid) f_cnt <= f_cnt + 11'd1;
            if (end_valid) f_in <= 1'b0;
        end
    end
    // Every assertion is labelled (a_*) and paired with a cover of its own antecedent (a_*__ante, below; brief 143c).
    always_ff @(posedge clk) if (f_past && !rst) begin
        // bytes leave in order, numbered from 0, only inside a frame, and each one is the byte that came in
        if (out_valid) begin
            a_out_in_frame: assert (f_in);
            a_out_index: assert (out_idx == f_cnt);
            a_out_sof: assert (out_sof == (f_cnt == 11'd0));
            a_out_is_input: assert ($past(in_valid) && !$past(in_eof) && out_data == $past(in_data));
        end
        // the verdict: length counted right; good only when long enough, short enough, no RX_ER and the FCS right
        if (end_valid) begin
            a_end_in_frame: assert (f_in);
            a_end_len: assert (end_len == f_cnt);
            a_end_runt: assert (end_runt == (f_cnt < 11'(MINF)));
            a_end_giant: assert (end_giant == (f_cnt > 11'(MAXF)));
            if (end_good) a_end_good_clean: assert (!end_fcs_err && !end_runt && !end_giant && !end_er);
            a_end_from_eof: assert ($past(in_valid) && $past(in_eof));
        end
        a_sof_no_data: assert (!(sof_pulse && out_valid));
    end
    // antecedents (same guard): a byte leaves, a frame ends, a good frame ends, a start pulse comes
    always_ff @(posedge clk) if (f_past && !rst) begin
        a_out__ante: cover (out_valid && f_cnt != 11'd0);        // all a_out_*: not only the first byte
        a_end__ante: cover (end_valid);                          // all a_end_* except a_end_good_clean
        a_end_good_clean__ante: cover (end_valid && end_good);
        a_sof_no_data__ante: cover (sof_pulse);
    end
    always_ff @(posedge clk) if (f_past && !rst) begin
        c_runt: cover (end_valid && end_runt);
        c_giant: cover (end_valid && end_giant);
        c_er: cover (end_valid && end_er);
        c_bad_pre: cover (ev_bad_pre);
        c_good_frame: cover (end_valid && end_good);
    end
endmodule
