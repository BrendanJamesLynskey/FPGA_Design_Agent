// udp_core.sv: UDP-style command and telemetry endpoint behind the shell window.
// Packet bytes come in through IN, are checked and executed in at most ~45 clocks after the end-flag byte,
// the reply is left in a 32-byte buffer read back through RIDX/RWORD. Telemetry has its own tick generator,
// one held frame buffer and its own CRC engine. One clock domain, synchronous active-high reset.
// Datapath arrays (packet, reply and frame buffers, CRC, payload snapshot) are not reset.
// win_wdata is only the low 9 bits: IN uses [8:0], every other register [7:0].

module udp_core #(
    parameter logic [31:0] ID_WORD        = 32'h5544_5031,
    parameter logic [15:0] DEFAULT_PERIOD = 16'd100,
    parameter logic [15:0] MIN_PERIOD     = 16'd4
) (
    input  logic        clk,
    input  logic        rst,
    input  logic [6:0]  win_addr,
    input  logic        win_wr,
    input  logic [8:0]  win_wdata,
    output logic [31:0] win_rdata,
    output logic [15:0] led
);
    localparam logic [31:0] CRC_RESIDUE = 32'hDEBB_20E3;   // register value after the data and its CRC bytes

    typedef enum logic [2:0] {S_IDLE, S_CLASS, S_CRC, S_DECIDE, S_BUILD, S_TAIL} state_t;
    state_t state;

    function automatic logic [31:0] crc8(input logic [31:0] c, input logic [7:0] d);
        logic [31:0] r;
        r = c ^ {24'b0, d};
        for (int i = 0; i < 8; i++) r = r[0] ? ((r >> 1) ^ 32'hEDB8_8320) : (r >> 1);
        return r;
    endfunction

    // ---------------------------------------------------------------- state
    logic [7:0]   rx [16];
    logic [4:0]   rx_n;
    logic         busy;
    logic [4:0]   idx;
    logic [31:0]  crc;
    logic [7:0]   rep [32];
    logic [4:0]   rlen;
    logic [4:0]   tot;
    logic [4:0]   plen;
    logic [2:0]   stcode;
    logic [135:0] plb;
    logic [15:0]  cnt [7];
    logic [15:0]  refused;
    logic [15:0]  last_seq;
    logic         have_seq;
    logic [31:0]  scratch [3];
    logic [15:0]  period, tel_cnt;
    logic         tel_on;
    logic [31:0]  ticks;
    logic [7:0]   pend;
    logic         held, tf_run;
    logic [4:0]   tf_idx;
    logic [31:0]  tcrc;
    logic [7:0]   tf [17];
    logic [15:0]  fseq, fcount;
    logic [6:0]   ridx, tidx;

    assign led = cnt[0];

    // ---------------------------------------------------------------- window decode
    wire a_in   = win_wr && (win_addr == 7'd0);
    wire a_tick = win_wr && (win_addr == 7'd1);
    wire a_ridx = win_wr && (win_addr == 7'd3);
    wire a_tidx = win_wr && (win_addr == 7'd6);
    wire a_take = win_wr && (win_addr == 7'd8);

    // ---------------------------------------------------------------- length classification (state S_CLASS)
    // too long needs the length byte (two bytes seen); a packet under four bytes is otherwise too short
    wire [8:0] lim      = 9'd8 + {1'b0, rx[1]};
    wire       p_long   = (rx_n >= 5'd2) && ((rx[1] > 8'd8) || ({4'b0, rx_n} > lim));
    wire       p_short  = (rx_n < 5'd8) || ({4'b0, rx_n} < lim);

    // ---------------------------------------------------------------- command decision (state S_DECIDE)
    logic [7:0]   typ, ln, need;
    logic [15:0]  pseq, dseq, reg16;
    logic         known, seq_ok, consume, do_wr, do_start, do_stop, crc_ok;
    logic [2:0]   stc, cls;
    logic [4:0]   plen_c;
    logic [135:0] plb_c;
    logic [31:0]  regval;

    always_comb begin
        typ   = rx[0];
        ln    = rx[1];
        pseq  = {rx[2], rx[3]};
        reg16 = {rx[4], rx[5]};
        dseq  = pseq - last_seq;
        crc_ok = (crc == CRC_RESIDUE);
        case (typ)
            8'd1:    need = 8'd2;
            8'd2:    need = 8'd6;
            8'd4:    need = 8'd2;
            default: need = 8'd0;
        endcase
        known  = (typ >= 8'd1) && (typ <= 8'd5);
        seq_ok = !have_seq || ((dseq != 16'd0) && !dseq[15]);
        case (reg16[2:0])
            3'd0:    regval = ID_WORD;
            3'd1:    regval = scratch[0];
            3'd2:    regval = scratch[1];
            3'd3:    regval = scratch[2];
            3'd4:    regval = {16'b0, cnt[0]};
            3'd5:    regval = {16'b0, refused};
            3'd6:    regval = {16'b0, period};
            default: regval = ticks;
        endcase
        stc      = 3'd0;
        plen_c   = 5'd0;
        plb_c    = '0;
        consume  = 1'b0;
        do_wr    = 1'b0;
        do_start = 1'b0;
        do_stop  = 1'b0;
        if (!known)            stc = 3'd1;
        else if (ln != need)   stc = 3'd2;
        else if (!seq_ok)      stc = 3'd4;
        else begin
            consume = 1'b1;
            case (typ)
                8'd1: begin
                    if (reg16 >= 16'd8) stc = 3'd3;
                    else begin
                        plen_c = 5'd4;
                        plb_c[135:104] = regval;
                    end
                end
                8'd2: begin
                    if (reg16 >= 16'd8)                         stc = 3'd3;
                    else if (reg16 == 16'd0 || reg16 >= 16'd4)  stc = 3'd5;
                    else                                        do_wr = 1'b1;
                end
                8'd3: begin
                    plen_c = 5'd17;
                    plb_c  = {cnt[0], cnt[1], cnt[2], cnt[3], cnt[4], cnt[5], cnt[6], fcount, 7'b0, tel_on};
                end
                8'd4:    do_start = 1'b1;
                default: do_stop  = 1'b1;
            endcase
        end
        if (stc == 3'd4)      cls = (dseq == 16'd0) ? 3'd4 : 3'd5;
        else                  cls = 3'd6;
    end

    // ---------------------------------------------------------------- reply byte stream (state S_BUILD)
    logic [7:0] rbyte;
    always_comb begin
        case (idx)
            5'd0:    rbyte = {1'b1, rx[0][6:0]};
            5'd1:    rbyte = {5'b0, stcode};
            5'd2:    rbyte = rx[2];
            5'd3:    rbyte = rx[3];
            5'd4:    rbyte = {3'b0, plen};
            default: rbyte = plb[8 * (21 - int'(idx)) +: 8];   // payload byte idx-5, first byte on top
        endcase
    end

    // ---------------------------------------------------------------- read-back words (bytes 4i..4i+3, zero past the end)
    logic [7:0]  rw [4];
    logic [7:0]  tw [4];
    logic [4:0]  ri, ti;
    always_comb begin
        for (int j = 0; j < 4; j++) begin
            ri    = {ridx[2:0], 2'b00} + 5'(j);
            ti    = {tidx[2:0], 2'b00} + 5'(j);
            rw[j] = ((ridx[6:3] == 4'd0) && (ri < rlen))                ? rep[ri] : 8'h00;
            tw[j] = (held && (tidx[6:3] == 4'd0) && (ti < 5'd17))       ? tf[ti]  : 8'h00;
        end
    end

    // ---------------------------------------------------------------- telemetry due
    wire tick = (pend != 8'd0);
    wire due  = tick && tel_on && (({1'b0, tel_cnt} + 17'd1) >= {1'b0, period});
    wire held_eff = held && !a_take;

    // uptime including the tick that made the frame due, as bytes high first
    function automatic logic [7:0] tbyte(input logic [31:0] v, input int k);
        return v[8 * k +: 8];
    endfunction

    always_ff @(posedge clk) begin
        // read data, due one cycle after win_rd (the address is stable, so register it every clock)
        case (win_addr)
            7'd2:    win_rdata <= {27'b0, rlen};
            7'd3:    win_rdata <= {25'b0, ridx};
            7'd4:    win_rdata <= {rw[0], rw[1], rw[2], rw[3]};
            7'd5:    win_rdata <= held ? 32'd17 : 32'd0;
            7'd6:    win_rdata <= {25'b0, tidx};
            7'd7:    win_rdata <= {tw[0], tw[1], tw[2], tw[3]};
            7'd9:    win_rdata <= {30'b0, busy, tel_on};
            default: win_rdata <= 32'd0;
        endcase

        // ---- datapath, not reset
        if (a_in && state == S_IDLE && rx_n < 5'd16) rx[rx_n[3:0]] <= win_wdata[7:0];
        case (state)
            S_CRC:   crc <= crc8(crc, rx[idx[3:0]]);
            S_BUILD: begin
                crc      <= crc8(crc, rbyte);
                rep[idx] <= rbyte;
            end
            default: ;
        endcase
        if (state == S_TAIL) begin
            rep[tot]        <= ~crc[7:0];
            rep[tot + 5'd1] <= ~crc[15:8];
            rep[tot + 5'd2] <= ~crc[23:16];
            rep[tot + 5'd3] <= ~crc[31:24];
        end
        if (tf_run && tf_idx != 5'd13) tcrc <= crc8(tcrc, tf[tf_idx]);
        if (tf_run && tf_idx == 5'd13) begin
            tf[13] <= ~tcrc[7:0];
            tf[14] <= ~tcrc[15:8];
            tf[15] <= ~tcrc[23:16];
            tf[16] <= ~tcrc[31:24];
        end
        if (due && !held_eff) begin
            tf[0]  <= 8'hC0;
            tf[1]  <= 8'h00;
            tf[2]  <= fseq[15:8];
            tf[3]  <= fseq[7:0];
            tf[4]  <= 8'd8;
            tf[5]  <= tbyte(ticks + 32'd1, 3);
            tf[6]  <= tbyte(ticks + 32'd1, 2);
            tf[7]  <= tbyte(ticks + 32'd1, 1);
            tf[8]  <= tbyte(ticks + 32'd1, 0);
            tf[9]  <= cnt[0][15:8];
            tf[10] <= cnt[0][7:0];
            tf[11] <= refused[15:8];
            tf[12] <= refused[7:0];
            tcrc   <= 32'hFFFF_FFFF;
        end
        if (state == S_DECIDE) plb <= plb_c;

        // ---- control, reset
        if (rst) begin
            state    <= S_IDLE;
            rx_n     <= 5'd0;
            busy     <= 1'b0;
            idx      <= 5'd0;
            rlen     <= 5'd0;
            tot      <= 5'd0;
            plen     <= 5'd0;
            stcode   <= 3'd0;
            for (int i = 0; i < 7; i++) cnt[i] <= 16'd0;
            refused  <= 16'd0;
            last_seq <= 16'd0;
            have_seq <= 1'b0;
            for (int i = 0; i < 3; i++) scratch[i] <= 32'd0;
            period   <= DEFAULT_PERIOD;
            tel_cnt  <= 16'd0;
            tel_on   <= 1'b0;
            ticks    <= 32'd0;
            pend     <= 8'd0;
            held     <= 1'b0;
            tf_run   <= 1'b0;
            tf_idx   <= 5'd0;
            fseq     <= 16'd0;
            fcount   <= 16'd0;
            ridx     <= 7'd0;
            tidx     <= 7'd0;
        end else begin
            // ticks and telemetry period count
            if (a_tick)      pend <= win_wdata[7:0];
            else if (tick)   pend <= pend - 8'd1;
            if (tick) begin
                ticks <= ticks + 32'd1;
                if (tel_on) tel_cnt <= due ? 16'd0 : (tel_cnt + 16'd1);
            end
            if (a_ridx) ridx <= win_wdata[6:0];
            if (a_tidx) tidx <= win_wdata[6:0];

            // held frame CRC job
            if (tf_run) begin
                if (tf_idx == 5'd13) tf_run <= 1'b0;
                else                 tf_idx <= tf_idx + 5'd1;
            end
            if (a_take) begin
                held   <= 1'b0;
                tf_run <= 1'b0;
            end
            if (due && !held_eff) begin
                held   <= 1'b1;
                tf_run <= 1'b1;
                tf_idx <= 5'd0;
                fseq   <= fseq + 16'd1;
                fcount <= fcount + 16'd1;
            end

            // packet receive and process
            case (state)
                S_IDLE: begin
                    if (a_in) begin
                        busy <= 1'b1;
                        if (rx_n != 5'd31) rx_n <= rx_n + 5'd1;
                        if (win_wdata[8]) begin
                            state <= S_CLASS;
                            rlen  <= 5'd0;
                        end
                    end
                end
                S_CLASS: begin
                    if (p_long) begin
                        cnt[3]  <= cnt[3] + 16'd1;
                        refused <= refused + 16'd1;
                        state   <= S_IDLE;
                        busy    <= 1'b0;
                        rx_n    <= 5'd0;
                    end else if (p_short) begin
                        cnt[2]  <= cnt[2] + 16'd1;
                        refused <= refused + 16'd1;
                        state   <= S_IDLE;
                        busy    <= 1'b0;
                        rx_n    <= 5'd0;
                    end else begin
                        crc   <= 32'hFFFF_FFFF;
                        idx   <= 5'd0;
                        state <= S_CRC;
                    end
                end
                S_CRC: begin
                    if (idx == rx_n - 5'd1) state <= S_DECIDE;
                    else                    idx <= idx + 5'd1;
                end
                S_DECIDE: begin
                    if (!crc_ok) begin
                        cnt[1]  <= cnt[1] + 16'd1;
                        refused <= refused + 16'd1;
                        state   <= S_IDLE;
                        busy    <= 1'b0;
                        rx_n    <= 5'd0;
                    end else begin
                        stcode <= stc;
                        plen   <= plen_c;
                        tot    <= 5'd5 + plen_c;
                        crc    <= 32'hFFFF_FFFF;
                        idx    <= 5'd0;
                        state  <= S_BUILD;
                        if (consume) begin
                            last_seq <= pseq;
                            have_seq <= 1'b1;
                        end
                        if (stc == 3'd0) cnt[0] <= cnt[0] + 16'd1;
                        else begin
                            cnt[cls] <= cnt[cls] + 16'd1;
                            refused  <= refused + 16'd1;
                        end
                        if (do_wr) scratch[reg16[1:0] - 2'd1] <= {rx[6], rx[7], rx[8], rx[9]};
                        if (do_start) begin
                            if (reg16 != 16'd0) period <= (reg16 < MIN_PERIOD) ? MIN_PERIOD : reg16;
                            tel_on  <= 1'b1;
                            tel_cnt <= 16'd0;
                        end
                        if (do_stop) begin
                            tel_on <= 1'b0;
                            held   <= 1'b0;
                            tf_run <= 1'b0;
                        end
                    end
                end
                S_BUILD: begin
                    if (idx == tot - 5'd1) state <= S_TAIL;
                    else                   idx <= idx + 5'd1;
                end
                default: begin   // S_TAIL
                    rlen  <= tot + 5'd4;
                    state <= S_IDLE;
                    busy  <= 1'b0;
                    rx_n  <= 5'd0;
                end
            endcase
        end
    end
endmodule
