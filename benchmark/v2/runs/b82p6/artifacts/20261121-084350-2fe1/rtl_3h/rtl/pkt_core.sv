// pkt_core: packet byte capture, judging order, register file R0..R7, counters, reply builder.
module pkt_core #(
    parameter logic [31:0] ID_WORD = 32'h55445031
) (
    input  logic        clk,
    input  logic        rst,
    input  logic        in_wr,
    input  logic [8:0]  in_data,
    // telemetry side
    input  logic        tlm_on_i,
    input  logic [15:0] period_i,
    input  logic [31:0] uptime_i,
    input  logic [15:0] tcount_i,
    output logic        tlm_start,
    output logic        tlm_set,
    output logic [15:0] tlm_period,
    output logic        tlm_stop,
    output logic [15:0] cmds_o,
    output logic [15:0] refused_o,
    // readback
    input  logic [6:0]  ridx,
    output logic [31:0] rword,
    output logic [7:0]  rlen,
    output logic        busy
);
    typedef enum logic [2:0] {S_IDLE, S_JUDGE, S_CRC, S_CHK, S_DEC, S_BUILD, S_TRAIL, S_DONE} st_t;
    st_t st;

    logic [7:0]  bbuf [0:15];
    logic [7:0]  rbuf [0:31];
    logic [4:0]  cnt, i;
    logic [1:0]  k;
    logic [31:0] crc, crc_n, rval;
    logic [15:0] ctr [0:6];
    logic [15:0] refused, last;
    logic        have_last;
    logic [31:0] scr [1:3];
    logic [2:0]  status;
    logic [4:0]  plen;
    logic        has_reply, pend_v;
    logic [2:0]  pend_i;

    localparam logic [31:0] CRC_INIT    = 32'hFFFFFFFF;
    localparam logic [31:0] CRC_RESIDUE = 32'hDEBB20E3;

    assign cmds_o    = ctr[0];
    assign refused_o = refused;
    assign busy      = (st != S_IDLE);

    // ---- judging: first stage (length) ----
    wire [7:0] ln0  = bbuf[1];
    wire [5:0] need = 6'd8 + {1'b0, ln0[4:0]};
    wire [5:0] cnt6 = {1'b0, cnt};

    // ---- judging: second stage (type, length, sequence, register) ----
    wire [7:0]  typ   = bbuf[0];
    wire [15:0] seq   = {bbuf[2], bbuf[3]};
    wire [15:0] r     = {bbuf[4], bbuf[5]};
    wire [15:0] dseq  = seq - last;
    wire        newok = !have_last || (dseq != 16'd0 && !dseq[15]);
    wire [31:0] wval  = {bbuf[6], bbuf[7], bbuf[8], bbuf[9]};
    wire [15:0] tp    = {bbuf[4], bbuf[5]};

    logic [2:0]  d_status;
    logic [4:0]  d_plen;
    logic        d_cnt_v, d_accept, d_wscr, d_tstart, d_tstop;
    logic [2:0]  d_cnt_i;
    logic [31:0] d_rval;
    logic        typ_ok, len_ok;
    logic [7:0]  need_len;

    always_comb begin
        typ_ok   = (typ >= 8'd1) && (typ <= 8'd5);
        need_len = (typ == 8'd1 || typ == 8'd4) ? 8'd2 : (typ == 8'd2) ? 8'd6 : 8'd0;
        len_ok   = (ln0 == need_len);
        d_status = 3'd0;
        d_plen   = 5'd0;
        d_cnt_v  = 1'b0;
        d_cnt_i  = 3'd0;
        d_accept = 1'b0;
        d_wscr   = 1'b0;
        d_tstart = 1'b0;
        d_tstop  = 1'b0;
        case (r[2:0])
            3'd0:    d_rval = ID_WORD;
            3'd1:    d_rval = scr[1];
            3'd2:    d_rval = scr[2];
            3'd3:    d_rval = scr[3];
            3'd4:    d_rval = {16'd0, ctr[0]};
            3'd5:    d_rval = {16'd0, refused};
            3'd6:    d_rval = {16'd0, period_i};
            default: d_rval = uptime_i;
        endcase
        if (!typ_ok) begin
            d_status = 3'd1;
        end else if (!len_ok) begin
            d_status = 3'd2;
        end else if (!newok) begin
            d_status = 3'd4;
        end else begin
            d_accept = 1'b1;
            case (typ)
                8'd1: begin
                    if (r >= 16'd8) d_status = 3'd3;
                    else            d_plen = 5'd4;
                end
                8'd2: begin
                    if (r >= 16'd8)                    d_status = 3'd3;
                    else if (r == 16'd0 || r >= 16'd4) d_status = 3'd5;
                    else                               d_wscr = 1'b1;
                end
                8'd3:    d_plen = 5'd17;
                8'd4:    d_tstart = 1'b1;
                default: d_tstop = 1'b1;
            endcase
        end
        if (d_status == 3'd0) begin
            d_cnt_v = 1'b1;
            d_cnt_i = 3'd0;
        end else if (d_status == 3'd4) begin
            d_cnt_v = 1'b1;
            d_cnt_i = (dseq == 16'd0) ? 3'd4 : 3'd5;
        end else begin
            d_cnt_v = 1'b1;
            d_cnt_i = 3'd6;
        end
        if (d_status != 3'd0) begin
            d_plen   = 5'd0;
            d_wscr   = 1'b0;
            d_tstart = 1'b0;
            d_tstop  = 1'b0;
        end
    end

    // ---- reply byte i ----
    logic [7:0]   pb;
    logic [4:0]   j;
    logic [135:0] pl;
    always_comb begin
        j  = i - 5'd5;
        pl = {ctr[0], ctr[1], ctr[2], ctr[3], ctr[4], ctr[5], ctr[6], tcount_i, 7'd0, tlm_on_i};
        case (i)
            5'd0:    pb = typ | 8'h80;
            5'd1:    pb = {5'd0, status};
            5'd2:    pb = bbuf[2];
            5'd3:    pb = bbuf[3];
            5'd4:    pb = {3'd0, plen};
            default: begin
                if (typ == 8'd1) begin
                    case (j[1:0])
                        2'd0:    pb = rval[31:24];
                        2'd1:    pb = rval[23:16];
                        2'd2:    pb = rval[15:8];
                        default: pb = rval[7:0];
                    endcase
                end else begin
                    pb = pl[8 * (5'd16 - j) +: 8];
                end
            end
        endcase
    end

    wire [7:0] cur_byte = (st == S_CRC) ? bbuf[i[3:0]] : pb;
    crc32_engine u_crc (.c(crc), .d(cur_byte), .n(crc_n));

    logic [7:0] crcb;
    always_comb begin
        case (k)
            2'd0:    crcb = ~crc[7:0];
            2'd1:    crcb = ~crc[15:8];
            2'd2:    crcb = ~crc[23:16];
            default: crcb = ~crc[31:24];
        endcase
    end

    wire [4:0] cnt_n = (cnt == 5'd31) ? 5'd31 : cnt + 5'd1;

    always_ff @(posedge clk) begin
        tlm_start <= 1'b0;
        tlm_set   <= 1'b0;
        tlm_stop  <= 1'b0;
        if (rst) begin
            st        <= S_IDLE;
            cnt       <= 5'd0;
            for (int n = 0; n < 7; n++) ctr[n] <= 16'd0;
            refused   <= 16'd0;
            last      <= 16'd0;
            have_last <= 1'b0;
            scr[1]    <= 32'd0;
            scr[2]    <= 32'd0;
            scr[3]    <= 32'd0;
            rlen      <= 8'd0;
            has_reply <= 1'b0;
            pend_v    <= 1'b0;
        end else begin
            case (st)
                S_IDLE: begin
                    if (in_wr) begin
                        cnt <= cnt_n;
                        if (!cnt[4]) bbuf[cnt[3:0]] <= in_data[7:0];
                        if (in_data[8]) begin
                            st   <= S_JUDGE;
                            rlen <= 8'd0;
                        end
                    end
                end
                S_JUDGE: begin
                    pend_v    <= 1'b1;
                    has_reply <= 1'b0;
                    st        <= S_DONE;
                    if (cnt >= 5'd2 && ln0 > 8'd8) begin
                        pend_i <= 3'd3;
                    end else if (cnt >= 5'd2 && cnt6 > need) begin
                        pend_i <= 3'd3;
                    end else if (cnt < 5'd4 || cnt6 < need) begin
                        pend_i <= 3'd2;
                    end else begin
                        pend_v <= 1'b0;
                        crc    <= CRC_INIT;
                        i      <= 5'd0;
                        st     <= S_CRC;
                    end
                end
                S_CRC: begin
                    crc <= crc_n;
                    i   <= i + 5'd1;
                    if (i == cnt - 5'd1) st <= S_CHK;
                end
                S_CHK: begin
                    if (crc == CRC_RESIDUE) begin
                        st <= S_DEC;
                    end else begin
                        pend_v    <= 1'b1;
                        pend_i    <= 3'd1;
                        has_reply <= 1'b0;
                        st        <= S_DONE;
                    end
                end
                S_DEC: begin
                    status    <= d_status;
                    plen      <= d_plen;
                    pend_v    <= d_cnt_v;
                    pend_i    <= d_cnt_i;
                    has_reply <= 1'b1;
                    rval      <= d_rval;
                    if (d_accept) begin
                        last      <= seq;
                        have_last <= 1'b1;
                    end
                    if (d_wscr) scr[r[1:0]] <= wval;
                    tlm_start  <= d_tstart;
                    tlm_set    <= d_tstart && (tp != 16'd0);
                    tlm_period <= (tp < 16'd4) ? 16'd4 : tp;
                    tlm_stop   <= d_tstop;
                    crc        <= CRC_INIT;
                    i          <= 5'd0;
                    st         <= S_BUILD;
                end
                S_BUILD: begin
                    rbuf[i] <= pb;
                    crc     <= crc_n;
                    i       <= i + 5'd1;
                    k       <= 2'd0;
                    if (i == plen + 5'd4) st <= S_TRAIL;
                end
                S_TRAIL: begin
                    rbuf[i] <= crcb;
                    i       <= i + 5'd1;
                    k       <= k + 2'd1;
                    if (k == 2'd3) st <= S_DONE;
                end
                default: begin  // S_DONE
                    if (pend_v) begin
                        ctr[pend_i] <= ctr[pend_i] + 16'd1;
                        if (pend_i != 3'd0) refused <= refused + 16'd1;
                    end
                    rlen <= has_reply ? ({3'd0, plen} + 8'd9) : 8'd0;
                    cnt  <= 5'd0;
                    st   <= S_IDLE;
                end
            endcase
        end
    end

    // ---- reply readback (always_comb so every simulator re-evaluates on rbuf changes) ----
    wire [8:0] rbase = {ridx, 2'b00};
    logic [7:0] rb [0:3];
    logic [8:0] rj;
    always_comb begin
        for (int n = 0; n < 4; n++) begin
            rj = rbase + 9'(n);
            if (rj < {1'b0, rlen} && rj < 9'd32) rb[n] = rbuf[rj[4:0]];
            else                                 rb[n] = 8'h00;
        end
    end
    assign rword = {rb[0], rb[1], rb[2], rb[3]};
endmodule
