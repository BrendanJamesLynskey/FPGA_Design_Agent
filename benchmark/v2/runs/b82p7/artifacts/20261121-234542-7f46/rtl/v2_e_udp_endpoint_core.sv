// Command engine: packet receive (byte stream through the IN register), CRC-32
// check, refusal-order judgement, sequence rule, registers, counters, reply
// building, tick generator and the shell window registers.
module v2_e_udp_endpoint_core (
    input  logic        clk,
    input  logic        rst,          // synchronous, active high
    input  logic [6:0]  win_addr,
    input  logic        win_wr,
    input  logic        win_rd,
    input  logic [31:0] win_wdata,
    output logic [31:0] win_rdata,
    output logic [15:0] led
);
    localparam logic [31:0] ID_WORD = 32'h55445031;
    localparam logic [31:0] RESIDUE = 32'hDEBB20E3;

    typedef enum logic [1:0] {ST_IDLE, ST_JUDGE, ST_BUILD, ST_APPLY} state_t;
    state_t st;

    // ---------------- receive ----------------
    logic [4:0]  n;
    logic [7:0]  h_type, h_len, h_seqh, h_seql;
    logic [7:0]  pl [0:7];
    logic [31:0] crc, crc_nx;
    logic [7:0]  crc_data, ob;

    logic in_wr, tick_wr, ridx_wr, tidx_wr, take_wr;
    assign in_wr   = win_wr && (win_addr == 7'd0) && (st == ST_IDLE);
    assign tick_wr = win_wr && (win_addr == 7'd1);
    assign ridx_wr = win_wr && (win_addr == 7'd3);
    assign tidx_wr = win_wr && (win_addr == 7'd6);
    assign take_wr = win_wr && (win_addr == 7'd8);

    v2_e_udp_endpoint_crc32_byte u_crc (.crc_in(crc), .data(crc_data), .crc_out(crc_nx));
    assign crc_data = (st == ST_BUILD) ? ob : win_wdata[7:0];

    // ---------------- state ----------------
    logic [15:0] cmds, refused, c_bad, c_short, c_long, c_rep, c_ooo, c_err;
    logic [31:0] scr1, scr2, scr3;
    logic        have_last;
    logic [15:0] last;
    logic [4:0]  rlen;
    logic [6:0]  ridx, tidx;
    logic [7:0]  rbuf [0:31];

    // decision registers (set in JUDGE, used in BUILD / APPLY)
    logic [2:0]  d_status, d_cnt;
    logic        d_reply, d_seqpass, d_ok;
    logic [4:0]  plen;
    logic [4:0]  bi;

    // telemetry
    logic        tel_on, tel_held, tick, start_en, stop_en;
    logic [15:0] tel_period, fcount;
    logic [31:0] uptime, tword;
    logic [4:0]  tlen;
    logic [11:0] pending;

    assign tick = (pending != 12'd0);
    always_ff @(posedge clk) begin
        if (rst) pending <= 12'd0;
        else pending <= pending - {11'd0, tick} + (tick_wr ? {4'd0, win_wdata[7:0]} : 12'd0);
    end

    assign start_en = (st == ST_APPLY) && d_ok && (h_type == 8'd4);
    assign stop_en  = (st == ST_APPLY) && d_ok && (h_type == 8'd5);

    v2_e_udp_endpoint_telemetry u_tel (
        .clk(clk), .rst(rst), .tick(tick), .cmds(cmds), .refused(refused),
        .start_en(start_en), .start_per({pl[0], pl[1]}), .stop_en(stop_en), .take(take_wr),
        .tidx(tidx), .on(tel_on), .held(tel_held), .period(tel_period), .uptime(uptime),
        .fcount(fcount), .tlen(tlen), .tword(tword));

    assign led = cmds;

    // ---------------- judgement (combinational on the packet registers) ----------------
    logic [15:0] j_seq, j_reg, j_diff;
    logic        j_long, j_short, j_bad, j_known, j_lenbad, j_seqok, j_regbad, j_roreg;
    logic [5:0]  j_need;
    logic [2:0]  j_status, j_cnt;
    logic        j_reply, j_seqpass, j_ok;
    logic [4:0]  j_plen;
    logic [7:0]  j_exp;

    always_comb begin
        j_seq    = {h_seqh, h_seql};
        j_reg    = {pl[0], pl[1]};
        j_diff   = j_seq - last;
        j_need   = 6'd8 + h_len[5:0];
        j_long   = (n >= 5'd2) && ((h_len > 8'd8) || ({1'b0, n} > j_need));
        j_short  = (n < 5'd4) || ({1'b0, n} < j_need);
        j_bad    = (crc != RESIDUE);
        j_known  = (h_type >= 8'd1) && (h_type <= 8'd5);
        case (h_type)
            8'd1, 8'd4: j_exp = 8'd2;
            8'd2:       j_exp = 8'd6;
            default:    j_exp = 8'd0;
        endcase
        j_lenbad = (h_len != j_exp);
        j_seqok  = !have_last || ((j_diff != 16'd0) && !j_diff[15]);
        j_regbad = (j_reg >= 16'd8);
        j_roreg  = (j_reg == 16'd0) || (j_reg >= 16'd4);

        j_status  = 3'd0;
        j_cnt     = 3'd0;
        j_reply   = 1'b1;
        j_seqpass = 1'b0;
        j_ok      = 1'b0;
        if (j_long) begin
            j_reply = 1'b0; j_cnt = 3'd3;
        end else if (j_short) begin
            j_reply = 1'b0; j_cnt = 3'd2;
        end else if (j_bad) begin
            j_reply = 1'b0; j_cnt = 3'd1;
        end else if (!j_known) begin
            j_status = 3'd1; j_cnt = 3'd6;
        end else if (j_lenbad) begin
            j_status = 3'd2; j_cnt = 3'd6;
        end else if (!j_seqok) begin
            j_status = 3'd4; j_cnt = (j_diff == 16'd0) ? 3'd4 : 3'd5;
        end else begin
            j_seqpass = 1'b1;
            if ((h_type == 8'd1 || h_type == 8'd2) && j_regbad) begin
                j_status = 3'd3; j_cnt = 3'd6;
            end else if (h_type == 8'd2 && j_roreg) begin
                j_status = 3'd5; j_cnt = 3'd6;
            end else begin
                j_ok = 1'b1;
            end
        end
        j_plen = 5'd0;
        if (j_ok && h_type == 8'd1) j_plen = 5'd4;
        if (j_ok && h_type == 8'd3) j_plen = 5'd17;
    end

    // ---------------- reply byte source ----------------
    logic [31:0]  regv, cw, regs_sh;
    logic [135:0] sv, svs;
    logic [4:0]   pidx;
    logic [7:0]   pbyte, svsh;
    logic [5:0]   pend;
    logic [1:0]   cidx;

    always_comb begin
        case (pl[1][2:0])
            3'd0:    regv = ID_WORD;
            3'd1:    regv = scr1;
            3'd2:    regv = scr2;
            3'd3:    regv = scr3;
            3'd4:    regv = {16'd0, cmds};
            3'd5:    regv = {16'd0, refused};
            3'd6:    regv = {16'd0, tel_period};
            default: regv = uptime;
        endcase
        sv      = {cmds, c_bad, c_short, c_long, c_rep, c_ooo, c_err, fcount, 7'd0, tel_on};
        pidx    = bi - 5'd5;
        svsh    = {5'd16 - pidx, 3'b000};
        svs     = sv >> svsh;
        regs_sh = regv >> {3'd0, ~pidx[1:0], 3'b000};
        if (h_type == 8'd1) pbyte = regs_sh[7:0];
        else                pbyte = svs[7:0];
        pend    = 6'd5 + {1'b0, plen};
        cidx    = bi[1:0] - pend[1:0];
        cw      = ~crc >> {27'd0, cidx, 3'b000};
        case (bi)
            5'd0:    ob = h_type | 8'h80;
            5'd1:    ob = {5'd0, d_status};
            5'd2:    ob = h_seqh;
            5'd3:    ob = h_seql;
            5'd4:    ob = {3'd0, plen};
            default: ob = ({1'b0, bi} < pend) ? pbyte : cw[7:0];
        endcase
    end

    // ---------------- control ----------------
    always_ff @(posedge clk) begin
        if (rst) begin
            st        <= ST_IDLE;
            n         <= 5'd0;
            crc       <= 32'hFFFFFFFF;
            cmds      <= 16'd0;
            refused   <= 16'd0;
            c_bad     <= 16'd0;
            c_short   <= 16'd0;
            c_long    <= 16'd0;
            c_rep     <= 16'd0;
            c_ooo     <= 16'd0;
            c_err     <= 16'd0;
            scr1      <= 32'd0;
            scr2      <= 32'd0;
            scr3      <= 32'd0;
            have_last <= 1'b0;
            last      <= 16'd0;
            rlen      <= 5'd0;
            ridx      <= 7'd0;
            tidx      <= 7'd0;
            d_status  <= 3'd0;
            d_cnt     <= 3'd0;
            d_reply   <= 1'b0;
            d_seqpass <= 1'b0;
            d_ok      <= 1'b0;
            plen      <= 5'd0;
            bi        <= 5'd0;
        end else begin
            if (ridx_wr) ridx <= win_wdata[6:0];
            if (tidx_wr) tidx <= win_wdata[6:0];
            case (st)
                ST_IDLE: begin
                    if (in_wr) begin
                        crc <= crc_nx;
                        if (n != 5'd31) n <= n + 5'd1;
                        if (win_wdata[8]) begin
                            st   <= ST_JUDGE;
                            rlen <= 5'd0;
                        end
                    end
                end
                ST_JUDGE: begin
                    d_status  <= j_status;
                    d_cnt     <= j_cnt;
                    d_reply   <= j_reply;
                    d_seqpass <= j_seqpass;
                    d_ok      <= j_ok;
                    plen      <= j_plen;
                    bi        <= 5'd0;
                    crc       <= 32'hFFFFFFFF;
                    st        <= j_reply ? ST_BUILD : ST_APPLY;
                end
                ST_BUILD: begin
                    if ({1'b0, bi} < pend) crc <= crc_nx;
                    if ({1'b0, bi} == pend + 6'd3) begin
                        rlen <= 5'd9 + plen;
                        st   <= ST_APPLY;
                    end else begin
                        bi <= bi + 5'd1;
                    end
                end
                ST_APPLY: begin
                    if (d_ok) cmds <= cmds + 16'd1;
                    else begin
                        refused <= refused + 16'd1;
                        case (d_cnt)
                            3'd1: c_bad   <= c_bad + 16'd1;
                            3'd2: c_short <= c_short + 16'd1;
                            3'd3: c_long  <= c_long + 16'd1;
                            3'd4: c_rep   <= c_rep + 16'd1;
                            3'd5: c_ooo   <= c_ooo + 16'd1;
                            default: c_err <= c_err + 16'd1;
                        endcase
                    end
                    if (d_seqpass) begin
                        have_last <= 1'b1;
                        last      <= {h_seqh, h_seql};
                    end
                    if (d_ok && h_type == 8'd2) begin
                        case (pl[1][1:0])
                            2'd1: scr1 <= {pl[2], pl[3], pl[4], pl[5]};
                            2'd2: scr2 <= {pl[2], pl[3], pl[4], pl[5]};
                            2'd3: scr3 <= {pl[2], pl[3], pl[4], pl[5]};
                            default: ;
                        endcase
                    end
                    n   <= 5'd0;
                    crc <= 32'hFFFFFFFF;
                    st  <= ST_IDLE;
                end
                default: st <= ST_IDLE;
            endcase
        end
    end

    // packet and reply storage (data, no reset)
    always_ff @(posedge clk) begin
        if (in_wr) begin
            case (n)
                5'd0: h_type <= win_wdata[7:0];
                5'd1: h_len  <= win_wdata[7:0];
                5'd2: h_seqh <= win_wdata[7:0];
                5'd3: h_seql <= win_wdata[7:0];
                default: ;
            endcase
            if (n >= 5'd4 && n < 5'd12) pl[n[2:0] ^ 3'b100] <= win_wdata[7:0];
        end
        if (st == ST_BUILD) rbuf[bi] <= ob;
    end

    // ---------------- shell window read ----------------
    logic [8:0]  rbase, ri0, ri1, ri2, ri3;
    logic [31:0] rword;
    assign rbase = {ridx, 2'b00};
    assign ri0 = rbase;
    assign ri1 = rbase + 9'd1;
    assign ri2 = rbase + 9'd2;
    assign ri3 = rbase + 9'd3;
    assign rword = {
        (ri0 < {4'd0, rlen}) ? rbuf[ri0[4:0]] : 8'h00,
        (ri1 < {4'd0, rlen}) ? rbuf[ri1[4:0]] : 8'h00,
        (ri2 < {4'd0, rlen}) ? rbuf[ri2[4:0]] : 8'h00,
        (ri3 < {4'd0, rlen}) ? rbuf[ri3[4:0]] : 8'h00
    };

    always_ff @(posedge clk) begin
        if (rst) win_rdata <= 32'd0;
        else if (win_rd) begin
            case (win_addr)
                7'd2:    win_rdata <= {27'd0, rlen};
                7'd3:    win_rdata <= {25'd0, ridx};
                7'd4:    win_rdata <= rword;
                7'd5:    win_rdata <= {27'd0, tlen};
                7'd6:    win_rdata <= {25'd0, tidx};
                7'd7:    win_rdata <= tword;
                7'd9:    win_rdata <= {30'd0, (st != ST_IDLE), tel_on};
                default: win_rdata <= 32'd0;
            endcase
        end
    end

    logic unused_ok;
    assign unused_ok = &{1'b0, tel_held, d_reply, win_wdata[31:9], cw[31:8], regs_sh[31:8], svs[135:8]};
endmodule
