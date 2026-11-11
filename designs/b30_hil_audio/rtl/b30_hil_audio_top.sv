// b30_hil_audio_top.sv: the brief-30 hardware-in-the-loop demonstration design for the Nexys A7-100T.
// One design that carries the library instruments behind the test shell, so every sensing path has something to read:
//   dds_awg           -> the tone: sine at 48.008 kHz sample rate -> PWM -> AUD_PWM (the board's low-pass filter and jack)
//   freq_duty_counter -> measures the tone's sign bit (zero crossings) in the FPGA
//   logic_analyser    -> captures the 16-bit tone samples at the sample rate
//   frame_crc         -> CRC of a synthetic 128-pixel "frame" from a 24-bit LFSR, every 4096 clocks
//   XADC              -> Tj, VCCINT, VCCAUX, VCCBRAM codes, polled into registers
// Window registers (address = ADDR - 0x80), 32 bit:
//   0x00 CTRL    RW  bit0 tone on (reset 1), bit1 flip one pixel bit of every frame (the data-path fault switch)
//   0x01 STEP    RW  DDS phase step (reset 89463225: 1 kHz at 48.008 kHz)
//   0x02 WAVE    RW  [1:0] wave (0 sine,1 triangle,2 saw,3 square), [7:4] amplitude shift (reset 0, 2)
//   0x03 SAMPLE  R   current DDS sample (sign extended)
//   0x10 FD_EDGES, 0x11 FD_HIGH, 0x12 FD_GATES, 0x13 FD_GATE_CLKS (50e6 clocks, 0.5 s)   R   freq_duty_counter on the sample sign bit
//   0x20-0x28    logic_analyser registers (see ip_lib/logic_analyser)
//   0x40 XT, 0x41 XVCCINT, 0x42 XVCCAUX, 0x43 XVCCBRAM   R   raw 12-bit XADC codes (UG480)
//   0x50 FC_CRC, 0x51 FC_FRAMES, 0x52 FC_PIX, 0x53 FC_SUM, 0x54 FC_EXPECT (RW), 0x55 FC_MISMATCH   R/RW   frame_crc
module b30_hil_audio_top #(
    parameter int          CLKS_PER_BIT   = 868,
    parameter int          TIMEOUT_CYCLES = 100_000,
    parameter int          FD_GATE_CLKS   = 50_000_000,   // 0.5 s at 100 MHz (the simulation shrinks it)
    parameter logic [31:0] BUILD_STAMP    = 32'h0
) (
    input  logic       CLK100MHZ,
    input  logic       CPU_RESETN,
    input  logic       UART_TXD_IN,
    output logic       UART_RXD_OUT,
    output wire        AUD_PWM,
    output logic       AUD_SD,
    output logic [1:0] LED
);
    logic clk, rst;
    assign clk = CLK100MHZ;
    reset_sync u_rst (.clk(clk), .rst_n_async(CPU_RESETN), .rst(rst));

    logic [6:0]  win_addr;
    logic        win_wr, win_rd;
    logic [31:0] win_wdata, win_rdata;
    fpga_shell #(.CLKS_PER_BIT(CLKS_PER_BIT), .TIMEOUT_CYCLES(TIMEOUT_CYCLES), .DESIGN_ID(32'h4833_3041), .BUILD_STAMP(BUILD_STAMP)) u_shell (
        .clk(clk), .rst(rst), .uart_rx(UART_TXD_IN), .uart_tx(UART_RXD_OUT),
        .win_addr(win_addr), .win_wr(win_wr), .win_rd(win_rd), .win_wdata(win_wdata), .win_rdata(win_rdata));

    // ------------------------------------------------------------------ control registers
    logic        tone_on = 1'b1, flip = 1'b0;
    logic [31:0] step = 32'd89463225;
    logic [1:0]  wave = 2'd0;
    logic [3:0]  amp  = 4'd2;
    logic [31:0] fc_expect = '0;
    always_ff @(posedge clk) begin
        if (rst) begin tone_on <= 1'b1; flip <= 1'b0; step <= 32'd89463225; wave <= 2'd0; amp <= 4'd2; fc_expect <= '0; end
        else if (win_wr) case (win_addr)
            7'h00: begin tone_on <= win_wdata[0]; flip <= win_wdata[1]; end
            7'h01: step <= win_wdata;
            7'h02: begin wave <= win_wdata[1:0]; amp <= win_wdata[7:4]; end
            7'h54: fc_expect <= win_wdata;
            default: ;
        endcase
    end

    // ------------------------------------------------------------------ tone: 48.008 kHz sample tick, DDS, PWM
    logic [11:0] tcnt = '0;
    logic        tick = 1'b0;
    always_ff @(posedge clk) begin
        tick <= (tcnt == 12'd2082);
        tcnt <= (tcnt == 12'd2082) ? '0 : tcnt + 1'b1;
    end
    logic signed [15:0] sample;
    logic [31:0] ph_unused;
    dds_awg #(.PHASE_W(32), .LUT_W(8), .OUT_W(16)) u_dds (
        .clk(clk), .rst(rst), .tick(tick), .step(step), .wave(wave), .amp_shift(amp), .sample(sample), .phase_o(ph_unused));

    logic [9:0] pwm_cnt = '0;
    logic [9:0] duty;
    always_ff @(posedge clk) begin
        pwm_cnt <= pwm_cnt + 1'b1;
        if (pwm_cnt == 10'd1023) duty <= tone_on ? (sample[15:6] ^ 10'h200) : 10'h200;     // offset binary, mid-scale when off
    end
    logic pwm_hi;
    assign pwm_hi = (pwm_cnt < duty);
    assign AUD_PWM = pwm_hi ? 1'bz : 1'b0;      // the board's audio stage pulls the line up: drive low, release high
    assign AUD_SD  = 1'b1;
    logic [25:0] beat = '0;
    always_ff @(posedge clk) beat <= beat + 1'b1;
    assign LED = {beat[25], tone_on};

    // ------------------------------------------------------------------ in-FPGA instruments
    logic        fd_valid;
    logic [25:0] fd_edges, fd_high;
    logic [31:0] fd_gates;
    freq_duty_counter #(.GATE_CLKS(FD_GATE_CLKS), .CNT_W(26)) u_fd (
        .clk(clk), .rst(rst), .sig(~sample[15]), .valid(fd_valid), .edges(fd_edges), .high_clks(fd_high), .gates(fd_gates));

    logic [31:0] la_rdata;
    logic_analyser #(.WIDTH(16), .ADDR_W(8)) u_la (
        .clk(clk), .rst(rst), .sample(sample), .sample_en(tick),
        .win_addr({3'b0, win_addr[3:0]}), .win_wr(win_wr && win_addr[6:4] == 3'h2), .win_rd(win_rd), .win_wdata(win_wdata), .win_rdata(la_rdata));

    // synthetic frame: 128 pixels of a 24-bit LFSR (seed 0xACE1, s <= {s[22:0], s23^s22^s21^s16}) every 4096 clocks
    logic [11:0] fcnt = '0;
    logic [23:0] lfsr = 24'h00ACE1;
    logic        f_start, p_valid;
    logic [23:0] p_data;
    always_ff @(posedge clk) begin
        fcnt    <= fcnt + 1'b1;
        f_start <= (fcnt == 12'hFFF);
        p_valid <= (fcnt < 12'd128) && (fcnt != 12'hFFF);
        if (fcnt == 12'hFFF) lfsr <= 24'h00ACE1;
        else if (fcnt < 12'd128) lfsr <= {lfsr[22:0], lfsr[23] ^ lfsr[22] ^ lfsr[21] ^ lfsr[16]};
        p_data  <= (flip && fcnt == 12'd64) ? (lfsr ^ 24'h000001) : lfsr;
    end
    logic [31:0] fc_crc, fc_pix, fc_sum, fc_frames, fc_mism;
    logic        fc_done;
    frame_crc #(.PIX_W(24)) u_fc (
        .clk(clk), .rst(rst), .frame_start(f_start), .pix_valid(p_valid), .pix_data(p_data), .crc_expect(fc_expect),
        .crc_last(fc_crc), .pix_last(fc_pix), .sum_last(fc_sum), .frames(fc_frames), .mismatches(fc_mism), .frame_done(fc_done));

    // ------------------------------------------------------------------ XADC: Tj, VCCINT, VCCAUX, VCCBRAM
    logic [15:0] do_x;
    logic        drdy, den = 1'b0;
    logic [6:0]  daddr = 7'h00;
    logic [11:0] xcode [0:3];
    logic [1:0]  xsel = '0;
    logic [19:0] xpc = '0;
    initial begin xcode[0] = '0; xcode[1] = '0; xcode[2] = '0; xcode[3] = '0; end
    XADC #(
        .INIT_40(16'h1000), .INIT_41(16'h2EF0), .INIT_42(16'h0400), .INIT_48(16'h4700), .INIT_49(16'h0000),
        .INIT_4A(16'h4700), .INIT_4B(16'h0000), .INIT_4C(16'h0000), .INIT_4D(16'h0000), .INIT_4E(16'h0000),
        .INIT_4F(16'h0000), .INIT_50(16'hB5ED), .INIT_51(16'h57E4), .INIT_52(16'hA147), .INIT_53(16'hCA33),
        .INIT_54(16'hA93A), .INIT_55(16'h52C6), .INIT_56(16'h9555), .INIT_57(16'hAE4E), .INIT_58(16'h5999),
        .INIT_5C(16'h5111), .SIM_DEVICE("7SERIES")
    ) u_xadc (
        .DCLK(clk), .DEN(den), .DWE(1'b0), .DADDR(daddr), .DI(16'h0000), .DO(do_x), .DRDY(drdy),
        .RESET(1'b0), .CONVST(1'b0), .CONVSTCLK(1'b0), .VP(1'b0), .VN(1'b0), .VAUXP(16'h0000), .VAUXN(16'h0000),
        .ALM(), .OT(), .BUSY(), .CHANNEL(), .EOC(), .EOS(), .JTAGBUSY(), .JTAGLOCKED(), .JTAGMODIFIED(), .MUXADDR());
    always_ff @(posedge clk) begin
        den <= 1'b0;
        xpc <= xpc + 1'b1;
        if (xpc == '0) begin
            daddr <= (xsel == 2'd0) ? 7'h00 : (xsel == 2'd1) ? 7'h01 : (xsel == 2'd2) ? 7'h02 : 7'h06;
            den   <= 1'b1;
        end
        if (drdy) begin xcode[xsel] <= do_x[15:4]; xsel <= xsel + 1'b1; end
    end

    // ------------------------------------------------------------------ window read mux (registered: valid the clock after win_rd)
    always_ff @(posedge clk) begin
        casez (win_addr)
            7'h00: win_rdata <= {30'b0, flip, tone_on};
            7'h01: win_rdata <= step;
            7'h02: win_rdata <= {24'b0, amp, 2'b0, wave};
            7'h03: win_rdata <= {{16{sample[15]}}, sample};
            7'h10: win_rdata <= {6'b0, fd_edges};
            7'h11: win_rdata <= {6'b0, fd_high};
            7'h12: win_rdata <= fd_gates;
            7'h13: win_rdata <= 32'(FD_GATE_CLKS);
            7'h2?: win_rdata <= la_rdata;
            7'h40: win_rdata <= {20'b0, xcode[0]};
            7'h41: win_rdata <= {20'b0, xcode[1]};
            7'h42: win_rdata <= {20'b0, xcode[2]};
            7'h43: win_rdata <= {20'b0, xcode[3]};
            7'h50: win_rdata <= fc_crc;
            7'h51: win_rdata <= fc_frames;
            7'h52: win_rdata <= fc_pix;
            7'h53: win_rdata <= fc_sum;
            7'h54: win_rdata <= fc_expect;
            7'h55: win_rdata <= fc_mism;
            default: win_rdata <= '0;
        endcase
    end
endmodule
