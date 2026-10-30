// dimmer_counter.sv: the T1 design without its pins: counter, PWM dimmer,
// display scan, and the registers in the test shell's window
// (designs/t1_dimmer_counter/spec.yaml).

module dimmer_counter #(
    parameter int DEBOUNCE_CYCLES = 1_000_000,
    parameter int PWM_PRESCALE    = 4,
    parameter int REFRESH_BITS    = 17
) (
    input  logic        clk,
    input  logic        rst,
    input  logic        btn_up,
    input  logic        btn_down,
    input  logic        btn_clear,
    input  logic [15:0] sw_async,
    output logic [15:0] led,
    output logic [7:0]  an,
    output logic [6:0]  seg,
    // shell window
    input  logic [6:0]  win_addr,
    input  logic        win_wr,
    input  logic        win_rd,
    /* verilator lint_off UNUSEDSIGNAL */
    input  logic [31:0] win_wdata,          // registers are at most 16 bits wide
    /* verilator lint_on UNUSEDSIGNAL */
    output logic [31:0] win_rdata
);
    localparam logic [6:0] R_COUNT = 7'h00, R_DUTY = 7'h01, R_CTRL = 7'h02, R_INPUTS = 7'h03, R_PRESSES = 7'h04;
    localparam int PW = $clog2(PWM_PRESCALE + 1);

    logic [15:0] count;
    logic [7:0]  duty;
    logic [1:0]  ctrl;                // [0] DUTY_SRC, [1] DISPLAY_EN
    logic [7:0]  n_up, n_down, n_clear;
    logic [15:0] sw;
    logic        lv_up, lv_down, lv_clear, p_up, p_down, p_clear;
    logic [PW-1:0] pre;
    logic [7:0]  phase;

    debounce #(.CYCLES(DEBOUNCE_CYCLES)) u_db_up    (.clk(clk), .rst(rst), .btn(btn_up),    .level(lv_up),    .press(p_up));
    debounce #(.CYCLES(DEBOUNCE_CYCLES)) u_db_down  (.clk(clk), .rst(rst), .btn(btn_down),  .level(lv_down),  .press(p_down));
    debounce #(.CYCLES(DEBOUNCE_CYCLES)) u_db_clear (.clk(clk), .rst(rst), .btn(btn_clear), .level(lv_clear), .press(p_clear));
    sync2 #(.WIDTH(16)) u_sw_sync (.clk(clk), .rst(rst), .d(sw_async), .q(sw));

    wire [7:0] duty_eff = ctrl[0] ? sw[7:0] : duty;

    // counter, registers, press counts
    always_ff @(posedge clk) begin
        if (rst) begin
            count   <= '0;
            duty    <= 8'h40;
            ctrl    <= 2'b10;
            n_up    <= '0;
            n_down  <= '0;
            n_clear <= '0;
        end else begin
            if (p_up)    n_up    <= n_up + 1'b1;
            if (p_down)  n_down  <= n_down + 1'b1;
            if (p_clear) n_clear <= n_clear + 1'b1;

            if (win_wr && win_addr == R_COUNT) count <= win_wdata[15:0];
            else if (p_clear)                  count <= '0;
            else if (p_up)                     count <= count + 1'b1;
            else if (p_down)                   count <= count - 1'b1;

            if (win_wr && win_addr == R_DUTY) duty <= win_wdata[7:0];
            if (win_wr && win_addr == R_CTRL) ctrl <= win_wdata[1:0];
        end
    end

    // register read, one cycle after win_rd
    always_ff @(posedge clk) begin
        if (rst) begin
            win_rdata <= '0;
        end else if (win_rd) begin
            case (win_addr)
                R_COUNT:   win_rdata <= {16'h0, count};
                R_DUTY:    win_rdata <= {24'h0, duty};
                R_CTRL:    win_rdata <= {30'h0, ctrl};
                R_INPUTS:  win_rdata <= {13'h0, lv_clear, lv_down, lv_up, sw};
                R_PRESSES: win_rdata <= {8'h0, n_clear, n_down, n_up};
                default:   win_rdata <= '0;
            endcase
        end
    end

    // PWM: the phase advances every PWM_PRESCALE clocks; LEDs lit while phase < duty
    always_ff @(posedge clk) begin
        if (rst) begin
            pre   <= '0;
            phase <= '0;
            led   <= '0;
        end else begin
            if (pre == PW'(PWM_PRESCALE - 1)) begin
                pre   <= '0;
                phase <= phase + 1'b1;
            end else begin
                pre <= pre + 1'b1;
            end
            led <= (phase < duty_eff) ? count : 16'h0;
        end
    end

    sevenseg_scan #(.REFRESH_BITS(REFRESH_BITS)) u_scan (
        .clk(clk), .rst(rst), .enable(ctrl[1]),
        .digits({duty_eff, 8'h00, count}), .blank(8'b0011_0000),
        .an(an), .seg(seg));
endmodule
