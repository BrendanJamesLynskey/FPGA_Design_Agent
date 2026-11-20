// Packet engine: window decode, packet byte store, length/CRC-32 judging, sequence rule,
// registers R0-R7, counters, reply build (with CRC-32) and word readback.
module udp_core #(
    parameter logic [31:0] DESIGN_ID            = 32'h55445031,
    parameter int          DEFAULT_PERIOD_TICKS = 100,
    parameter int          MIN_PERIOD_TICKS     = 4,
    parameter logic [31:0] CRC_POLY             = 32'hEDB88320,
    parameter logic [31:0] CRC_INIT             = 32'hFFFFFFFF
) (
    input  logic        clk,
    input  logic        rst,
    input  logic [6:0]  win_addr,
    input  logic        win_wr,
    input  logic        win_rd,
    /* verilator lint_off UNUSEDSIGNAL */
    input  logic [31:0] win_wdata,
    /* verilator lint_on UNUSEDSIGNAL */
    output logic [31:0] win_rdata,
    output logic [15:0] led
);
    typedef enum logic [2:0] {S_RX, S_CLS, S_CRC, S_CMP, S_JDG, S_BLD, S_TRL} state_t;

    state_t st;

    logic [7:0]  rxb  [0:31];
    logic [7:0]  rbuf [0:31];
    logic [4:0]  n, nfin, ci, bi, rlen;
    logic [31:0] crc, crc_n;
    logic [6:0]  ridx;
    logic [15:0] last;
    logic        have_last;
    logic [31:0] cmds, refused, sc1, sc2, sc3;
    logic [15:0] cnt_bad, cnt_short, cnt_long, cnt_rep, cnt_ooo, cnt_err;

    // telemetry block
    logic        tel_on, held;
    logic [15:0] period, fcount;
    logic [31:0] uptime, tword;
    logic [6:0]  tidx;

    // ---------------------------------------------------------------- window decode
    wire wr_in   = win_wr && (win_addr == 7'd0);
    wire wr_tick = win_wr && (win_addr == 7'd1);
    wire wr_ridx = win_wr && (win_addr == 7'd3);
    wire wr_tidx = win_wr && (win_addr == 7'd6);
    wire wr_take = win_wr && (win_addr == 7'd8);

    wire        busy = (st != S_RX);
    wire [4:0]  n_nx = (n == 5'd31) ? 5'd31 : n + 5'd1;

    assign led = cmds[15:0];

    // ---------------------------------------------------------------- judging wires
    wire [7:0]  typ  = rxb[0];
    wire [7:0]  len  = rxb[1];
    wire [15:0] seq  = {rxb[2], rxb[3]};
    wire [15:0] regn = {rxb[4], rxb[5]};
    wire [31:0] wval = {rxb[6], rxb[7], rxb[8], rxb[9]};

    // classification (state S_CLS)
    wire [8:0] lenp8   = {1'b0, len} + 9'd8;
    wire [8:0] nfin9   = {4'b0, nfin};
    wire       long_c  = (nfin >= 5'd2) && ((len > 8'd8) || (nfin9 > lenp8));
    wire       short_c = (nfin < 5'd4) || (nfin9 < lenp8);

    // CRC compare (state S_CMP)
    wire [4:0]  tb    = len[4:0] + 5'd4;
    wire [31:0] trail = {rxb[tb + 5'd3], rxb[tb + 5'd2], rxb[tb + 5'd1], rxb[tb]};
    wire [31:0] fin   = ~crc;
    wire        crc_ok = (fin == trail);

    // decision (state S_JDG)
    logic        known, len_ok, seq_ok, acc;
    logic [7:0]  need;
    logic [15:0] delta;
    logic [2:0]  stc;
    logic [4:0]  plen;
    logic [31:0] regval;
    logic [135:0] pv;

    always_comb begin
        known = (typ >= 8'd1) && (typ <= 8'd5);
        case (typ)
            8'd1, 8'd4: need = 8'd2;
            8'd2:       need = 8'd6;
            default:    need = 8'd0;
        endcase
        len_ok = (len == need);
        delta  = seq - last;
        seq_ok = !have_last || ((delta != 16'd0) && !delta[15]);
        acc    = known && len_ok && seq_ok;
        stc    = 3'd0;
        if (!known)                                          stc = 3'd1;
        else if (!len_ok)                                    stc = 3'd2;
        else if (!seq_ok)                                    stc = 3'd4;
        else if ((typ == 8'd1 || typ == 8'd2) && (|regn[15:3])) stc = 3'd3;
        else if (typ == 8'd2 && !(regn[2:0] == 3'd1 || regn[2:0] == 3'd2 || regn[2:0] == 3'd3))
                                                             stc = 3'd5;

        case (regn[2:0])
            3'd0:    regval = DESIGN_ID;
            3'd1:    regval = sc1;
            3'd2:    regval = sc2;
            3'd3:    regval = sc3;
            3'd4:    regval = cmds;
            3'd5:    regval = refused;
            3'd6:    regval = {16'b0, period};
            default: regval = uptime;
        endcase

        if (typ == 8'd3)
            pv = {cmds[15:0], cnt_bad, cnt_short, cnt_long, cnt_rep, cnt_ooo, cnt_err, fcount, 7'b0, tel_on};
        else
            pv = {regval, 104'b0};

        plen = 5'd0;
        if (stc == 3'd0) begin
            if (typ == 8'd1)      plen = 5'd4;
            else if (typ == 8'd3) plen = 5'd17;
        end
    end

    wire jdg      = (st == S_JDG);
    wire start_p  = jdg && (stc == 3'd0) && (typ == 8'd4);
    wire stop_p   = jdg && (stc == 3'd0) && (typ == 8'd5);

    // ---------------------------------------------------------------- CRC engine (rx check and reply build)
    wire [7:0] crc_d = (st == S_BLD) ? rbuf[bi] : rxb[ci];
    crc32_byte #(.CRC_POLY(CRC_POLY)) u_crc (.crc_i(crc), .d(crc_d), .crc_o(crc_n));

    // ---------------------------------------------------------------- telemetry
    udp_tel #(
        .DEFAULT_PERIOD_TICKS(DEFAULT_PERIOD_TICKS), .MIN_PERIOD_TICKS(MIN_PERIOD_TICKS),
        .CRC_POLY(CRC_POLY), .CRC_INIT(CRC_INIT)
    ) u_tel (
        .clk(clk), .rst(rst),
        .tick_we(wr_tick), .tick_n(win_wdata[7:0]),
        .take(wr_take),
        .start_p(start_p), .start_per(regn), .stop_p(stop_p),
        .cmds16(cmds[15:0]), .refused16(refused[15:0]),
        .tidx_we(wr_tidx), .tidx_wd(win_wdata[6:0]), .tidx(tidx),
        .tel_on(tel_on), .period(period), .uptime(uptime), .fcount(fcount),
        .held(held), .tword(tword)
    );

    // ---------------------------------------------------------------- control (reset)
    always_ff @(posedge clk) begin
        if (rst) begin
            st        <= S_RX;
            n         <= 5'd0;
            ci        <= 5'd0;
            bi        <= 5'd0;
            rlen      <= 5'd0;
            ridx      <= 7'd0;
            last      <= 16'd0;
            have_last <= 1'b0;
            cmds      <= 32'd0;
            refused   <= 32'd0;
            sc1       <= 32'd0;
            sc2       <= 32'd0;
            sc3       <= 32'd0;
            cnt_bad   <= 16'd0;
            cnt_short <= 16'd0;
            cnt_long  <= 16'd0;
            cnt_rep   <= 16'd0;
            cnt_ooo   <= 16'd0;
            cnt_err   <= 16'd0;
        end else begin
            if (wr_ridx) ridx <= win_wdata[6:0];

            case (st)
                S_RX: begin
                    if (wr_in) begin
                        n <= n_nx;
                        if (win_wdata[8]) begin
                            n    <= 5'd0;
                            rlen <= 5'd0;
                            st   <= S_CLS;
                        end
                    end
                end
                S_CLS: begin
                    ci <= 5'd0;
                    if (long_c) begin
                        cnt_long <= cnt_long + 16'd1;
                        refused  <= refused + 32'd1;
                        st       <= S_RX;
                    end else if (short_c) begin
                        cnt_short <= cnt_short + 16'd1;
                        refused   <= refused + 32'd1;
                        st        <= S_RX;
                    end else begin
                        st <= S_CRC;
                    end
                end
                S_CRC: begin
                    if (ci == len[4:0] + 5'd3) st <= S_CMP;
                    else                       ci <= ci + 5'd1;
                end
                S_CMP: begin
                    if (crc_ok) begin
                        st <= S_JDG;
                    end else begin
                        cnt_bad <= cnt_bad + 16'd1;
                        refused <= refused + 32'd1;
                        st      <= S_RX;
                    end
                end
                S_JDG: begin
                    if (acc) begin
                        last      <= seq;
                        have_last <= 1'b1;
                    end
                    if (stc != 3'd0) begin
                        refused <= refused + 32'd1;
                        if (stc == 3'd4) begin
                            if (delta == 16'd0) cnt_rep <= cnt_rep + 16'd1;
                            else                cnt_ooo <= cnt_ooo + 16'd1;
                        end else begin
                            cnt_err <= cnt_err + 16'd1;
                        end
                    end else begin
                        cmds <= cmds + 32'd1;
                        if (typ == 8'd2) begin
                            case (regn[1:0])
                                2'd1:    sc1 <= wval;
                                2'd2:    sc2 <= wval;
                                default: sc3 <= wval;
                            endcase
                        end
                    end
                    rlen <= 5'd9 + plen;
                    bi   <= 5'd0;
                    st   <= S_BLD;
                end
                S_BLD: begin
                    if (bi == rlen - 5'd5) st <= S_TRL;
                    else                   bi <= bi + 5'd1;
                end
                S_TRL: st <= S_RX;
                default: st <= S_RX;
            endcase
        end
    end

    // ---------------------------------------------------------------- datapath (no reset)
    always_ff @(posedge clk) begin
        if (st == S_RX && wr_in && n < 5'd16) rxb[{1'b0, n[3:0]}] <= win_wdata[7:0];
        if (st == S_RX && wr_in && win_wdata[8]) nfin <= n_nx;

        if (st == S_CLS || st == S_JDG) crc <= CRC_INIT;
        else if (st == S_CRC || st == S_BLD) crc <= crc_n;

        if (st == S_JDG) begin
            rbuf[0] <= typ | 8'h80;
            rbuf[1] <= {5'b0, stc};
            rbuf[2] <= rxb[2];
            rbuf[3] <= rxb[3];
            rbuf[4] <= {3'b0, plen};
            for (int k = 0; k < 17; k++) rbuf[5 + k] <= pv[135 - 8 * k -: 8];
        end
        if (st == S_TRL) begin
            rbuf[rlen - 5'd4]        <= fin[7:0];
            rbuf[rlen - 5'd4 + 5'd1] <= fin[15:8];
            rbuf[rlen - 5'd4 + 5'd2] <= fin[23:16];
            rbuf[rlen - 5'd4 + 5'd3] <= fin[31:24];
        end
    end

    // ---------------------------------------------------------------- reply word read
    logic [31:0] rword;
    always_comb begin
        rword = 32'h0;
        for (int k = 0; k < 4; k++) begin
            logic [8:0] idx;
            idx = {ridx, 2'b00} + 9'(k);
            if (idx < {4'b0, rlen}) rword[31 - 8 * k -: 8] = rbuf[idx[4:0]];
        end
    end

    // window read: registered, valid the cycle after win_rd
    always_ff @(posedge clk) begin
        case (win_addr)
            7'd2:    win_rdata <= {27'b0, rlen};
            7'd3:    win_rdata <= {25'b0, ridx};
            7'd4:    win_rdata <= rword;
            7'd5:    win_rdata <= held ? 32'd17 : 32'd0;
            7'd6:    win_rdata <= {25'b0, tidx};
            7'd7:    win_rdata <= tword;
            7'd9:    win_rdata <= {30'b0, busy, tel_on};
            default: win_rdata <= 32'd0;
        endcase
    end

    wire unused_rd = win_rd;
endmodule
