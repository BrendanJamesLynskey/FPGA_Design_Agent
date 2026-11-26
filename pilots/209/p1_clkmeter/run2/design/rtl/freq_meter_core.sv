// freq_meter_core: register file, gate counter (clk = ref_clk), c3_clk edge counter, LED blinkers.
module freq_meter_core #(
    parameter logic [31:0] GATE_LEN_DEFAULT            = 32'd156250000,
    parameter logic [31:0] GATE_LEN_MIN                = 32'd1000,
    parameter logic [31:0] LED_HALF_PERIOD_C3_CYCLES   = 32'd12500000,
    parameter logic [31:0] LED_HALF_PERIOD_REF_CYCLES  = 32'd78125000,
    parameter logic [31:0] DESIGN_ID                   = 32'd546373633
) (
    input  logic        clk,        // ref_clk
    input  logic        rst,        // active high, synchronous to clk
    input  logic        c3_clk,
    input  logic        h_we,
    input  logic        h_re,
    input  logic [11:0] h_addr,
    input  logic [31:0] h_wdata,
    output logic [31:0] h_rdata,
    output logic [1:0]  led,
    output logic        sfp_tx_disable
);
    localparam int WAIT_N = 23;   // ref cycles: gate close seen in c3 (2 edges), last count edge, 2-FF back (~22)

    assign sfp_tx_disable = 1'b1;

    // ---------------- build stamp ----------------
    logic [31:0] build_word;
    /* verilator lint_off PINMISSING */
    /* verilator lint_off PINCONNECTEMPTY */
    USR_ACCESSE2 u_usr (.CFGCLK(), .DATA(build_word), .DATAVALID());
    /* verilator lint_on PINCONNECTEMPTY */
    /* verilator lint_on PINMISSING */

    // ---------------- ref domain registers ----------------
    logic [31:0] scratch, gate_len, count_r, gate_actual, meas_done, latched, rem;
    logic        led_en, busy, done, gate_open;
    logic [1:0]  state;           // 0 idle, 1 run, 2 wait
    logic [5:0]  wcnt;
    logic [31:0] count_x;         // count from c3 domain (after crossing)

    localparam logic [1:0] S_IDLE = 2'd0, S_RUN = 2'd1, S_WAIT = 2'd2;

    wire start_req = h_we && (h_addr == 12'h014) && h_wdata[0] && !busy;
    wire [31:0] gate_eff = (gate_len < GATE_LEN_MIN) ? GATE_LEN_MIN : gate_len;

    always_ff @(posedge clk) begin
        if (rst) begin
            scratch     <= 32'd0;
            gate_len    <= GATE_LEN_DEFAULT;
            led_en      <= 1'b0;
            busy        <= 1'b0;
            done        <= 1'b0;
            gate_open   <= 1'b0;
            state       <= S_IDLE;
            count_r     <= 32'd0;
            gate_actual <= 32'd0;
            meas_done   <= 32'd0;
        end else begin
            if (h_we) begin
                case (h_addr)
                    12'h008: scratch  <= h_wdata;
                    12'h010: gate_len <= h_wdata;
                    12'h014: led_en   <= h_wdata[1];
                    default: ;
                endcase
            end
            case (state)
                S_IDLE: if (start_req) begin
                    busy      <= 1'b1;
                    done      <= 1'b0;
                    latched   <= gate_eff;
                    rem       <= gate_eff - 32'd1;
                    gate_open <= 1'b1;
                    state     <= S_RUN;
                end
                S_RUN: begin
                    rem <= rem - 32'd1;
                    if (rem == 32'd0) begin
                        gate_open <= 1'b0;
                        wcnt      <= 6'd0;
                        state     <= S_WAIT;
                    end
                end
                default: begin
                    wcnt <= wcnt + 6'd1;
                    if (wcnt == 6'(WAIT_N)) begin
                        count_r     <= count_x;
                        gate_actual <= latched;
                        done        <= 1'b1;
                        busy        <= 1'b0;
                        meas_done   <= meas_done + 32'd1;
                        state       <= S_IDLE;
                    end
                end
            endcase
        end
    end

    // read port: registered, holds until next h_re
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
                12'h01C: h_rdata <= count_r;
                12'h020: h_rdata <= gate_actual;
                12'h024: h_rdata <= meas_done;
                default: h_rdata <= 32'd0;
            endcase
        end
    end

    // LED 1 (ref domain)
    logic [31:0] led1_cnt;
    logic        led1_r;
    always_ff @(posedge clk) begin
        if (rst || !led_en) begin
            led1_cnt <= 32'd0;
            led1_r   <= 1'b0;
        end else if (led1_cnt == LED_HALF_PERIOD_REF_CYCLES - 32'd1) begin
            led1_cnt <= 32'd0;
            led1_r   <= ~led1_r;
        end else begin
            led1_cnt <= led1_cnt + 32'd1;
        end
    end

    // ---------------- crossings ref -> c3 ----------------
    logic rst_c3, gate_c3, led_en_c3;
    xpm_cdc_async_rst #(.DEST_SYNC_FF(4), .INIT_SYNC_FF(0), .RST_ACTIVE_HIGH(1)) u_rst_c3 (
        .src_arst(rst), .dest_clk(c3_clk), .dest_arst(rst_c3));
    xpm_cdc_single #(.DEST_SYNC_FF(2), .INIT_SYNC_FF(0), .SIM_ASSERT_CHK(0), .SRC_INPUT_REG(0)) u_gate (
        .src_clk(clk), .src_in(gate_open), .dest_clk(c3_clk), .dest_out(gate_c3));
    xpm_cdc_single #(.DEST_SYNC_FF(2), .INIT_SYNC_FF(0), .SIM_ASSERT_CHK(0), .SRC_INPUT_REG(1)) u_led_en (
        .src_clk(clk), .src_in(led_en), .dest_clk(c3_clk), .dest_out(led_en_c3));

    // ---------------- c3 domain ----------------
    logic [31:0] c3_cnt;
    logic [31:0] led0_cnt;
    logic        gate_d, led0_r;
    always_ff @(posedge c3_clk) begin
        if (rst_c3) begin
            c3_cnt   <= 32'd0;
            gate_d   <= 1'b0;
            led0_cnt <= 32'd0;
            led0_r   <= 1'b0;
        end else begin
            gate_d <= gate_c3;
            if (gate_c3) c3_cnt <= (gate_d ? c3_cnt : 32'd0) + 32'd1;
            if (!led_en_c3) begin
                led0_cnt <= 32'd0;
                led0_r   <= 1'b0;
            end else if (led0_cnt == LED_HALF_PERIOD_C3_CYCLES - 32'd1) begin
                led0_cnt <= 32'd0;
                led0_r   <= ~led0_r;
            end else begin
                led0_cnt <= led0_cnt + 32'd1;
            end
        end
    end

    // ---------------- crossing c3 -> ref (read only after the gate has closed and WAIT_N elapsed) ----------------
    xpm_cdc_array_single #(.DEST_SYNC_FF(2), .INIT_SYNC_FF(0), .SIM_ASSERT_CHK(0), .SRC_INPUT_REG(0), .WIDTH(32)) u_cnt (
        .src_clk(c3_clk), .src_in(c3_cnt), .dest_clk(clk), .dest_out(count_x));

    assign led = {led1_r & led_en, led0_r & led_en};
endmodule
