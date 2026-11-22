// udp_core.sv: packet framer, judging, command execution and reply builder.
// Bytes arrive from the window IN register. A rolling CRC-32 runs over every byte, trailer included:
// a good packet leaves the register at the residue 0xDEBB20E3. When the end-flag byte arrives the
// packet is judged in one cycle (S_JUDGE) and the reply (header, payload, CRC-32) is built into the
// reply memory one byte per clock (S_BUILD), about 30 clocks in all. IN bytes are ignored while busy.
module udp_core #(
    parameter logic [31:0] ID_WORD = 32'h55445031
) (
    input  logic        clk,
    input  logic        rst,
    // window
    input  logic        in_wr,
    input  logic [8:0]  in_data,
    input  logic [6:0]  ridx,
    output logic [31:0] rword,
    output logic [7:0]  rlen,
    output logic        busy,
    // telemetry
    input  logic        tel_on,
    input  logic [15:0] period,
    input  logic [31:0] uptime,
    input  logic [15:0] fcount,
    output logic        cmd_start,
    output logic [15:0] cmd_period,
    output logic        cmd_stop,
    output logic [15:0] done_cnt,
    output logic [15:0] refused_cnt
);
    localparam logic [31:0] CRC_RESIDUE = 32'hDEBB20E3;
    localparam logic [1:0]  K_NONE = 2'd0, K_READ = 2'd1, K_STATUS = 2'd2;

    typedef enum logic [1:0] {S_IDLE, S_JUDGE, S_BUILD} state_t;
    state_t state;

    logic [7:0]  pbuf [16];
    logic [7:0]  n;
    logic [31:0] rcrc, rcrc_nxt;
    logic [31:0] wreg1, wreg2, wreg3;
    logic [15:0] cnt_bad, cnt_short, cnt_long, cnt_rep, cnt_ooo, cnt_tle;
    logic        seq_valid;
    logic [15:0] last_seq;

    // reply under construction
    logic [7:0]  r_typ, r_st;
    logic [15:0] r_seq;
    logic [1:0]  r_kind;
    logic [31:0] r_val;
    logic        done_pend;
    logic [4:0]  bk;
    logic [31:0] bcrc, bcrc_nxt;
    logic [7:0]  bbyte;
    logic [7:0]  rmem [4][8];

    assign busy = (state != S_IDLE);

    // ------------------------------------------------------------ judging (combinational)
    wire [7:0]  typ  = pbuf[0];
    wire [7:0]  ln   = pbuf[1];
    wire [15:0] seq  = {pbuf[2], pbuf[3]};
    wire [15:0] rnum = {pbuf[4], pbuf[5]};
    wire [8:0]  n9   = {1'b0, n};
    wire [8:0]  full_len = 9'd8 + {1'b0, ln};

    logic        drop_short, drop_long, drop_bad, dropped;
    logic        type_ok, len_ok, seq_ok, seq_pass, reg_big, wr_ro;
    logic [7:0]  want;
    logic [15:0] diff;
    logic [2:0]  st;
    logic [31:0] rdval;

    always_comb begin
        drop_short = 1'b0;
        drop_long  = 1'b0;
        drop_bad   = 1'b0;
        if (n < 8'd4)                            drop_short = 1'b1;
        else if (ln > 8'd8 || n9 > full_len)     drop_long  = 1'b1;
        else if (n9 < full_len)                  drop_short = 1'b1;
        else if (rcrc != CRC_RESIDUE)            drop_bad   = 1'b1;
        dropped = drop_short | drop_long | drop_bad;

        type_ok = (typ != 8'd0) && (typ <= 8'd5);
        case (typ)
            8'd1:    want = 8'd2;
            8'd2:    want = 8'd6;
            8'd4:    want = 8'd2;
            default: want = 8'd0;
        endcase
        len_ok   = (ln == want);
        diff     = seq - last_seq;
        seq_ok   = !seq_valid || (diff != 16'd0 && !diff[15]);
        seq_pass = type_ok && len_ok && seq_ok;
        reg_big  = |rnum[15:3];
        wr_ro    = rnum[2] || (rnum[1:0] == 2'd0);

        if (!type_ok)                                    st = 3'd1;
        else if (!len_ok)                                st = 3'd2;
        else if (!seq_ok)                                st = 3'd4;
        else if ((typ == 8'd1 || typ == 8'd2) && reg_big) st = 3'd3;
        else if (typ == 8'd2 && wr_ro)                   st = 3'd5;
        else                                             st = 3'd0;

        case (rnum[2:0])
            3'd0:    rdval = ID_WORD;
            3'd1:    rdval = wreg1;
            3'd2:    rdval = wreg2;
            3'd3:    rdval = wreg3;
            3'd4:    rdval = {16'h0, refused_cnt};
            3'd5:    rdval = {16'h0, done_cnt};
            3'd6:    rdval = {16'h0, period};
            default: rdval = uptime;
        endcase
    end

    wire exec_ok = (state == S_JUDGE) && !dropped && (st == 3'd0);
    assign cmd_start  = exec_ok && (typ == 8'd4);
    assign cmd_period = rnum;
    assign cmd_stop   = exec_ok && (typ == 8'd5);

    // ------------------------------------------------------------ reply byte source
    wire [4:0] plen    = (r_kind == K_READ) ? 5'd4 : (r_kind == K_STATUS) ? 5'd17 : 5'd0;
    wire [5:0] hdrpay  = 6'd5 + {1'b0, plen};
    wire [5:0] total   = hdrpay + 6'd4;
    wire [4:0] pj      = bk - 5'd5;
    logic [7:0] pay_byte;

    always_comb begin
        pay_byte = 8'h00;
        if (r_kind == K_READ) begin
            case (pj[1:0])
                2'd0:    pay_byte = r_val[31:24];
                2'd1:    pay_byte = r_val[23:16];
                2'd2:    pay_byte = r_val[15:8];
                default: pay_byte = r_val[7:0];
            endcase
        end else begin
            case (pj)
                5'd0:  pay_byte = done_cnt[15:8];
                5'd1:  pay_byte = done_cnt[7:0];
                5'd2:  pay_byte = cnt_bad[15:8];
                5'd3:  pay_byte = cnt_bad[7:0];
                5'd4:  pay_byte = cnt_short[15:8];
                5'd5:  pay_byte = cnt_short[7:0];
                5'd6:  pay_byte = cnt_long[15:8];
                5'd7:  pay_byte = cnt_long[7:0];
                5'd8:  pay_byte = cnt_rep[15:8];
                5'd9:  pay_byte = cnt_rep[7:0];
                5'd10: pay_byte = cnt_ooo[15:8];
                5'd11: pay_byte = cnt_ooo[7:0];
                5'd12: pay_byte = cnt_tle[15:8];
                5'd13: pay_byte = cnt_tle[7:0];
                5'd14: pay_byte = fcount[15:8];
                5'd15: pay_byte = fcount[7:0];
                5'd16: pay_byte = {7'h00, tel_on};
                default: pay_byte = 8'h00;
            endcase
        end

        if (bk == 5'd0)                bbyte = r_typ;
        else if (bk == 5'd1)           bbyte = r_st;
        else if (bk == 5'd2)           bbyte = r_seq[15:8];
        else if (bk == 5'd3)           bbyte = r_seq[7:0];
        else if (bk == 5'd4)           bbyte = {3'b000, plen};
        else if ({1'b0, bk} < hdrpay)  bbyte = pay_byte;
        else                           bbyte = ~bcrc[7:0];
    end

    crc32_byte u_rx_crc (.crc_in(rcrc), .data(in_data[7:0]), .crc_out(rcrc_nxt));
    crc32_byte u_tx_crc (.crc_in(bcrc), .data(bbyte),        .crc_out(bcrc_nxt));

    // ------------------------------------------------------------ sequential
    always_ff @(posedge clk) begin
        if (rst) begin
            state       <= S_IDLE;
            n           <= 8'd0;
            rcrc        <= 32'hFFFFFFFF;
            wreg1       <= 32'd0;
            wreg2       <= 32'd0;
            wreg3       <= 32'd0;
            cnt_bad     <= 16'd0;
            cnt_short   <= 16'd0;
            cnt_long    <= 16'd0;
            cnt_rep     <= 16'd0;
            cnt_ooo     <= 16'd0;
            cnt_tle     <= 16'd0;
            done_cnt    <= 16'd0;
            refused_cnt <= 16'd0;
            seq_valid   <= 1'b0;
            rlen        <= 8'd0;
            done_pend   <= 1'b0;
            bk          <= 5'd0;
        end else begin
            case (state)
                S_IDLE: begin
                    if (in_wr) begin
                        if (n < 8'd16) pbuf[n[3:0]] <= in_data[7:0];
                        if (n != 8'hFF) n <= n + 8'd1;
                        rcrc <= rcrc_nxt;
                        if (in_data[8]) state <= S_JUDGE;
                    end
                end

                S_JUDGE: begin
                    n    <= 8'd0;
                    rcrc <= 32'hFFFFFFFF;
                    rlen <= 8'd0;
                    if (drop_short) cnt_short <= cnt_short + 16'd1;
                    if (drop_long)  cnt_long  <= cnt_long  + 16'd1;
                    if (drop_bad)   cnt_bad   <= cnt_bad   + 16'd1;
                    if (dropped || st != 3'd0) refused_cnt <= refused_cnt + 16'd1;
                    if (dropped) begin
                        state <= S_IDLE;
                    end else begin
                        if (st == 3'd4) begin
                            if (diff == 16'd0) cnt_rep <= cnt_rep + 16'd1;
                            else               cnt_ooo <= cnt_ooo + 16'd1;
                        end else if (st != 3'd0) begin
                            cnt_tle <= cnt_tle + 16'd1;
                        end
                        if (seq_pass) begin
                            last_seq  <= seq;
                            seq_valid <= 1'b1;
                        end
                        if (st == 3'd0 && typ == 8'd2) begin
                            case (rnum[1:0])
                                2'd1:    wreg1 <= {pbuf[6], pbuf[7], pbuf[8], pbuf[9]};
                                2'd2:    wreg2 <= {pbuf[6], pbuf[7], pbuf[8], pbuf[9]};
                                default: wreg3 <= {pbuf[6], pbuf[7], pbuf[8], pbuf[9]};
                            endcase
                        end
                        r_typ     <= typ | 8'h80;
                        r_st      <= {5'b0, st};
                        r_seq     <= seq;
                        r_val     <= rdval;
                        r_kind    <= (st == 3'd0 && typ == 8'd1) ? K_READ :
                                     (st == 3'd0 && typ == 8'd3) ? K_STATUS : K_NONE;
                        done_pend <= (st == 3'd0);
                        bk        <= 5'd0;
                        bcrc      <= 32'hFFFFFFFF;
                        state     <= S_BUILD;
                    end
                end

                S_BUILD: begin
                    rmem[bk[1:0]][bk[4:2]] <= bbyte;
                    bcrc <= ({1'b0, bk} < hdrpay) ? bcrc_nxt : {8'h00, bcrc[31:8]};
                    bk   <= bk + 5'd1;
                    if ({1'b0, bk} == total - 6'd1) begin
                        state <= S_IDLE;
                        rlen  <= {2'b00, total};
                        if (done_pend) done_cnt <= done_cnt + 16'd1;
                    end
                end

                default: state <= S_IDLE;
            endcase
        end
    end

    // ------------------------------------------------------------ word readout
    always_comb begin
        logic [7:0] m [4];
        logic [8:0] bi;
        for (int l = 0; l < 4; l++) begin
            bi   = {ridx, 2'b00} + 9'(l);
            m[l] = (bi < {1'b0, rlen}) ? rmem[l][ridx[2:0]] : 8'h00;
        end
        rword = {m[0], m[1], m[2], m[3]};
    end
endmodule
