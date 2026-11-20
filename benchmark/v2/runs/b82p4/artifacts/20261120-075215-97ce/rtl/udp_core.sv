// UDP command and telemetry endpoint core. One clock, synchronous active-high reset.
// Packet bytes arrive through the shell window; the CRC-32 is streamed over every byte
// (residue check), the packet decision is taken in one cycle after the end-flag byte, and the
// reply is then assembled and CRC'd bytewise in at most ~35 clocks.
module udp_core #(
    parameter logic [31:0] ID_WORD                = 32'h55445031,
    parameter logic [31:0] SCRATCH_RESET          = 32'h0,
    parameter int          TELEMETRY_PERIOD_RESET = 100,
    parameter int          TELEMETRY_PERIOD_MIN   = 4,
    parameter int          MAX_PAYLOAD            = 8
) (
    input  logic        clk,
    input  logic        rst,
    input  logic [6:0]  win_addr,
    input  logic        win_wr,
    input  logic        win_rd,
    input  logic [31:0] win_wdata,
    output logic [31:0] win_rdata,
    output logic [15:0] led
);
    localparam logic [31:0] CRC_RESIDUE = 32'hDEBB20E3;

    typedef enum logic [1:0] {R_IDLE, R_DECIDE, R_CRC, R_WR} rstate_t;
    typedef enum logic [1:0] {F_IDLE, F_CRC, F_WR} fstate_t;

    // ---- packet collector
    logic [7:0]  pkt [0:11];
    logic [7:0]  n;
    logic [31:0] rx_crc;
    logic        busy;
    logic        have_last;
    logic [15:0] last;

    // ---- registers and counters
    logic [31:0] scratch [0:2];
    logic [31:0] cmds, refused, ticks;
    logic [15:0] cnt [0:5];
    logic [15:0] period, tcount, fseq, fcount;
    logic        tel_on;
    logic [7:0]  pending;

    // ---- reply buffer
    logic [7:0]  rbuf [0:27];
    logic [4:0]  rlen, rtot, rpre, rix;
    logic [31:0] tx_crc;
    rstate_t     rstate;

    // ---- telemetry frame buffer
    logic [7:0]  fbuf [0:16];
    logic        fheld, fready;
    logic [4:0]  fix;
    logic [31:0] f_crc;
    fstate_t     fstate;

    logic [6:0]  ridx, tidx;

    // ---- CRC engines
    logic [31:0] rx_crc_n, tx_crc_n, f_crc_n;
    crc32_byte u_crc_rx (.crc_in(rx_crc), .data(win_wdata[7:0]), .crc_out(rx_crc_n));
    crc32_byte u_crc_tx (.crc_in(tx_crc), .data(rbuf[rix]),      .crc_out(tx_crc_n));
    crc32_byte u_crc_f  (.crc_in(f_crc),  .data(fbuf[fix]),      .crc_out(f_crc_n));

    // ---- packet decision (valid in R_DECIDE)
    logic [7:0]  typ, plen_f;
    logic [7:0]  len_f;
    logic [15:0] seq, regn, dseq;
    logic [8:0]  need;
    logic        too_long, too_short, bad_crc, type_ok, len_ok, seq_ok, is_rep, wr_ro;
    logic        o_reply, o_refuse, o_accept, o_ok;
    logic [2:0]  o_status, o_cnt;
    logic [31:0] rd_val;
    logic [4:0]  o_plen;

    assign typ  = pkt[0];
    assign len_f = pkt[1];
    assign seq  = {pkt[2], pkt[3]};
    assign regn = {pkt[4], pkt[5]};
    assign need = 9'd8 + {1'b0, len_f};
    assign dseq = seq - last;

    assign too_long  = (n >= 8'd2) && ((len_f > 8'(MAX_PAYLOAD)) || ({1'b0, n} > need));
    assign too_short = (n < 8'd4) || ({1'b0, n} < need);
    assign bad_crc   = (rx_crc != CRC_RESIDUE);
    assign type_ok   = (typ >= 8'd1) && (typ <= 8'd5);
    assign is_rep    = have_last && (dseq == 16'd0);
    assign seq_ok    = !have_last || ((dseq != 16'd0) && !dseq[15]);
    assign wr_ro     = (typ == 8'd2) && ((regn[2:0] == 3'd0) || (regn[2:0] >= 3'd4));

    always_comb begin
        plen_f = 8'd0;
        case (typ)
            8'd1:    plen_f = 8'd2;
            8'd2:    plen_f = 8'd6;
            8'd4:    plen_f = 8'd2;
            default: plen_f = 8'd0;
        endcase
        len_ok = (len_f == plen_f);
    end

    always_comb begin
        rd_val = 32'h0;
        case (regn[2:0])
            3'd0:    rd_val = ID_WORD;
            3'd1:    rd_val = scratch[0];
            3'd2:    rd_val = scratch[1];
            3'd3:    rd_val = scratch[2];
            3'd4:    rd_val = cmds;
            3'd5:    rd_val = refused;
            3'd6:    rd_val = {16'h0, period};
            default: rd_val = ticks;
        endcase
    end

    always_comb begin
        o_reply = 1'b0; o_refuse = 1'b0; o_accept = 1'b0; o_ok = 1'b0;
        o_status = 3'd0; o_cnt = 3'd0;
        if (too_long) begin
            o_refuse = 1'b1; o_cnt = 3'd2;
        end else if (too_short) begin
            o_refuse = 1'b1; o_cnt = 3'd1;
        end else if (bad_crc) begin
            o_refuse = 1'b1; o_cnt = 3'd0;
        end else if (!type_ok) begin
            o_refuse = 1'b1; o_reply = 1'b1; o_status = 3'd1; o_cnt = 3'd5;
        end else if (!len_ok) begin
            o_refuse = 1'b1; o_reply = 1'b1; o_status = 3'd2; o_cnt = 3'd5;
        end else if (!seq_ok) begin
            o_refuse = 1'b1; o_reply = 1'b1; o_status = 3'd4;
            o_cnt = is_rep ? 3'd3 : 3'd4;
        end else begin
            o_accept = 1'b1; o_reply = 1'b1;
            if (((typ == 8'd1) || (typ == 8'd2)) && (regn >= 16'd8)) begin
                o_refuse = 1'b1; o_status = 3'd3; o_cnt = 3'd5;
            end else if (wr_ro) begin
                o_refuse = 1'b1; o_status = 3'd5; o_cnt = 3'd5;
            end else begin
                o_ok = 1'b1;
            end
        end
        if (o_ok && (typ == 8'd1))      o_plen = 5'd4;
        else if (o_ok && (typ == 8'd3)) o_plen = 5'd17;
        else                            o_plen = 5'd0;
    end

    // ---- main sequential logic
    wire in_wr   = win_wr && (win_addr == 7'd0);
    wire tick_wr = win_wr && (win_addr == 7'd1);
    wire take_wr = win_wr && (win_addr == 7'd8);
    wire [15:0] tcount_n = tcount + 16'd1;
    wire        due      = ({1'b0, tcount_n} >= {1'b0, period});
    wire [31:0] ticks_n  = ticks + 32'd1;

    always_ff @(posedge clk) begin
        if (rst) begin
            n         <= 8'd0;
            rx_crc    <= 32'hFFFF_FFFF;
            busy      <= 1'b0;
            have_last <= 1'b0;
            for (int i = 0; i < 3; i++) scratch[i] <= SCRATCH_RESET;
            cmds      <= 32'd0;
            refused   <= 32'd0;
            ticks     <= 32'd0;
            for (int i = 0; i < 6; i++) cnt[i] <= 16'd0;
            period    <= 16'(TELEMETRY_PERIOD_RESET);
            tcount    <= 16'd0;
            fseq      <= 16'd0;
            fcount    <= 16'd0;
            tel_on    <= 1'b0;
            pending   <= 8'd0;
            rlen      <= 5'd0;
            rstate    <= R_IDLE;
            fstate    <= F_IDLE;
            fheld     <= 1'b0;
            fready    <= 1'b0;
            ridx      <= 7'd0;
            tidx      <= 7'd0;
        end else begin
            // window register writes
            if (win_wr && (win_addr == 7'd3)) ridx <= win_wdata[6:0];
            if (win_wr && (win_addr == 7'd6)) tidx <= win_wdata[6:0];

            // ---- packet bytes
            if (in_wr && (rstate == R_IDLE)) begin
                if (n < 8'd12) pkt[n[3:0]] <= win_wdata[7:0];
                if (n != 8'd255) n <= n + 8'd1;
                rx_crc <= rx_crc_n;
                busy   <= 1'b1;
                if (win_wdata[8]) rstate <= R_DECIDE;
            end

            // ---- reply builder
            case (rstate)
                R_DECIDE: begin
                    n      <= 8'd0;
                    rx_crc <= 32'hFFFF_FFFF;
                    rlen   <= 5'd0;
                    if (o_refuse) begin
                        cnt[o_cnt] <= cnt[o_cnt] + 16'd1;
                        refused    <= refused + 32'd1;
                    end
                    if (o_accept) begin
                        have_last <= 1'b1;
                        last      <= seq;
                    end
                    if (o_reply) begin
                        rbuf[0] <= typ | 8'h80;
                        rbuf[1] <= {5'b0, o_status};
                        rbuf[2] <= pkt[2];
                        rbuf[3] <= pkt[3];
                        rbuf[4] <= {3'b0, o_plen};
                        if (o_ok && (typ == 8'd1)) begin
                            rbuf[5] <= rd_val[31:24];
                            rbuf[6] <= rd_val[23:16];
                            rbuf[7] <= rd_val[15:8];
                            rbuf[8] <= rd_val[7:0];
                        end
                        if (o_ok && (typ == 8'd3)) begin
                            rbuf[5] <= cmds[15:8];
                            rbuf[6] <= cmds[7:0];
                            for (int i = 0; i < 6; i++) begin
                                rbuf[7 + 2 * i] <= cnt[i][15:8];
                                rbuf[8 + 2 * i] <= cnt[i][7:0];
                            end
                            rbuf[19] <= fcount[15:8];
                            rbuf[20] <= fcount[7:0];
                            rbuf[21] <= {7'b0, tel_on};
                        end
                        rpre   <= 5'd5 + o_plen;
                        rtot   <= 5'd9 + o_plen;
                        tx_crc <= 32'hFFFF_FFFF;
                        rix    <= 5'd0;
                        rstate <= R_CRC;
                    end else begin
                        busy   <= 1'b0;
                        rstate <= R_IDLE;
                    end
                    if (o_ok) begin
                        cmds <= cmds + 32'd1;
                        case (typ)
                            8'd2: begin
                                scratch[regn[1:0] - 2'd1] <= {pkt[6], pkt[7], pkt[8], pkt[9]};
                            end
                            8'd4: begin
                                if (regn != 16'd0)
                                    period <= (regn < 16'(TELEMETRY_PERIOD_MIN)) ?
                                              16'(TELEMETRY_PERIOD_MIN) : regn;
                                tel_on <= 1'b1;
                                tcount <= 16'd0;
                            end
                            8'd5: begin
                                tel_on <= 1'b0;
                                fheld  <= 1'b0;
                                fready <= 1'b0;
                                fstate <= F_IDLE;
                            end
                            default: ;
                        endcase
                    end
                end
                R_CRC: begin
                    tx_crc <= tx_crc_n;
                    rix    <= rix + 5'd1;
                    if (rix == rpre - 5'd1) rstate <= R_WR;
                end
                R_WR: begin
                    rbuf[rix] <= ~tx_crc[7:0];
                    tx_crc    <= {8'h00, tx_crc[31:8]};
                    rix       <= rix + 5'd1;
                    if (rix == rtot - 5'd1) begin
                        rlen   <= rtot;
                        busy   <= 1'b0;
                        rstate <= R_IDLE;
                    end
                end
                default: ;
            endcase

            // ---- frame builder
            case (fstate)
                F_CRC: begin
                    f_crc <= f_crc_n;
                    fix   <= fix + 5'd1;
                    if (fix == 5'd12) fstate <= F_WR;
                end
                F_WR: begin
                    fbuf[fix] <= ~f_crc[7:0];
                    f_crc     <= {8'h00, f_crc[31:8]};
                    fix       <= fix + 5'd1;
                    if (fix == 5'd16) begin
                        fready <= 1'b1;
                        fstate <= F_IDLE;
                    end
                end
                default: ;
            endcase

            // ---- tick generation and telemetry pacer
            if (pending != 8'd0) begin
                pending <= pending - 8'd1;
                ticks   <= ticks_n;
                if (tel_on) begin
                    if (due) begin
                        tcount <= 16'd0;
                        if (!fheld) begin
                            fbuf[0]  <= 8'hC0;
                            fbuf[1]  <= 8'h00;
                            fbuf[2]  <= fseq[15:8];
                            fbuf[3]  <= fseq[7:0];
                            fbuf[4]  <= 8'd8;
                            fbuf[5]  <= ticks_n[31:24];
                            fbuf[6]  <= ticks_n[23:16];
                            fbuf[7]  <= ticks_n[15:8];
                            fbuf[8]  <= ticks_n[7:0];
                            fbuf[9]  <= cmds[15:8];
                            fbuf[10] <= cmds[7:0];
                            fbuf[11] <= refused[15:8];
                            fbuf[12] <= refused[7:0];
                            f_crc    <= 32'hFFFF_FFFF;
                            fix      <= 5'd0;
                            fstate   <= F_CRC;
                            fheld    <= 1'b1;
                            fready   <= 1'b0;
                            fseq     <= fseq + 16'd1;
                            fcount   <= fcount + 16'd1;
                        end
                    end else begin
                        tcount <= tcount_n;
                    end
                end
            end
            if (tick_wr) pending <= win_wdata[7:0];

            // ---- take register releases the held frame
            if (take_wr) begin
                fheld  <= 1'b0;
                fready <= 1'b0;
                fstate <= F_IDLE;
            end
        end
    end

    // ---- window read mux (registered: data valid the cycle after win_rd)
    logic [31:0] rword, tword;
    logic [8:0]  rbi, tbi;
    always_comb begin
        rword = 32'h0;
        tword = 32'h0;
        for (int k = 0; k < 4; k++) begin
            rbi = {ridx, 2'b00} + 9'(k);
            tbi = {tidx, 2'b00} + 9'(k);
            rword = {rword[23:0], (rbi < {4'b0, rlen}) ? rbuf[rbi[4:0]] : 8'h00};
            tword = {tword[23:0], (fready && (tbi < 9'd17)) ? fbuf[tbi[4:0]] : 8'h00};
        end
    end

    always_ff @(posedge clk) begin
        if (rst) begin
            win_rdata <= 32'h0;
        end else begin
            case (win_addr)
                7'd2:    win_rdata <= {27'h0, rlen};
                7'd3:    win_rdata <= {25'h0, ridx};
                7'd4:    win_rdata <= rword;
                7'd5:    win_rdata <= fready ? 32'd17 : 32'd0;
                7'd6:    win_rdata <= {25'h0, tidx};
                7'd7:    win_rdata <= tword;
                7'd9:    win_rdata <= {30'h0, busy, tel_on};
                default: win_rdata <= 32'h0;
            endcase
        end
    end

    assign led = cmds[15:0];

    /* verilator lint_off UNUSEDSIGNAL */
    wire unused_ok = &{1'b0, win_rd, win_wdata[31:9]};
    /* verilator lint_on UNUSEDSIGNAL */
endmodule
