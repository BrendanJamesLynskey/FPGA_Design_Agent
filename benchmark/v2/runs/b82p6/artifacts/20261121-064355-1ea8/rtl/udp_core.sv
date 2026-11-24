// udp_core: packet receiver (CRC-32), judge, reply builder, telemetry and tick generator,
// behind the shell window. Single clock, synchronous active-high reset on control state only.
module udp_core (
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
    localparam logic [31:0] ID_WORD     = 32'h55445031;
    localparam logic [31:0] CRC_INIT    = 32'hFFFFFFFF;
    localparam logic [31:0] CRC_RESIDUE = 32'hDEBB20E3;

    // one byte-wide CRC-32 update (reflected 0xEDB88320), shared by receive, reply and frame
    function automatic logic [31:0] crc8(input logic [31:0] c, input logic [7:0] d);
        logic [31:0] r;
        r = c ^ {24'd0, d};
        for (int i = 0; i < 8; i++) r = r[0] ? ((r >> 1) ^ 32'hEDB88320) : (r >> 1);
        return r;
    endfunction

    typedef enum logic [1:0] {S_IDLE, S_J1, S_J2, S_BUILD} st_t;
    localparam logic [1:0] K_NONE = 2'd0, K_READ = 2'd1, K_STAT = 2'd2;

    // ---------------------------------------------------------------- window decode
    logic wr_in, wr_tick, wr_ridx, wr_tidx, wr_take;
    assign wr_in   = win_wr && (win_addr == 7'd0);
    assign wr_tick = win_wr && (win_addr == 7'd1);
    assign wr_ridx = win_wr && (win_addr == 7'd3);
    assign wr_tidx = win_wr && (win_addr == 7'd6);
    assign wr_take = win_wr && (win_addr == 7'd8);

    // ---------------------------------------------------------------- state
    st_t         state;
    logic [4:0]  rn;                 // bytes received (saturating)
    logic [31:0] rcrc;               // running CRC of the packet received
    logic [15:0] c_cmds, c_bad, c_short, c_long, c_rep, c_ooo, c_err, c_refused, fcount;
    logic [15:0] last_seq;
    logic        have_last;
    logic [31:0] scratch [0:2];
    logic [15:0] period;
    logic [15:0] tcnt;
    logic [31:0] uptime;
    logic [7:0]  tpend;
    logic        tele_on;
    logic [7:0]  fseq;
    logic        fheld, fb_busy;
    logic [3:0]  fb_bi;
    logic [31:0] fcrc;
    logic [31:0] fc_up;
    logic [15:0] fc_cmd, fc_ref;
    logic [7:0]  fc_seq;
    logic [5:0]  r_bi;
    logic [31:0] rcrc_r;
    logic [2:0]  r_status;
    logic [1:0]  r_kind;
    logic [4:0]  r_plen;
    logic [31:0] rval;
    logic        cmd_pend;
    logic [5:0]  rlen;
    logic [6:0]  ridx, tidx;

    // datapath (no reset)
    logic [7:0]  pb [0:11];
    logic [7:0]  rbuf [0:31];
    logic [7:0]  fbuf [0:15];
    logic        f_long, f_short, f_crcok, f_typok, f_lenok, f_seqnew, f_seqeq, f_regok, f_ro;

    logic busy;
    assign busy = (state != S_IDLE);
    assign led  = c_cmds;

    // ---------------------------------------------------------------- judge stage 1: flags (no reset)
    logic [7:0] j_pl, j_need;
    logic [8:0] j_lp8, j_n9;
    logic [15:0] j_seq, j_dd;
    assign j_pl   = pb[1];
    assign j_lp8  = {1'b0, j_pl} + 9'd8;
    assign j_n9   = {4'b0, rn};
    assign j_seq  = {pb[2], pb[3]};
    assign j_dd   = j_seq - last_seq;
    always_comb begin
        case (pb[0])
            8'd1, 8'd4: j_need = 8'd2;
            8'd2:       j_need = 8'd6;
            default:    j_need = 8'd0;
        endcase
    end

    always_ff @(posedge clk) begin
        if (state == S_J1) begin
            f_long   <= (rn >= 5'd4) && ((j_pl > 8'd8) || (j_n9 > j_lp8));
            f_short  <= (rn < 5'd4) || (j_n9 < j_lp8);
            f_crcok  <= (rcrc == CRC_RESIDUE);
            f_typok  <= (pb[0] >= 8'd1) && (pb[0] <= 8'd5);
            f_lenok  <= (j_pl == j_need);
            f_seqnew <= !have_last || ((j_dd != 16'd0) && !j_dd[15]);
            f_seqeq  <= (j_seq == last_seq);
            f_regok  <= (pb[4] == 8'd0) && (pb[5] < 8'd8);
            f_ro     <= pb[5][2] || (pb[5][2:0] == 3'd0);
        end
    end

    // ---------------------------------------------------------------- judge stage 2: decision
    logic        d_drop, d_long, d_short, d_bad, d_rep, d_ooo, d_err, d_ref, d_ok, d_acc, d_wr, d_start, d_stop;
    logic [2:0]  d_status;
    logic [1:0]  d_kind;
    logic [4:0]  d_plen;
    logic [31:0] d_val;

    always_comb begin
        d_drop = 1'b0; d_long = 1'b0; d_short = 1'b0; d_bad = 1'b0; d_rep = 1'b0; d_ooo = 1'b0;
        d_err = 1'b0; d_ref = 1'b0; d_ok = 1'b0; d_acc = 1'b0; d_wr = 1'b0; d_start = 1'b0; d_stop = 1'b0;
        d_status = 3'd0; d_kind = K_NONE; d_plen = 5'd0;
        if (f_long) begin
            d_drop = 1'b1; d_long = 1'b1; d_ref = 1'b1;
        end else if (f_short) begin
            d_drop = 1'b1; d_short = 1'b1; d_ref = 1'b1;
        end else if (!f_crcok) begin
            d_drop = 1'b1; d_bad = 1'b1; d_ref = 1'b1;
        end else if (!f_typok) begin
            d_status = 3'd1; d_err = 1'b1; d_ref = 1'b1;
        end else if (!f_lenok) begin
            d_status = 3'd2; d_err = 1'b1; d_ref = 1'b1;
        end else if (!f_seqnew) begin
            d_status = 3'd4; d_ref = 1'b1; d_rep = f_seqeq; d_ooo = !f_seqeq;
        end else begin
            d_acc = 1'b1;
            case (pb[0])
                8'd1, 8'd2: begin
                    if (!f_regok) begin
                        d_status = 3'd3; d_err = 1'b1; d_ref = 1'b1;
                    end else if (pb[0] == 8'd2 && f_ro) begin
                        d_status = 3'd5; d_err = 1'b1; d_ref = 1'b1;
                    end else if (pb[0] == 8'd1) begin
                        d_ok = 1'b1; d_kind = K_READ; d_plen = 5'd4;
                    end else begin
                        d_ok = 1'b1; d_wr = 1'b1;
                    end
                end
                8'd3: begin d_ok = 1'b1; d_kind = K_STAT; d_plen = 5'd17; end
                8'd4: begin d_ok = 1'b1; d_start = 1'b1; end
                default: begin d_ok = 1'b1; d_stop = 1'b1; end
            endcase
        end
    end

    always_comb begin
        case (pb[5][2:0])
            3'd0:    d_val = ID_WORD;
            3'd1:    d_val = scratch[0];
            3'd2:    d_val = scratch[1];
            3'd3:    d_val = scratch[2];
            3'd4:    d_val = {16'd0, c_cmds};
            3'd5:    d_val = {16'd0, c_refused};
            3'd6:    d_val = {16'd0, period};
            default: d_val = uptime;
        endcase
    end

    logic [15:0] d_per;
    assign d_per = {pb[4], pb[5]};

    // ---------------------------------------------------------------- reply byte generation
    logic [5:0]  hdr_len;
    logic [4:0]  pj;
    logic [15:0] ctr_sel;
    logic [7:0]  pay, bld_byte;
    logic [1:0]  tk;
    assign hdr_len = 6'd5 + {1'b0, r_plen};
    assign pj      = 5'(r_bi - 6'd5);
    assign tk      = 2'(r_bi - hdr_len);

    always_comb begin
        case (pj[4:1])
            4'd0:    ctr_sel = c_cmds;
            4'd1:    ctr_sel = c_bad;
            4'd2:    ctr_sel = c_short;
            4'd3:    ctr_sel = c_long;
            4'd4:    ctr_sel = c_rep;
            4'd5:    ctr_sel = c_ooo;
            4'd6:    ctr_sel = c_err;
            default: ctr_sel = fcount;
        endcase
        pay = 8'h00;
        if (r_kind == K_READ) begin
            case (pj[1:0])
                2'd0:    pay = rval[31:24];
                2'd1:    pay = rval[23:16];
                2'd2:    pay = rval[15:8];
                default: pay = rval[7:0];
            endcase
        end else if (r_kind == K_STAT) begin
            if (pj[4]) pay = {7'd0, tele_on};
            else       pay = pj[0] ? ctr_sel[7:0] : ctr_sel[15:8];
        end
        if (r_bi >= hdr_len) begin
            case (tk)
                2'd0:    bld_byte = ~rcrc_r[7:0];
                2'd1:    bld_byte = ~rcrc_r[15:8];
                2'd2:    bld_byte = ~rcrc_r[23:16];
                default: bld_byte = ~rcrc_r[31:24];
            endcase
        end else begin
            case (r_bi)
                6'd0:    bld_byte = pb[0] | 8'h80;
                6'd1:    bld_byte = {5'd0, r_status};
                6'd2:    bld_byte = pb[2];
                6'd3:    bld_byte = pb[3];
                6'd4:    bld_byte = {3'd0, r_plen};
                default: bld_byte = pay;
            endcase
        end
    end

    // ---------------------------------------------------------------- frame byte generation
    logic [7:0] fr_byte;
    always_comb begin
        case (fb_bi)
            4'd0:    fr_byte = 8'hC0;
            4'd1:    fr_byte = 8'h00;
            4'd2:    fr_byte = fc_seq;
            4'd3:    fr_byte = 8'd8;
            4'd4:    fr_byte = fc_up[31:24];
            4'd5:    fr_byte = fc_up[23:16];
            4'd6:    fr_byte = fc_up[15:8];
            4'd7:    fr_byte = fc_up[7:0];
            4'd8:    fr_byte = fc_cmd[15:8];
            4'd9:    fr_byte = fc_cmd[7:0];
            4'd10:   fr_byte = fc_ref[15:8];
            4'd11:   fr_byte = fc_ref[7:0];
            4'd12:   fr_byte = ~fcrc[7:0];
            4'd13:   fr_byte = ~fcrc[15:8];
            4'd14:   fr_byte = ~fcrc[23:16];
            default: fr_byte = ~fcrc[31:24];
        endcase
    end

    // ---------------------------------------------------------------- tick and telemetry due
    logic        tick;
    logic [16:0] tcnt_n;
    assign tick   = (tpend != 8'd0);
    assign tcnt_n = {1'b0, tcnt} + 17'd1;

    // ---------------------------------------------------------------- control state
    always_ff @(posedge clk) begin
        if (rst) begin
            state     <= S_IDLE;
            rn        <= 5'd0;
            rcrc      <= CRC_INIT;
            c_cmds    <= 16'd0;
            c_bad     <= 16'd0;
            c_short   <= 16'd0;
            c_long    <= 16'd0;
            c_rep     <= 16'd0;
            c_ooo     <= 16'd0;
            c_err     <= 16'd0;
            c_refused <= 16'd0;
            fcount    <= 16'd0;
            last_seq  <= 16'd0;
            have_last <= 1'b0;
            scratch[0] <= 32'd0;
            scratch[1] <= 32'd0;
            scratch[2] <= 32'd0;
            period    <= 16'd100;
            tcnt      <= 16'd0;
            uptime    <= 32'd0;
            tpend     <= 8'd0;
            tele_on   <= 1'b0;
            fseq      <= 8'd0;
            fheld     <= 1'b0;
            fb_busy   <= 1'b0;
            fb_bi     <= 4'd0;
            fcrc      <= CRC_INIT;
            fc_up     <= 32'd0;
            fc_cmd    <= 16'd0;
            fc_ref    <= 16'd0;
            fc_seq    <= 8'd0;
            r_bi      <= 6'd0;
            rcrc_r    <= CRC_INIT;
            r_status  <= 3'd0;
            r_kind    <= K_NONE;
            r_plen    <= 5'd0;
            rval      <= 32'd0;
            cmd_pend  <= 1'b0;
            rlen      <= 6'd0;
            ridx      <= 7'd0;
            tidx      <= 7'd0;
        end else begin
            // ---- tick generator, uptime, telemetry period count
            if (tick) begin
                tpend  <= tpend - 8'd1;
                uptime <= uptime + 32'd1;
                if (tele_on) begin
                    if (tcnt_n >= {1'b0, period}) begin
                        tcnt <= 16'd0;
                        if (!fheld && !fb_busy) begin
                            fb_busy <= 1'b1;
                            fb_bi   <= 4'd0;
                            fcrc    <= CRC_INIT;
                            fc_up   <= uptime + 32'd1;
                            fc_cmd  <= c_cmds;
                            fc_ref  <= c_refused;
                            fc_seq  <= fseq;
                            fseq    <= fseq + 8'd1;
                            fcount  <= fcount + 16'd1;
                        end
                    end else begin
                        tcnt <= tcnt_n[15:0];
                    end
                end
            end
            if (wr_tick) tpend <= win_wdata[7:0];

            // ---- frame builder: one byte per clock
            if (fb_busy) begin
                if (fb_bi < 4'd12) fcrc <= crc8(fcrc, fr_byte);
                fb_bi <= fb_bi + 4'd1;
                if (fb_bi == 4'd15) begin
                    fb_busy <= 1'b0;
                    fheld   <= 1'b1;
                end
            end

            // ---- window registers
            if (wr_ridx) ridx <= win_wdata[6:0];
            if (wr_tidx) tidx <= win_wdata[6:0];

            // ---- packet receive
            if (wr_in && (state == S_IDLE)) begin
                rcrc <= crc8(rcrc, win_wdata[7:0]);
                if (rn != 5'd31) rn <= rn + 5'd1;
                if (win_wdata[8]) begin
                    state <= S_J1;
                    rlen  <= 6'd0;
                end
            end

            // ---- judge, reply build
            case (state)
                S_J1: begin
                    rn    <= 5'd0;
                    rcrc  <= CRC_INIT;
                    state <= S_J2;
                end
                S_J2: begin
                    state    <= d_drop ? S_IDLE : S_BUILD;
                    r_bi     <= 6'd0;
                    rcrc_r   <= CRC_INIT;
                    r_status <= d_status;
                    r_kind   <= d_kind;
                    r_plen   <= d_plen;
                    rval     <= d_val;
                    cmd_pend <= d_ok;
                    if (d_long)  c_long  <= c_long + 16'd1;
                    if (d_short) c_short <= c_short + 16'd1;
                    if (d_bad)   c_bad   <= c_bad + 16'd1;
                    if (d_rep)   c_rep   <= c_rep + 16'd1;
                    if (d_ooo)   c_ooo   <= c_ooo + 16'd1;
                    if (d_err)   c_err   <= c_err + 16'd1;
                    if (d_ref)   c_refused <= c_refused + 16'd1;
                    if (d_acc) begin
                        last_seq  <= j_seq;
                        have_last <= 1'b1;
                    end
                    if (d_wr) begin
                        case (pb[5][1:0])
                            2'd1:    scratch[0] <= {pb[6], pb[7], pb[8], pb[9]};
                            2'd2:    scratch[1] <= {pb[6], pb[7], pb[8], pb[9]};
                            default: scratch[2] <= {pb[6], pb[7], pb[8], pb[9]};
                        endcase
                    end
                    if (d_start) begin
                        if (d_per != 16'd0) period <= (d_per < 16'd4) ? 16'd4 : d_per;
                        tele_on <= 1'b1;
                        tcnt    <= 16'd0;
                    end
                    if (d_stop) begin
                        tele_on <= 1'b0;
                        fheld   <= 1'b0;
                        fb_busy <= 1'b0;
                    end
                end
                S_BUILD: begin
                    if (r_bi < hdr_len) rcrc_r <= crc8(rcrc_r, bld_byte);
                    r_bi <= r_bi + 6'd1;
                    if (r_bi == hdr_len + 6'd3) begin
                        rlen  <= hdr_len + 6'd4;
                        state <= S_IDLE;
                        if (cmd_pend) begin
                            c_cmds   <= c_cmds + 16'd1;
                            cmd_pend <= 1'b0;
                        end
                    end
                end
                default: ;
            endcase

            // ---- take releases the held frame
            if (wr_take) begin
                fheld   <= 1'b0;
                fb_busy <= 1'b0;
            end
        end
    end

    // ---------------------------------------------------------------- buffers (no reset)
    always_ff @(posedge clk) begin
        if (wr_in && (state == S_IDLE) && (rn < 5'd12)) pb[rn[3:0]] <= win_wdata[7:0];
        if (state == S_BUILD) rbuf[r_bi[4:0]] <= bld_byte;
        if (fb_busy) fbuf[fb_bi] <= fr_byte;
    end

    // ---------------------------------------------------------------- readback words
    logic [8:0]  ri, ti;
    logic [7:0]  rb [0:3];
    logic [7:0]  tb [0:3];
    logic [31:0] rword, tword;
    logic [5:0]  tlen;
    assign tlen = fheld ? 6'd16 : 6'd0;

    always_comb begin
        for (int k = 0; k < 4; k++) begin
            ri    = {ridx, 2'b00} + 9'(k);
            ti    = {tidx, 2'b00} + 9'(k);
            rb[k] = (ri < {3'd0, rlen}) ? rbuf[ri[4:0]] : 8'h00;
            tb[k] = (ti < {3'd0, tlen}) ? fbuf[ti[3:0]] : 8'h00;
        end
        rword = {rb[0], rb[1], rb[2], rb[3]};
        tword = {tb[0], tb[1], tb[2], tb[3]};
    end

    always_ff @(posedge clk) begin
        if (rst) win_rdata <= 32'd0;
        else if (win_rd) begin
            case (win_addr)
                7'd2:    win_rdata <= {26'd0, rlen};
                7'd3:    win_rdata <= {25'd0, ridx};
                7'd4:    win_rdata <= rword;
                7'd5:    win_rdata <= {26'd0, tlen};
                7'd6:    win_rdata <= {25'd0, tidx};
                7'd7:    win_rdata <= tword;
                7'd9:    win_rdata <= {30'd0, busy, tele_on};
                default: win_rdata <= 32'd0;
            endcase
        end
    end
endmodule
