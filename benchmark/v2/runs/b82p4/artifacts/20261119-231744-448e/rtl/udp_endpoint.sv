// UDP command and telemetry endpoint: window registers, packet judge, reply builder.
module udp_endpoint #(
    parameter logic [31:0] ID_WORD = 32'h55445031
) (
    input  logic        clk,
    input  logic        rst,         // synchronous, active high
    input  logic [6:0]  win_addr,
    input  logic        win_wr,
    input  logic        win_rd,
    /* verilator lint_off UNUSEDSIGNAL */
    input  logic [31:0] win_wdata,   // only bits 8:0 are used by the window registers
    /* verilator lint_on UNUSEDSIGNAL */
    output logic [31:0] win_rdata,
    output logic [15:0] led
);
    typedef enum logic [2:0] {S_COL, S_EVAL, S_CRC, S_CHK, S_DEC, S_RCRC, S_TRL} st_t;
    localparam logic [31:0] RESIDUE = 32'hDEBB20E3;

    st_t         state;
    logic [4:0]  cnt, idx, plen, rlen;
    logic [7:0]  pbuf [0:15];
    logic [7:0]  rbuf [0:25];
    logic [31:0] crc, crc_nx;
    logic [31:0] scratch [0:2];
    logic [15:0] cmds, refused, c_crc, c_short, c_long, c_rep, c_ooo, c_err;
    logic [31:0] ticks;
    logic [15:0] pending;
    logic        have_last;
    logic [15:0] last_seq;
    logic [6:0]  ridx, tidx;
    logic        cmd_start, cmd_stop;

    // telemetry
    logic [15:0] period, fcnt;
    logic        tele_on;
    logic [31:0] tword;
    logic [7:0]  tlen;

    wire a_in   = win_wr && (win_addr == 7'd0);
    wire a_tick = win_wr && (win_addr == 7'd1);
    wire a_take = win_wr && (win_addr == 7'd8);
    wire tick   = (pending != 16'd0);
    wire busy   = (state != S_COL);

    assign led = cmds;

    /* verilator lint_off PINCONNECTEMPTY */
    udp_tele u_tele (
        .clk(clk), .rst(rst), .tick(tick), .ticks_next(ticks + 32'd1),
        .cmds(cmds), .refused(refused),
        .cmd_start(cmd_start), .cmd_stop(cmd_stop),
        .cmd_period({pbuf[4], pbuf[5]}),
        .take(a_take), .tidx(tidx),
        .period(period), .on(tele_on), .held(), .fcnt(fcnt),
        .tword(tword), .tlen(tlen));
    /* verilator lint_on PINCONNECTEMPTY */

    // CRC engine, shared by the packet check and the reply trailer
    logic [7:0] crc_byte;
    assign crc_byte = (state == S_CRC) ? pbuf[idx[3:0]] : rbuf[idx];
    udp_crc32_byte u_crc (.crc(crc), .d(crc_byte), .nxt(crc_nx));

    // eval helpers (a packet of fewer than 4 bytes is always too short)
    wire [8:0] lim      = 9'd8 + {1'b0, pbuf[1]};
    wire       is_long  = (cnt >= 5'd4) && (pbuf[1] > 8'd8 || {4'b0, cnt} > lim);
    wire       is_short = (cnt < 5'd4) || ({4'b0, cnt} < lim);

    // decision (S_DEC)
    wire [7:0]  typ    = pbuf[0];
    wire [7:0]  plenb  = pbuf[1];
    wire [15:0] seq    = {pbuf[2], pbuf[3]};
    wire [15:0] regno  = {pbuf[4], pbuf[5]};
    wire [31:0] wval   = {pbuf[6], pbuf[7], pbuf[8], pbuf[9]};
    wire [15:0] dseq   = seq - last_seq;
    wire        seq_ok = !have_last || (dseq != 16'd0 && !dseq[15]);

    logic [2:0]  d_status;
    logic [4:0]  d_plen;
    logic        d_ok, d_err, d_rep, d_ooo, d_wr;
    logic [31:0] regval;

    always_comb begin
        logic known, len_ok;
        known = (typ >= 8'd1) && (typ <= 8'd5);
        case (typ)
            8'd1:    len_ok = (plenb == 8'd2);
            8'd2:    len_ok = (plenb == 8'd6);
            8'd4:    len_ok = (plenb == 8'd2);
            default: len_ok = (plenb == 8'd0);
        endcase
        case (regno[2:0])
            3'd0:    regval = ID_WORD;
            3'd1:    regval = scratch[0];
            3'd2:    regval = scratch[1];
            3'd3:    regval = scratch[2];
            3'd4:    regval = {16'b0, cmds};
            3'd5:    regval = {16'b0, refused};
            3'd6:    regval = {16'b0, period};
            default: regval = ticks;
        endcase
        d_status = 3'd0;
        d_err = 1'b0; d_rep = 1'b0; d_ooo = 1'b0; d_wr = 1'b0;
        d_plen = 5'd0;
        if (!known) begin
            d_status = 3'd1; d_err = 1'b1;
        end else if (!len_ok) begin
            d_status = 3'd2; d_err = 1'b1;
        end else if (!seq_ok) begin
            d_status = 3'd4;
            d_rep = (dseq == 16'd0);
            d_ooo = (dseq != 16'd0);
        end else if ((typ == 8'd1 || typ == 8'd2) && regno >= 16'd8) begin
            d_status = 3'd3; d_err = 1'b1;
        end else if (typ == 8'd2 && !(regno == 16'd1 || regno == 16'd2 || regno == 16'd3)) begin
            d_status = 3'd5; d_err = 1'b1;
        end else begin
            d_wr = (typ == 8'd2);
            if (typ == 8'd1) d_plen = 5'd4;
            if (typ == 8'd3) d_plen = 5'd17;
        end
        d_ok = (d_status == 3'd0);
    end

    wire [135:0] spay = {cmds, c_crc, c_short, c_long, c_rep, c_ooo, c_err, fcnt, 7'b0, tele_on};

    // control
    always_ff @(posedge clk) begin
        cmd_start <= 1'b0;
        cmd_stop  <= 1'b0;
        if (rst) begin
            state     <= S_COL;
            cnt       <= 5'd0;
            idx       <= 5'd0;
            plen      <= 5'd0;
            rlen      <= 5'd0;
            cmds      <= 16'd0;
            refused   <= 16'd0;
            c_crc     <= 16'd0;
            c_short   <= 16'd0;
            c_long    <= 16'd0;
            c_rep     <= 16'd0;
            c_ooo     <= 16'd0;
            c_err     <= 16'd0;
            ticks     <= 32'd0;
            pending   <= 16'd0;
            have_last <= 1'b0;
            last_seq  <= 16'd0;
            ridx      <= 7'd0;
            tidx      <= 7'd0;
            for (int i = 0; i < 3; i++) scratch[i] <= 32'd0;
        end else begin
            // ticks
            pending <= pending + {8'b0, a_tick ? win_wdata[7:0] : 8'd0} - {15'b0, tick};
            if (tick) ticks <= ticks + 32'd1;
            // window registers
            if (win_wr && win_addr == 7'd3) ridx <= win_wdata[6:0];
            if (win_wr && win_addr == 7'd6) tidx <= win_wdata[6:0];

            case (state)
                S_COL: begin
                    if (a_in) begin
                        cnt <= (cnt == 5'd31) ? 5'd31 : cnt + 5'd1;
                        if (win_wdata[8]) state <= S_EVAL;
                    end
                end
                S_EVAL: begin
                    rlen <= 5'd0;
                    idx  <= 5'd0;
                    if (is_long) begin
                        c_long  <= c_long + 16'd1;
                        refused <= refused + 16'd1;
                        state <= S_COL; cnt <= 5'd0;
                    end else if (is_short) begin
                        c_short <= c_short + 16'd1;
                        refused <= refused + 16'd1;
                        state <= S_COL; cnt <= 5'd0;
                    end else begin
                        state <= S_CRC;
                    end
                end
                S_CRC: begin
                    idx <= idx + 5'd1;
                    if (idx + 5'd1 == cnt) state <= S_CHK;
                end
                S_CHK: begin
                    if (crc != RESIDUE) begin
                        c_crc   <= c_crc + 16'd1;
                        refused <= refused + 16'd1;
                        state <= S_COL; cnt <= 5'd0;
                    end else begin
                        state <= S_DEC;
                    end
                end
                S_DEC: begin
                    plen  <= d_plen;
                    idx   <= 5'd0;
                    state <= S_RCRC;
                    if (d_err) c_err <= c_err + 16'd1;
                    if (d_rep) c_rep <= c_rep + 16'd1;
                    if (d_ooo) c_ooo <= c_ooo + 16'd1;
                    if (!d_ok) refused <= refused + 16'd1;
                    if (d_ok) cmds <= cmds + 16'd1;
                    if (d_status != 3'd4 && d_status != 3'd1 && d_status != 3'd2) begin
                        have_last <= 1'b1;
                        last_seq  <= seq;
                    end
                    if (d_wr) begin
                        case (regno[1:0])
                            2'd1: scratch[0] <= wval;
                            2'd2: scratch[1] <= wval;
                            default: scratch[2] <= wval;
                        endcase
                    end
                    cmd_start <= d_ok && (typ == 8'd4);
                    cmd_stop  <= d_ok && (typ == 8'd5);
                end
                S_RCRC: begin
                    idx <= idx + 5'd1;
                    if (idx == plen + 5'd4) begin
                        idx   <= 5'd0;
                        state <= S_TRL;
                    end
                end
                S_TRL: begin
                    idx <= idx + 5'd1;
                    if (idx[1:0] == 2'd3) begin
                        rlen  <= plen + 5'd9;
                        state <= S_COL;
                        cnt   <= 5'd0;
                    end
                end
                default: state <= S_COL;
            endcase
        end
    end

    // datapath (no reset: lengths and flags gate every read)
    always_ff @(posedge clk) begin
        if (state == S_COL && a_in && cnt < 5'd16) pbuf[cnt[3:0]] <= win_wdata[7:0];

        case (state)
            S_EVAL:  crc <= 32'hFFFFFFFF;
            S_CRC:   crc <= crc_nx;
            S_DEC:   crc <= 32'hFFFFFFFF;
            S_RCRC:  crc <= crc_nx;
            default: ;
        endcase

        if (state == S_DEC) begin
            rbuf[0] <= typ | 8'h80;
            rbuf[1] <= {5'b0, d_status};
            rbuf[2] <= pbuf[2];
            rbuf[3] <= pbuf[3];
            rbuf[4] <= {3'b0, d_plen};
            if (d_ok && typ == 8'd3) begin
                for (int k = 0; k < 17; k++) rbuf[5 + k] <= spay[8 * (16 - k) +: 8];
            end else if (d_ok && typ == 8'd1) begin
                for (int k = 0; k < 4; k++) rbuf[5 + k] <= regval[8 * (3 - k) +: 8];
            end
        end
        if (state == S_TRL)
            rbuf[5'd5 + plen + {3'b0, idx[1:0]}] <= 8'((~crc) >> {idx[1:0], 3'b000});
    end

    // reply word read
    logic [31:0] rword;
    always_comb begin
        logic [8:0] j;
        logic [7:0] b [0:3];
        for (int k = 0; k < 4; k++) begin
            j = {ridx, 2'b00} + 9'(k);
            b[k] = (j < {4'b0, rlen}) ? rbuf[j[4:0]] : 8'h00;
        end
        rword = {b[0], b[1], b[2], b[3]};
    end

    // window read: data valid the cycle after win_rd
    always_ff @(posedge clk) begin
        if (win_rd) begin
            case (win_addr)
                7'd2:    win_rdata <= {27'b0, rlen};
                7'd3:    win_rdata <= {25'b0, ridx};
                7'd4:    win_rdata <= rword;
                7'd5:    win_rdata <= {24'b0, tlen};
                7'd6:    win_rdata <= {25'b0, tidx};
                7'd7:    win_rdata <= tword;
                7'd9:    win_rdata <= {30'b0, busy, tele_on};
                default: win_rdata <= 32'd0;
            endcase
        end
    end
endmodule
