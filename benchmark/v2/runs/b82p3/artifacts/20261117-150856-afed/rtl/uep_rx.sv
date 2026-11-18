// uep_rx: packet intake, CRC-32 check, judging, sequence rule, counters, register file, reply buffer.
module uep_rx #(
    parameter int          TIMEOUT_CYCLES = 100000,
    parameter logic [31:0] ID_WORD        = 32'h55445031
) (
    input  logic        clk,
    input  logic        rst,
    // window
    input  logic        win_wr,
    input  logic [6:0]  win_addr,
    input  logic [31:0] win_wdata,
    output logic [6:0]  ridx,
    output logic [7:0]  rlen,
    output logic [31:0] rword,
    output logic        busy,
    // counts
    output logic [15:0] cmds,
    output logic [15:0] refused,
    // telemetry interface
    output logic        tel_start,
    output logic        tel_stop,
    output logic [15:0] tel_period,
    input  logic [15:0] period,
    input  logic [31:0] ticks,
    input  logic        tel_on,
    input  logic [15:0] fcount
);
    localparam int TW = $clog2(TIMEOUT_CYCLES + 1);
    localparam logic [TW-1:0] TMAX = TW'(TIMEOUT_CYCLES - 1);
    localparam logic [31:0] RESIDUE = 32'hDEBB20E3;

    typedef enum logic [2:0] {S_IDLE, S_JUDGE, S_CRC, S_DECIDE, S_RCRC} state_t;
    state_t state;

    logic [7:0]  pbuf [0:15];
    logic [7:0]  rbuf [0:31];
    logic [31:0] rcrc;
    logic [7:0]  n;
    logic [TW-1:0] idle;
    logic [4:0]  ci;
    logic [31:0] crc;
    logic [15:0] cnt [0:6];
    logic [31:0] scratch [0:2];
    logic [15:0] last_seq;
    logic        last_valid;

    assign cmds    = cnt[0];
    assign busy    = (state != S_IDLE);

    wire in_wr   = win_wr && (win_addr == 7'd0);
    wire ridx_wr = win_wr && (win_addr == 7'd3);

    // ---- CRC engine
    logic [7:0]  crc_byte;
    logic [31:0] crc_nx;
    always_comb crc_byte = (state == S_RCRC) ? rbuf[ci] : pbuf[ci[3:0]];
    uep_crc_step u_crc (.crc(crc), .d(crc_byte), .nxt(crc_nx));

    // ---- judging (combinational view of the held packet)
    wire [7:0]  ty   = pbuf[0];
    wire [7:0]  ln   = pbuf[1];
    wire [15:0] sq   = {pbuf[2], pbuf[3]};
    wire [15:0] regn = {pbuf[4], pbuf[5]};
    wire [15:0] dseq = sq - last_seq;
    wire crc_good = (crc == RESIDUE);
    wire type_ok  = (ty >= 8'd1) && (ty <= 8'd5);
    logic [7:0] need;
    always_comb begin
        case (ty)
            8'd1:    need = 8'd2;
            8'd2:    need = 8'd6;
            8'd4:    need = 8'd2;
            default: need = 8'd0;
        endcase
    end
    wire len_ok   = (ln == need);
    wire seq_ok   = !last_valid || ((dseq != 16'd0) && !dseq[15]);
    wire seq_rep  = last_valid && (dseq == 16'd0);
    wire has_reg  = (ty == 8'd1) || (ty == 8'd2);
    wire reg_bad  = |regn[15:3];
    wire wr_ro    = (ty == 8'd2) && ((regn[2:0] == 3'd0) || regn[2]);

    logic [2:0] status;
    always_comb begin
        if (!type_ok)                 status = 3'd1;
        else if (!len_ok)             status = 3'd2;
        else if (!seq_ok)             status = 3'd4;
        else if (has_reg && reg_bad)  status = 3'd3;
        else if (wr_ro)               status = 3'd5;
        else                          status = 3'd0;
    end
    wire [2:0] kind = (status == 3'd4) ? (seq_rep ? 3'd4 : 3'd5) : 3'd6;

    logic [31:0] regval;
    always_comb begin
        case (regn[2:0])
            3'd0:    regval = ID_WORD;
            3'd1:    regval = scratch[0];
            3'd2:    regval = scratch[1];
            3'd3:    regval = scratch[2];
            3'd4:    regval = {16'h0, cnt[0]};
            3'd5:    regval = {16'h0, refused};
            3'd6:    regval = {16'h0, period};
            default: regval = ticks;
        endcase
    end

    // ---- control
    wire timeout_hit = (n != 8'd0) && (idle >= TMAX);

    always_ff @(posedge clk) begin
        tel_start <= 1'b0;
        tel_stop  <= 1'b0;
        if (rst) begin
            state      <= S_IDLE;
            n          <= 8'd0;
            idle       <= '0;
            rlen       <= 8'd0;
            ridx       <= 7'd0;
            refused    <= 16'd0;
            last_seq   <= 16'd0;
            last_valid <= 1'b0;
            tel_period <= 16'd0;
            for (int i = 0; i < 7; i++) cnt[i] <= 16'd0;
            for (int i = 0; i < 3; i++) scratch[i] <= 32'd0;
        end else begin
            if (ridx_wr) ridx <= win_wdata[6:0];
            case (state)
                S_IDLE: begin
                    if (in_wr) begin
                        n    <= (n == 8'hFF) ? 8'hFF : n + 8'd1;
                        idle <= '0;
                        if (win_wdata[8]) state <= S_JUDGE;
                    end else if (n != 8'd0) begin
                        idle <= idle + 1'b1;
                        if (timeout_hit) begin
                            n       <= 8'd0;
                            idle    <= '0;
                            rlen    <= 8'd0;
                            cnt[2]  <= cnt[2] + 16'd1;
                            refused <= refused + 16'd1;
                        end
                    end
                end
                S_JUDGE: begin
                    rlen <= 8'd0;
                    if (n < 8'd4) begin
                        cnt[2] <= cnt[2] + 16'd1; refused <= refused + 16'd1;
                        n <= 8'd0; state <= S_IDLE;
                    end else if (ln > 8'd8 || n > ln + 8'd8) begin
                        cnt[3] <= cnt[3] + 16'd1; refused <= refused + 16'd1;
                        n <= 8'd0; state <= S_IDLE;
                    end else if (n < ln + 8'd8) begin
                        cnt[2] <= cnt[2] + 16'd1; refused <= refused + 16'd1;
                        n <= 8'd0; state <= S_IDLE;
                    end else begin
                        state <= S_CRC;
                    end
                end
                S_CRC: begin
                    if (ci == n[4:0] - 5'd1) state <= S_DECIDE;
                end
                S_DECIDE: begin
                    if (!crc_good) begin
                        cnt[1] <= cnt[1] + 16'd1; refused <= refused + 16'd1;
                        n <= 8'd0; state <= S_IDLE;
                    end else begin
                        if (type_ok && len_ok && seq_ok) begin
                            last_seq   <= sq;
                            last_valid <= 1'b1;
                        end
                        if (status == 3'd0) begin
                            cnt[0] <= cnt[0] + 16'd1;
                            if (ty == 8'd2) scratch[regn[1:0] - 2'd1] <= {pbuf[6], pbuf[7], pbuf[8], pbuf[9]};
                            tel_start  <= (ty == 8'd4);
                            tel_stop   <= (ty == 8'd5);
                            tel_period <= regn;
                        end else begin
                            cnt[kind] <= cnt[kind] + 16'd1;
                            refused   <= refused + 16'd1;
                        end
                        state <= S_RCRC;
                    end
                end
                S_RCRC: begin
                    if (ci == rbuf[4][4:0] + 5'd4) begin
                        rlen  <= rbuf[4] + 8'd9;
                        n     <= 8'd0;
                        state <= S_IDLE;
                    end
                end
                default: state <= S_IDLE;
            endcase
        end
    end

    // ---- datapath (no reset)
    always_ff @(posedge clk) begin
        if (state == S_IDLE && in_wr && n < 8'd16) pbuf[n[3:0]] <= win_wdata[7:0];
        case (state)
            S_JUDGE, S_DECIDE: begin
                crc <= 32'hFFFFFFFF;
                ci  <= 5'd0;
            end
            S_CRC, S_RCRC: begin
                crc <= crc_nx;
                ci  <= ci + 5'd1;
            end
            default: ;
        endcase
        if (state == S_RCRC && ci == rbuf[4][4:0] + 5'd4) rcrc <= ~crc_nx;
        if (state == S_DECIDE && crc_good) begin
            rbuf[0] <= ty | 8'h80;
            rbuf[1] <= {5'd0, status};
            rbuf[2] <= pbuf[2];
            rbuf[3] <= pbuf[3];
            rbuf[4] <= 8'd0;
            if (status == 3'd0) begin
                if (ty == 8'd1) begin
                    rbuf[4] <= 8'd4;
                    rbuf[5] <= regval[31:24];
                    rbuf[6] <= regval[23:16];
                    rbuf[7] <= regval[15:8];
                    rbuf[8] <= regval[7:0];
                end else if (ty == 8'd3) begin
                    rbuf[4] <= 8'd17;
                    for (int i = 0; i < 7; i++) begin
                        rbuf[5 + 2 * i] <= cnt[i][15:8];
                        rbuf[6 + 2 * i] <= cnt[i][7:0];
                    end
                    rbuf[19] <= fcount[15:8];
                    rbuf[20] <= fcount[7:0];
                    rbuf[21] <= {7'd0, tel_on};
                end
            end
        end
    end

    // ---- reply word read-back
    always_comb begin
        logic [7:0] rb [0:3];
        logic [8:0] jj;
        logic [1:0] m;
        for (int k = 0; k < 4; k++) begin
            jj = {ridx, 2'b00} + 9'(k);
            m  = jj[1:0] - rlen[1:0];
            rb[k] = 8'h00;
            if (rlen != 8'd0) begin
                if (jj + 9'd4 < {1'b0, rlen})  rb[k] = rbuf[jj[4:0]];
                else if (jj < {1'b0, rlen})    rb[k] = rcrc[{m, 3'b000} +: 8];
            end
        end
        rword = {rb[0], rb[1], rb[2], rb[3]};
    end

    /* verilator lint_off UNUSEDSIGNAL */
    wire unused_ok = &{1'b0, win_wdata[31:9], win_addr[6:0]};
    /* verilator lint_on UNUSEDSIGNAL */
endmodule
