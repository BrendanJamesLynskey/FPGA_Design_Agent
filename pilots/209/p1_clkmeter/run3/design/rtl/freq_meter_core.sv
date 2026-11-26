// freq_meter_core: register file, measurement control, LED dividers and the clk_c3 <-> clk_ref crossings.
// clk is the 25 MHz C3 clock (register-port clock), clk_ref the 156.25 MHz reference (the ruler).
module freq_meter_core #(
    parameter logic [31:0] DESIGN_ID                  = 32'h20910001,
    parameter int unsigned GATE_DEFAULT_CYCLES        = 156250000,
    parameter int unsigned GATE_MIN_CYCLES            = 1000,
    parameter int unsigned LED_C3_HALF_PERIOD_CYCLES  = 12500000,
    parameter int unsigned LED_REF_HALF_PERIOD_CYCLES = 78125000
) (
    input  logic        clk,
    input  logic        clk_ref,
    input  logic        rst,          // active high, synchronous to clk
    input  logic        h_we,
    input  logic        h_re,
    input  logic [11:0] h_addr,
    input  logic [31:0] h_wdata,
    output logic [31:0] h_rdata,
    output logic [1:0]  led,
    output logic        sfp_tx_disable
);
    assign sfp_tx_disable = 1'b1;

    // ---------------- BUILD word ----------------
    logic [31:0] build_word;
    logic usr_cfgclk, usr_valid;
    USR_ACCESSE2 u_usr (.CFGCLK(usr_cfgclk), .DATA(build_word), .DATAVALID(usr_valid));
    /* verilator lint_off UNUSEDSIGNAL */
    logic unused_usr;
    assign unused_usr = usr_cfgclk ^ usr_valid;
    /* verilator lint_on UNUSEDSIGNAL */

    // ---------------- reset into clk_ref ----------------
    logic rst_ref;
    xpm_cdc_async_rst #(.DEST_SYNC_FF(4), .INIT_SYNC_FF(0), .RST_ACTIVE_HIGH(1)) u_rst_ref (
        .src_arst(rst), .dest_clk(clk_ref), .dest_arst(rst_ref));

    // ---------------- clk_c3 domain: registers ----------------
    logic [31:0] scratch, gate_len, count_r, actual_r, meas_done, len_lat;
    logic        led_en, busy, done;
    logic        c2r_send, c2r_rcv;
    logic        r2c_req;
    logic [31:0] r2c_data, act_l;
    logic        gate_s, gate_q, fell_f, got_f;
    logic [31:0] cnt;

    wire wr_ctrl = h_we && (h_addr == 12'h014);
    wire start   = wr_ctrl && h_wdata[0] && !busy;
    wire finish  = fell_f && got_f && busy;

    always_ff @(posedge clk) begin
        if (rst) begin
            scratch   <= 32'd0;
            gate_len  <= GATE_DEFAULT_CYCLES;
            led_en    <= 1'b0;
            busy      <= 1'b0;
            done      <= 1'b0;
            meas_done <= 32'd0;
            c2r_send  <= 1'b0;
            fell_f    <= 1'b0;
            got_f     <= 1'b0;
            gate_q    <= 1'b0;
        end else begin
            if (h_we && h_addr == 12'h008) scratch  <= h_wdata;
            if (h_we && h_addr == 12'h010) gate_len <= h_wdata;
            if (wr_ctrl) led_en <= h_wdata[1];
            gate_q <= gate_s;
            if (gate_q && !gate_s) fell_f <= 1'b1;
            if (r2c_req)           got_f  <= 1'b1;
            if (start) begin
                busy     <= 1'b1;
                done     <= 1'b0;
                c2r_send <= 1'b1;
            end
            if (c2r_send && c2r_rcv) c2r_send <= 1'b0;
            if (finish) begin
                busy      <= 1'b0;
                done      <= 1'b1;
                meas_done <= meas_done + 32'd1;
                fell_f    <= 1'b0;
                got_f     <= 1'b0;
            end
        end
    end

    // datapath registers, no reset
    always_ff @(posedge clk) begin
        if (start) len_lat <= (gate_len < GATE_MIN_CYCLES) ? 32'(GATE_MIN_CYCLES) : gate_len;
        if (r2c_req) act_l <= r2c_data;
        if (gate_s) cnt <= gate_q ? cnt + 32'd1 : 32'd1;
    end
    always_ff @(posedge clk) begin
        if (rst) begin
            count_r  <= 32'd0;
            actual_r <= 32'd0;
        end else if (finish) begin
            count_r  <= cnt;
            actual_r <= act_l;
        end
    end

    // Result registers as the host sees them: refreshed from the live results only when a STATUS
    // read finds the meter not busy, so COUNT/GATE_ACTUAL/MEAS_DONE never change under a host
    // that last saw BUSY (they are stable from the STATUS read that reports DONE).
    logic [31:0] count_h, actual_h, meas_h;
    always_ff @(posedge clk) begin
        if (rst) begin
            count_h <= 32'd0; actual_h <= 32'd0; meas_h <= 32'd0;
        end else if (h_re && h_addr == 12'h018 && !busy) begin
            count_h <= count_r; actual_h <= actual_r; meas_h <= meas_done;
        end
    end

    // read port
    always_ff @(posedge clk) begin
        if (rst) h_rdata <= 32'd0;
        else if (h_re) begin
            case (h_addr)
                12'h000: h_rdata <= DESIGN_ID;
                12'h004: h_rdata <= build_word;
                12'h008: h_rdata <= scratch;
                12'h010: h_rdata <= gate_len;
                12'h014: h_rdata <= {30'd0, led_en, 1'b0};
                12'h018: h_rdata <= {30'd0, done, busy};
                12'h01C: h_rdata <= count_h;
                12'h020: h_rdata <= actual_h;
                12'h024: h_rdata <= meas_h;
                default: h_rdata <= 32'd0;
            endcase
        end
    end

    // ---------------- crossings ----------------
    logic        c2r_req;
    logic [31:0] c2r_data;
    xpm_cdc_handshake #(.DEST_EXT_HSK(0), .DEST_SYNC_FF(4), .INIT_SYNC_FF(0), .SIM_ASSERT_CHK(0),
                        .SRC_SYNC_FF(4), .WIDTH(32)) u_c2r (
        .src_clk(clk), .src_in(len_lat), .src_send(c2r_send), .src_rcv(c2r_rcv),
        .dest_clk(clk_ref), .dest_out(c2r_data), .dest_req(c2r_req), .dest_ack(1'b0));

    logic        rs_send, rs_rcv;
    logic [31:0] actual_ref;
    xpm_cdc_handshake #(.DEST_EXT_HSK(0), .DEST_SYNC_FF(4), .INIT_SYNC_FF(0), .SIM_ASSERT_CHK(0),
                        .SRC_SYNC_FF(4), .WIDTH(32)) u_r2c (
        .src_clk(clk_ref), .src_in(actual_ref), .src_send(rs_send), .src_rcv(rs_rcv),
        .dest_clk(clk), .dest_out(r2c_data), .dest_req(r2c_req), .dest_ack(1'b0));

    logic gate_open;
    xpm_cdc_single #(.DEST_SYNC_FF(3), .INIT_SYNC_FF(0), .SIM_ASSERT_CHK(0), .SRC_INPUT_REG(0)) u_gate (
        .src_clk(clk_ref), .src_in(gate_open), .dest_clk(clk), .dest_out(gate_s));

    logic led_en_ref;
    xpm_cdc_single #(.DEST_SYNC_FF(3), .INIT_SYNC_FF(0), .SIM_ASSERT_CHK(0), .SRC_INPUT_REG(0)) u_leden (
        .src_clk(clk), .src_in(led_en), .dest_clk(clk_ref), .dest_out(led_en_ref));

    // ---------------- clk_ref domain: gate ----------------
    logic [31:0] len_m1, acnt;
    logic        arm;
    always_ff @(posedge clk_ref) begin
        if (rst_ref) begin
            gate_open <= 1'b0;
            arm       <= 1'b0;
            rs_send   <= 1'b0;
        end else begin
            if (c2r_req) arm <= 1'b1;
            if (arm) begin
                arm       <= 1'b0;
                gate_open <= 1'b1;
            end
            if (gate_open && acnt == len_m1) begin
                gate_open <= 1'b0;
                rs_send   <= 1'b1;
            end
            if (rs_send && rs_rcv) rs_send <= 1'b0;
        end
    end
    always_ff @(posedge clk_ref) begin
        if (c2r_req) len_m1 <= c2r_data - 32'd1;
        if (arm) acnt <= 32'd0;
        else if (gate_open) acnt <= acnt + 32'd1;
        if (gate_open && acnt == len_m1) actual_ref <= acnt + 32'd1;
    end

    // ---------------- LEDs ----------------
    localparam int W0 = $clog2(LED_C3_HALF_PERIOD_CYCLES + 1);
    localparam int W1 = $clog2(LED_REF_HALF_PERIOD_CYCLES + 1);
    logic [W0-1:0] c0;
    logic [W1-1:0] c1;
    logic          led0, led1;
    always_ff @(posedge clk) begin
        if (rst || !led_en) begin
            c0   <= '0;
            led0 <= 1'b0;
        end else if (c0 == W0'(LED_C3_HALF_PERIOD_CYCLES - 1)) begin
            c0   <= '0;
            led0 <= ~led0;
        end else c0 <= c0 + 1'b1;
    end
    always_ff @(posedge clk_ref) begin
        if (rst_ref || !led_en_ref) begin
            c1   <= '0;
            led1 <= 1'b0;
        end else if (c1 == W1'(LED_REF_HALF_PERIOD_CYCLES - 1)) begin
            c1   <= '0;
            led1 <= ~led1;
        end else c1 <= c1 + 1'b1;
    end
    assign led = {led1, led0};
endmodule
