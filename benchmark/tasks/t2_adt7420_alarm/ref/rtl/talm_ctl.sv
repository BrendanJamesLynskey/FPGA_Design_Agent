// talm_ctl.sv: ADT7420 alarm monitor. Configure: CONFIG = 0x90 (16-bit,
// comparator, INT active low), T_HIGH, T_LOW. Then a reading every
// PERIOD_CYCLES: pointer 0x00, repeated START, two bytes. MAX/MIN/SAMPLES.
module talm_ctl #(
    parameter int QUARTER       = 250,
    parameter int PERIOD_CYCLES = 25_000_000
) (
    input  logic        clk,
    input  logic        rst,
    input  logic        scl_in,
    input  logic        sda_in,
    output logic        scl_oe,
    output logic        sda_oe,
    input  logic        alarm,          // synchronised, active high
    input  logic [6:0]  win_addr,
    input  logic        win_wr,
    input  logic        win_rd,
    input  logic [31:0] win_wdata,
    output logic [31:0] win_rdata
);
    localparam logic [2:0] S = 3'd1, W = 3'd2, R = 3'd3, P = 3'd4;
    localparam logic [7:0] AW = 8'h96, AR = 8'h97, CONFIG_VAL = 8'h90;
    localparam int PW = $clog2(PERIOD_CYCLES + 1);

    typedef enum logic [2:0] {IDLE, ISSUE, WAIT1, WAIT, ABORT, ABORT_W} st_t;
    st_t st;

    logic        go, cbusy, cnack, configured, valid, nack, busy, reading;
    logic [2:0]  op;
    logic [7:0]  wd, rx, msb;
    logic        rn, last;
    logic [4:0]  step;
    logic [15:0] thigh, tlow, temp, tmax, tmin;
    logic [31:0] samples;
    logic [PW-1:0] pc;
    logic        pend;

    tm_i2c_core #(.QUARTER(QUARTER)) u_i2c (
        .clk(clk), .rst(rst), .go(go), .op(op), .wdata(wd), .rnack(rn), .scl_in(scl_in), .sda_in(sda_in),
        .scl_oe(scl_oe), .sda_oe(sda_oe), .busy(cbusy), .owned(), .nack(cnack), .rxdata(rx));

    // the two programs: configure (17 steps) and reading (8 steps)
    always_comb begin
        op = P; wd = 8'h00; rn = 1'b0; last = 1'b0;
        if (!reading) begin
            case (step)
                5'd0:  op = S;
                5'd1:  begin op = W; wd = AW; end
                5'd2:  begin op = W; wd = 8'h03; end
                5'd3:  begin op = W; wd = CONFIG_VAL; end
                5'd4:  op = P;
                5'd5:  op = S;
                5'd6:  begin op = W; wd = AW; end
                5'd7:  begin op = W; wd = 8'h04; end
                5'd8:  begin op = W; wd = thigh[15:8]; end
                5'd9:  begin op = W; wd = thigh[7:0]; end
                5'd10: op = P;
                5'd11: op = S;
                5'd12: begin op = W; wd = AW; end
                5'd13: begin op = W; wd = 8'h06; end
                5'd14: begin op = W; wd = tlow[15:8]; end
                5'd15: begin op = W; wd = tlow[7:0]; end
                default: begin op = P; last = 1'b1; end
            endcase
        end else begin
            case (step)
                5'd0: op = S;
                5'd1: begin op = W; wd = AW; end
                5'd2: begin op = W; wd = 8'h00; end
                5'd3: op = S;                                 // repeated START (the bus is owned)
                5'd4: begin op = W; wd = AR; end
                5'd5: begin op = R; rn = 1'b0; end
                5'd6: begin op = R; rn = 1'b1; end
                default: begin op = P; last = 1'b1; end
            endcase
        end
    end

    wire start_cfg = win_wr && win_addr == 7'h00 && win_wdata[0] && !busy;

    // reading timer: from the start of the previous reading
    always_ff @(posedge clk) begin
        if (rst || !configured) begin
            pc <= '0; pend <= 1'b0;
        end else if (st == IDLE && pend && !start_cfg) begin
            pc <= '0; pend <= 1'b0;
        end else if (pc == PW'(PERIOD_CYCLES - 1)) begin
            pc <= '0; pend <= 1'b1;
        end else begin
            pc <= pc + 1'b1;
        end
    end

    always_ff @(posedge clk) begin
        go <= 1'b0;
        if (rst) begin
            st <= IDLE; step <= '0; reading <= 1'b0; busy <= 1'b0; configured <= 1'b0; valid <= 1'b0;
            nack <= 1'b0; thigh <= 16'h2000; tlow <= 16'h0500; temp <= '0; tmax <= '0; tmin <= '0;
            samples <= '0; msb <= '0;
        end else begin
            if (win_wr && win_addr == 7'h02) thigh <= win_wdata[15:0];
            if (win_wr && win_addr == 7'h03) tlow  <= win_wdata[15:0];
            case (st)
                IDLE: if (start_cfg) begin
                    busy <= 1'b1; reading <= 1'b0; step <= '0; configured <= 1'b0;
                    valid <= 1'b0; nack <= 1'b0; temp <= '0; tmax <= '0; tmin <= '0; samples <= '0;
                    st <= ISSUE;
                end else if (configured && pend) begin
                    busy <= 1'b1; reading <= 1'b1; step <= '0; st <= ISSUE;
                end
                ISSUE: begin go <= 1'b1; st <= WAIT1; end
                WAIT1: st <= WAIT;
                WAIT: if (!cbusy) begin
                    if (op == W && cnack) begin
                        nack <= 1'b1;
                        st <= ABORT;
                    end else if (last) begin
                        st <= IDLE; busy <= 1'b0;
                        if (!reading) configured <= 1'b1;
                    end else begin
                        if (reading && step == 5'd5) msb <= rx;
                        if (reading && step == 5'd6) begin
                            temp <= {msb, rx};
                            samples <= samples + 1'b1;
                            valid <= 1'b1;
                            if (!valid || $signed({msb, rx}) > $signed(tmax)) tmax <= {msb, rx};
                            if (!valid || $signed({msb, rx}) < $signed(tmin)) tmin <= {msb, rx};
                        end
                        step <= step + 1'b1;
                        st <= ISSUE;
                    end
                end
                // a NACK: STOP, then end this program (a configure still completes its remaining transactions)
                ABORT: begin
                    if (!reading && step < 5'd11) begin
                        step <= (step < 5'd5) ? 5'd4 : 5'd10;     // the STOP of this transaction, then go on
                        st <= ISSUE;
                    end else begin
                        step <= 5'd16;                           // the final STOP
                        if (reading) step <= 5'd7;
                        st <= ISSUE;
                    end
                end
                default: st <= IDLE;
            endcase
        end
    end

    always_ff @(posedge clk) begin
        if (rst) win_rdata <= '0;
        else if (win_rd) begin
            case (win_addr)
                7'h01:   win_rdata <= {27'd0, alarm, nack, valid, configured, busy};
                7'h02:   win_rdata <= {16'd0, thigh};
                7'h03:   win_rdata <= {16'd0, tlow};
                7'h04:   win_rdata <= {16'd0, temp};
                7'h05:   win_rdata <= {16'd0, tmax};
                7'h06:   win_rdata <= {16'd0, tmin};
                7'h07:   win_rdata <= samples;
                default: win_rdata <= '0;
            endcase
        end
    end
endmodule
