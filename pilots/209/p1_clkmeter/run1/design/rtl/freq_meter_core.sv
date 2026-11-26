// Register core of the clock frequency meter.
// clk (25 MHz C3): register port, edge counter, LED0 blink. clk_ref (156.25 MHz): gate FSM, LED1 blink.
module freq_meter_core #(
    parameter int unsigned GATE_LEN_DEFAULT           = 156250000,
    parameter int unsigned GATE_LEN_MIN               = 1000,
    parameter int unsigned LED_C3_HALF_PERIOD_CYCLES  = 12500000,
    parameter int unsigned LED_REF_HALF_PERIOD_CYCLES = 78125000,
    parameter logic [31:0] DESIGN_ID                  = 32'h20910001
) (
    input  logic        clk,
    input  logic        clk_ref,
    input  logic        rst,           // active high, synchronous to clk
    input  logic        h_we,
    input  logic        h_re,
    input  logic [11:0] h_addr,
    input  logic [31:0] h_wdata,
    output logic [31:0] h_rdata,
    output logic [1:0]  led,
    output logic        sfp_tx_disable
);
    assign sfp_tx_disable = 1'b1;

    // ---------------- reset into clk_ref ----------------
    logic rst_ref;
    rst_sync_ref u_rst_sync_ref (.rst_in(rst), .clk_ref(clk_ref), .rst_ref(rst_ref));

    // ---------------- build stamp ----------------
    logic [31:0] build_word;
    /* verilator lint_off PINMISSING */
    /* verilator lint_off PINCONNECTEMPTY */
    USR_ACCESSE2 u_usr (.DATA(build_word), .CFGCLK(), .DATAVALID());
    /* verilator lint_on PINMISSING */

    // ---------------- registers (clk) ----------------
    logic [31:0] scratch, gate_len, count_r, gate_act_r, meas_done;
    logic        led_en, busy, done;
    logic [31:0] cnt;                    // working edge counter
    logic        snd;                    // start request handshake in flight
    logic [31:0] start_len;
    logic        start_rcv;
    logic        gate_s, gate_prev;
    logic        got_fall, got_act;
    logic [31:0] act_w;
    logic        res_req;
    logic [31:0] res_out;

    wire wr_ctrl = h_we && (h_addr == 12'h014);
    wire start_ok = wr_ctrl && h_wdata[0] && !busy;
    wire [31:0] len_clamped = (gate_len < GATE_LEN_MIN) ? 32'(GATE_LEN_MIN) : gate_len;
    wire fin = busy && got_fall && got_act;

    always_ff @(posedge clk) begin
        if (rst) begin
            scratch   <= '0;
            gate_len  <= 32'(GATE_LEN_DEFAULT);
            led_en    <= 1'b0;
            busy      <= 1'b0;
            done      <= 1'b0;
            snd       <= 1'b0;
            got_fall  <= 1'b0;
            got_act   <= 1'b0;
            meas_done <= '0;
            count_r   <= '0;
            gate_act_r <= '0;
            gate_prev <= 1'b0;
        end else begin
            gate_prev <= gate_s;
            if (h_we) begin
                case (h_addr)
                    12'h008: scratch  <= h_wdata;
                    12'h010: gate_len <= h_wdata;
                    12'h014: led_en   <= h_wdata[1];
                    default: ;
                endcase
            end
            if (start_ok) begin
                busy <= 1'b1; done <= 1'b0; snd <= 1'b1;
                got_fall <= 1'b0; got_act <= 1'b0;
            end
            if (snd && start_rcv) snd <= 1'b0;
            if (busy && gate_prev && !gate_s) got_fall <= 1'b1;
            if (res_req) begin got_act <= 1'b1; end
            if (fin) begin
                busy <= 1'b0; done <= 1'b1;
                count_r <= cnt; gate_act_r <= act_w;
                meas_done <= meas_done + 32'd1;
                got_fall <= 1'b0; got_act <= 1'b0;
            end
        end
    end

    always_ff @(posedge clk) begin
        if (start_ok) start_len <= len_clamped;
        if (res_req) act_w <= res_out;
        if (start_ok) cnt <= '0;
        else if (gate_s) cnt <= cnt + 32'd1;
    end

    // read port: registered, valid one clock after h_re, held until the next h_re
    always_ff @(posedge clk) begin
        if (rst) h_rdata <= '0;
        else if (h_re) begin
            case (h_addr)
                12'h000: h_rdata <= DESIGN_ID;
                12'h004: h_rdata <= build_word;
                12'h008: h_rdata <= scratch;
                12'h010: h_rdata <= gate_len;
                12'h014: h_rdata <= {30'd0, led_en, 1'b0};
                12'h018: h_rdata <= {30'd0, done, busy};
                12'h01C: h_rdata <= count_r;
                12'h020: h_rdata <= gate_act_r;
                12'h024: h_rdata <= meas_done;
                default: h_rdata <= '0;
            endcase
        end
    end

    // ---------------- CDC: start + gate length, clk -> clk_ref ----------------
    logic        req_pulse;
    logic [31:0] req_len;
    xpm_cdc_handshake #(.DEST_EXT_HSK(0), .DEST_SYNC_FF(4), .INIT_SYNC_FF(0), .SIM_ASSERT_CHK(0),
                        .SRC_SYNC_FF(4), .WIDTH(32)) u_start_hs (
        .src_clk(clk), .src_in(start_len), .src_send(snd), .src_rcv(start_rcv),
        .dest_clk(clk_ref), .dest_out(req_len), .dest_req(req_pulse), .dest_ack(1'b0));

    // ---------------- gate FSM (clk_ref) ----------------
    logic        gate_open, res_send, res_rcv;
    logic [31:0] len_l, acnt, res_data;
    wire  [31:0] acnt_n = acnt + 32'd1;
    always_ff @(posedge clk_ref) begin
        if (rst_ref) begin
            gate_open <= 1'b0;
            res_send  <= 1'b0;
        end else begin
            if (req_pulse) gate_open <= 1'b1;
            if (gate_open && acnt_n == len_l) begin gate_open <= 1'b0; res_send <= 1'b1; end
            if (res_send && res_rcv) res_send <= 1'b0;
        end
    end
    always_ff @(posedge clk_ref) begin
        if (req_pulse) begin len_l <= req_len; acnt <= '0; end
        else if (gate_open) begin
            acnt <= acnt_n;
            res_data <= acnt_n;
        end
    end

    // gate_open -> clk
    xpm_cdc_single #(.DEST_SYNC_FF(3), .INIT_SYNC_FF(0), .SIM_ASSERT_CHK(0), .SRC_INPUT_REG(0)) u_gate_sync (
        .src_clk(clk_ref), .src_in(gate_open), .dest_clk(clk), .dest_out(gate_s));

    // result: actual gate length, clk_ref -> clk
    xpm_cdc_handshake #(.DEST_EXT_HSK(0), .DEST_SYNC_FF(4), .INIT_SYNC_FF(0), .SIM_ASSERT_CHK(0),
                        .SRC_SYNC_FF(4), .WIDTH(32)) u_res_hs (
        .src_clk(clk_ref), .src_in(res_data), .src_send(res_send), .src_rcv(res_rcv),
        .dest_clk(clk), .dest_out(res_out), .dest_req(res_req), .dest_ack(1'b0));

    // ---------------- LEDs ----------------
    localparam int CW = 32;
    logic led0_q, led1_q;
    assign led = {led1_q, led0_q};
    logic [CW-1:0] c3_cnt, ref_cnt;
    logic          led0_t, led1_t, led_en_ref;
    always_ff @(posedge clk) begin
        if (rst || !led_en) begin c3_cnt <= '0; led0_t <= 1'b0; led0_q <= 1'b0; end
        else begin
            if (c3_cnt == CW'(LED_C3_HALF_PERIOD_CYCLES - 1)) begin c3_cnt <= '0; led0_t <= ~led0_t; end
            else c3_cnt <= c3_cnt + 1'b1;
            led0_q <= led_en & led0_t;
        end
    end

    xpm_cdc_single #(.DEST_SYNC_FF(3), .INIT_SYNC_FF(0), .SIM_ASSERT_CHK(0), .SRC_INPUT_REG(0)) u_led_en_sync (
        .src_clk(clk), .src_in(led_en), .dest_clk(clk_ref), .dest_out(led_en_ref));

    always_ff @(posedge clk_ref) begin
        if (rst_ref || !led_en_ref) begin ref_cnt <= '0; led1_t <= 1'b0; led1_q <= 1'b0; end
        else begin
            if (ref_cnt == CW'(LED_REF_HALF_PERIOD_CYCLES - 1)) begin ref_cnt <= '0; led1_t <= ~led1_t; end
            else ref_cnt <= ref_cnt + 1'b1;
            led1_q <= led_en_ref & led1_t;
        end
    end
endmodule
