// formal_mac_rx.sv: the receive frame FSM of rtl/mac_rx.sv (brief 58A step 0). The byte stream is free (any bytes,
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
    always_ff @(posedge clk) if (f_past && !rst) begin
        // bytes leave in order, numbered from 0, only inside a frame, and each one is the byte that came in
        if (out_valid) begin
            assert (f_in);
            assert (out_idx == f_cnt);
            assert (out_sof == (f_cnt == 11'd0));
            assert ($past(in_valid) && !$past(in_eof) && out_data == $past(in_data));
        end
        // the verdict: length counted right; good only when long enough, short enough, no RX_ER and the FCS right
        if (end_valid) begin
            assert (f_in);
            assert (end_len == f_cnt);
            assert (end_runt == (f_cnt < 11'(MINF)));
            assert (end_giant == (f_cnt > 11'(MAXF)));
            if (end_good) assert (!end_fcs_err && !end_runt && !end_giant && !end_er);
            assert ($past(in_valid) && $past(in_eof));
        end
        assert (!(sof_pulse && out_valid));
    end
    always_ff @(posedge clk) if (f_past && !rst) begin
        cover (end_valid && end_runt);
        cover (end_valid && end_giant);
        cover (end_valid && end_er);
        cover (ev_bad_pre);
    end
endmodule
