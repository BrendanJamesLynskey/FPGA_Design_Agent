// udp_core: packet parser (streaming CRC-32), sequence/register/counter logic,
// reply builder, telemetry and shell window registers. Single clock, sync reset.
module udp_core #(
    parameter logic [31:0] ID_WORD      = 32'h55445031,
    parameter int          PERIOD_RESET = 100,
    parameter int          PERIOD_MIN   = 4
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
    localparam logic [31:0] CRC_INIT = 32'hFFFF_FFFF;

    function automatic logic [31:0] crc8(input logic [31:0] c, input logic [7:0] b);
        logic [31:0] x;
        x = c ^ {24'd0, b};
        for (int i = 0; i < 8; i++) x = x[0] ? ((x >> 1) ^ 32'hEDB88320) : (x >> 1);
        return x;
    endfunction

    // ------------------------------------------------------------ parser
    logic [7:0]  pbuf [0:9];
    logic [7:0]  n;
    logic [31:0] pcrc;
    logic [7:0]  d0, d1, d2, d3;
    logic        ev;

    wire        in_wr  = win_wr && (win_addr == 7'd0);
    wire [7:0]  in_b   = win_wdata[7:0];
    wire        in_end = win_wdata[8];
    wire [7:0]  n_cur   = ev ? 8'd0 : n;
    wire [31:0] crc_cur = ev ? CRC_INIT : pcrc;

    always_ff @(posedge clk) begin
        if (rst) begin
            n    <= 8'd0;
            pcrc <= CRC_INIT;
            ev   <= 1'b0;
        end else begin
            ev <= 1'b0;
            if (in_wr) begin
                pcrc <= (n_cur >= 8'd4) ? crc8(crc_cur, d3) : crc_cur;
                n    <= (n_cur == 8'd255) ? 8'd255 : n_cur + 8'd1;
                ev   <= in_end;
            end else if (ev) begin
                n    <= 8'd0;
                pcrc <= CRC_INIT;
            end
        end
    end

    always_ff @(posedge clk) begin
        if (in_wr) begin
            d3 <= d2; d2 <= d1; d1 <= d0; d0 <= in_b;
            if (n_cur < 8'd10) pbuf[n_cur[3:0]] <= in_b;
        end
    end

    // ------------------------------------------------------------ evaluation (cycle after the end byte)
    logic [31:0] scratch [0:2];
    logic [31:0] cmds, refused, ticks;
    logic [15:0] c_crc, c_short, c_long, c_rep, c_ooo, c_err;
    logic [15:0] last_seq, period, fcount, fseq, tcnt;
    logic        have_last, tel_on, held;

    wire [7:0]  p_typ = pbuf[0];
    wire [7:0]  p_len = pbuf[1];
    wire [15:0] p_seq = {pbuf[2], pbuf[3]};
    wire [15:0] p_reg = {pbuf[4], pbuf[5]};
    wire [15:0] diff  = p_seq - last_seq;
    wire [8:0]  full_len = {1'b0, p_len} + 9'd8;

    logic        d_short, d_long, d_crc, d_rep, d_ooo, d_err, d_reply, d_ok, d_accept;
    logic [2:0]  d_status;
    logic [7:0]  need;
    logic [31:0] rv;

    always_comb begin
        case (p_typ)
            8'd1:    need = 8'd2;
            8'd2:    need = 8'd6;
            8'd4:    need = 8'd2;
            default: need = 8'd0;
        endcase
        case (p_reg[2:0])
            3'd0:    rv = ID_WORD;
            3'd1:    rv = scratch[0];
            3'd2:    rv = scratch[1];
            3'd3:    rv = scratch[2];
            3'd4:    rv = cmds;
            3'd5:    rv = refused;
            3'd6:    rv = {16'd0, period};
            default: rv = ticks;
        endcase
        d_short = 1'b0; d_long = 1'b0; d_crc = 1'b0; d_rep = 1'b0; d_ooo = 1'b0;
        d_err = 1'b0; d_reply = 1'b0; d_ok = 1'b0; d_accept = 1'b0; d_status = 3'd0;
        if (n < 8'd4) begin
            d_short = 1'b1;
        end else if (p_len > 8'd8 || {1'b0, n} > full_len) begin
            d_long = 1'b1;
        end else if ({1'b0, n} < full_len) begin
            d_short = 1'b1;
        end else if (~pcrc != {d0, d1, d2, d3}) begin
            d_crc = 1'b1;
        end else begin
            d_reply = 1'b1;
            if (p_typ == 8'd0 || p_typ > 8'd5) begin
                d_status = 3'd1; d_err = 1'b1;
            end else if (p_len != need) begin
                d_status = 3'd2; d_err = 1'b1;
            end else if (have_last && (diff == 16'd0 || diff[15])) begin
                d_status = 3'd4;
                if (diff == 16'd0) d_rep = 1'b1; else d_ooo = 1'b1;
            end else begin
                d_accept = 1'b1;
                if (p_typ == 8'd1 || p_typ == 8'd2) begin
                    if (p_reg[15:3] != 13'd0) begin
                        d_status = 3'd3; d_err = 1'b1;
                    end else if (p_typ == 8'd2 && (p_reg[2:0] == 3'd0 || p_reg[2] == 1'b1)) begin
                        d_status = 3'd5; d_err = 1'b1;
                    end
                end
                d_ok = !d_err;
            end
        end
    end

    // ------------------------------------------------------------ tick generation and telemetry state
    logic [15:0] pending;
    logic        tb_busy;
    logic [4:0]  tb_idx;
    logic [31:0] tb_crc;
    logic [7:0]  tbuf [0:31];

    wire tick_wr = win_wr && (win_addr == 7'd1);
    wire tick_ev = (pending != 16'd0);
    wire due     = tick_ev && tel_on && (({1'b0, tcnt} + 17'd1) >= {1'b0, period});
    wire due_cap = due && !held;
    wire take_wr = win_wr && (win_addr == 7'd8);
    wire [31:0] ticks_n = ticks + 32'd1;

    // reply builder state
    logic        rb_busy;
    logic [4:0]  rb_idx;
    logic [1:0]  rb_ci;
    logic [31:0] rb_crc;
    logic [7:0]  rb_typ, rb_st, rb_plen;
    logic [15:0] rb_seq;
    logic [135:0] plv;
    logic [7:0]  rlen;
    logic [7:0]  rbuf [0:31];

    wire [7:0] rb_end = rb_plen + 8'd5;
    logic [7:0] rb_byte;
    always_comb begin
        case (rb_idx)
            5'd0:    rb_byte = rb_typ;
            5'd1:    rb_byte = rb_st;
            5'd2:    rb_byte = rb_seq[15:8];
            5'd3:    rb_byte = rb_seq[7:0];
            5'd4:    rb_byte = rb_plen;
            default: rb_byte = plv[135:128];
        endcase
    end
    wire [31:0] rb_fin = ~rb_crc;
    logic [7:0] rb_cbyte;
    always_comb begin
        case (rb_ci)
            2'd0:    rb_cbyte = rb_fin[7:0];
            2'd1:    rb_cbyte = rb_fin[15:8];
            2'd2:    rb_cbyte = rb_fin[23:16];
            default: rb_cbyte = rb_fin[31:24];
        endcase
    end

    always_ff @(posedge clk) begin
        if (rb_busy) begin
            if ({3'd0, rb_idx} < rb_end) rbuf[rb_idx] <= rb_byte;
            else                         rbuf[rb_idx] <= rb_cbyte;
        end
    end

    always_ff @(posedge clk) begin
        if (ev && d_reply) begin
            rb_typ  <= p_typ | 8'h80;
            rb_st   <= {5'd0, d_status};
            rb_seq  <= p_seq;
            rb_plen <= (d_status != 3'd0) ? 8'd0 :
                       (p_typ == 8'd1) ? 8'd4 : (p_typ == 8'd3) ? 8'd17 : 8'd0;
            plv     <= (p_typ == 8'd3) ?
                       {cmds[15:0], c_crc, c_short, c_long, c_rep, c_ooo, c_err, fcount, 7'd0, tel_on} :
                       {rv, 104'd0};
        end else if (rb_busy && {3'd0, rb_idx} < rb_end && rb_idx >= 5'd5) begin
            plv <= plv << 8;
        end
    end

    always_ff @(posedge clk) begin
        if (rst) begin
            rb_busy <= 1'b0;
            rb_idx  <= 5'd0;
            rb_ci   <= 2'd0;
            rb_crc  <= CRC_INIT;
            rlen    <= 8'd0;
        end else if (ev) begin
            rlen    <= 8'd0;
            rb_busy <= d_reply;
            rb_idx  <= 5'd0;
            rb_ci   <= 2'd0;
            rb_crc  <= CRC_INIT;
        end else if (rb_busy) begin
            if ({3'd0, rb_idx} < rb_end) begin
                rb_crc <= crc8(rb_crc, rb_byte);
                rb_idx <= rb_idx + 5'd1;
            end else if (rb_ci != 2'd3) begin
                rb_ci  <= rb_ci + 2'd1;
                rb_idx <= rb_idx + 5'd1;
            end else begin
                rb_busy <= 1'b0;
                rlen    <= rb_end + 8'd4;
            end
        end
    end

    // ------------------------------------------------------------ registers, counters, telemetry
    always_ff @(posedge clk) begin
        if (rst) begin
            scratch[0] <= 32'd0; scratch[1] <= 32'd0; scratch[2] <= 32'd0;
            cmds <= 32'd0; refused <= 32'd0; ticks <= 32'd0;
            c_crc <= 16'd0; c_short <= 16'd0; c_long <= 16'd0;
            c_rep <= 16'd0; c_ooo <= 16'd0; c_err <= 16'd0;
            last_seq <= 16'd0; have_last <= 1'b0;
            period <= 16'(PERIOD_RESET);
            tel_on <= 1'b0; tcnt <= 16'd0; held <= 1'b0;
            fseq <= 16'd0; fcount <= 16'd0;
            pending <= 16'd0;
        end else begin
            pending <= pending - {15'd0, tick_ev} + (tick_wr ? {8'd0, win_wdata[7:0]} : 16'd0);
            if (tick_ev) ticks <= ticks_n;
            if (tick_ev && tel_on) tcnt <= due ? 16'd0 : tcnt + 16'd1;
            if (take_wr) held <= 1'b0;
            if (due_cap) begin
                held   <= 1'b1;
                fseq   <= fseq + 16'd1;
                fcount <= fcount + 16'd1;
            end
            if (ev) begin
                if (d_short) c_short <= c_short + 16'd1;
                if (d_long)  c_long  <= c_long  + 16'd1;
                if (d_crc)   c_crc   <= c_crc   + 16'd1;
                if (d_rep)   c_rep   <= c_rep   + 16'd1;
                if (d_ooo)   c_ooo   <= c_ooo   + 16'd1;
                if (d_err)   c_err   <= c_err   + 16'd1;
                if (d_short || d_long || d_crc || d_rep || d_ooo || d_err) refused <= refused + 32'd1;
                if (d_ok) cmds <= cmds + 32'd1;
                if (d_accept) begin
                    last_seq  <= p_seq;
                    have_last <= 1'b1;
                end
                if (d_ok && p_typ == 8'd2)
                    scratch[p_reg[1:0] - 2'd1] <= {pbuf[6], pbuf[7], pbuf[8], pbuf[9]};
                if (d_ok && p_typ == 8'd4) begin
                    if (p_reg != 16'd0) period <= (p_reg < 16'(PERIOD_MIN)) ? 16'(PERIOD_MIN) : p_reg;
                    tel_on <= 1'b1;
                    tcnt   <= 16'd0;
                end
                if (d_ok && p_typ == 8'd5) begin
                    tel_on <= 1'b0;
                    held   <= 1'b0;
                end
            end
        end
    end

    // ------------------------------------------------------------ telemetry frame builder
    wire [7:0] tb_byte = tbuf[tb_idx];
    wire [31:0] tb_fin = ~tb_crc;
    wire [1:0]  tb_k   = tb_idx[1:0] - 2'd1;   // idx 13..16 -> 0..3 (13 = 5'b01101)
    logic [7:0] tb_cbyte;
    always_comb begin
        case (tb_k)
            2'd0:    tb_cbyte = tb_fin[7:0];
            2'd1:    tb_cbyte = tb_fin[15:8];
            2'd2:    tb_cbyte = tb_fin[23:16];
            default: tb_cbyte = tb_fin[31:24];
        endcase
    end

    always_ff @(posedge clk) begin
        if (due_cap) begin
            tbuf[0]  <= 8'hC0;
            tbuf[1]  <= 8'h00;
            tbuf[2]  <= fseq[15:8];
            tbuf[3]  <= fseq[7:0];
            tbuf[4]  <= 8'd8;
            tbuf[5]  <= ticks_n[31:24];
            tbuf[6]  <= ticks_n[23:16];
            tbuf[7]  <= ticks_n[15:8];
            tbuf[8]  <= ticks_n[7:0];
            tbuf[9]  <= cmds[15:8];
            tbuf[10] <= cmds[7:0];
            tbuf[11] <= refused[15:8];
            tbuf[12] <= refused[7:0];
        end else if (tb_busy && tb_idx >= 5'd13 && tb_idx < 5'd17) begin
            tbuf[tb_idx] <= tb_cbyte;
        end
    end

    always_ff @(posedge clk) begin
        if (rst) begin
            tb_busy <= 1'b0;
            tb_idx  <= 5'd0;
            tb_crc  <= CRC_INIT;
        end else if (due_cap) begin
            tb_busy <= 1'b1;
            tb_idx  <= 5'd0;
            tb_crc  <= CRC_INIT;
        end else if (tb_busy) begin
            if (!held) begin
                tb_busy <= 1'b0;
            end else if (tb_idx < 5'd13) begin
                tb_crc <= crc8(tb_crc, tb_byte);
                tb_idx <= tb_idx + 5'd1;
            end else if (tb_idx < 5'd16) begin
                tb_idx <= tb_idx + 5'd1;
            end else begin
                tb_busy <= 1'b0;
            end
        end
    end

    // ------------------------------------------------------------ window registers
    logic [6:0] ridx, tidx;
    wire  [7:0] tlen = held ? 8'd17 : 8'd0;
    wire        busy = rb_busy | tb_busy | ev;

    logic [31:0] rword, tword;
    logic [8:0]  rbi, tbi;
    always_comb begin
        rbi = {ridx, 2'b00};
        tbi = {tidx, 2'b00};
        rword = 32'd0;
        tword = 32'd0;
        for (int k = 0; k < 4; k++) begin
            if (({1'b0, rbi} + 10'(k)) < {2'b00, rlen})
                rword[31 - 8*k -: 8] = rbuf[5'(rbi + 9'(k))];
            if (({1'b0, tbi} + 10'(k)) < {2'b00, tlen})
                tword[31 - 8*k -: 8] = tbuf[5'(tbi + 9'(k))];
        end
    end

    always_ff @(posedge clk) begin
        if (rst) begin
            ridx <= 7'd0;
            tidx <= 7'd0;
            win_rdata <= 32'd0;
        end else begin
            if (win_wr && win_addr == 7'd3) ridx <= win_wdata[6:0];
            if (win_wr && win_addr == 7'd6) tidx <= win_wdata[6:0];
            if (win_rd) begin
                case (win_addr)
                    7'd2:    win_rdata <= {24'd0, rlen};
                    7'd3:    win_rdata <= {25'd0, ridx};
                    7'd4:    win_rdata <= rword;
                    7'd5:    win_rdata <= {24'd0, tlen};
                    7'd6:    win_rdata <= {25'd0, tidx};
                    7'd7:    win_rdata <= tword;
                    7'd9:    win_rdata <= {30'd0, busy, tel_on};
                    default: win_rdata <= 32'd0;
                endcase
            end
        end
    end

    assign led = cmds[15:0];
endmodule
