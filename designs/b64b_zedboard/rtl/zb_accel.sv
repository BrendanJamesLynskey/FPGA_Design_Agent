// zb_accel: one packet at a time through a CRC-32 or a 16-tap FIR, between an AXI DMA's MM2S and S2MM streams (brief 64B).
//
// Control: the generated register block zb_accel_regs (regmaps/zb_accel.yaml). CMD.START arms the block for ONE packet: it
// clears the CRC, or (FIR mode) resets the FIR, waits for it to finish clearing, and loads the 16 coefficients from COEF0..15.
// Until it is armed (and loaded) the input stream is not accepted (s_axis_tready low). The packet ends at the input beat with
// TLAST; the block then disarms by itself.
//
//   CRC mode (CTRL.MODE = 0): CRC-32 (IEEE 802.3, reflected, init 0xFFFFFFFF, final XOR 0xFFFFFFFF) of the bytes of the packet,
//     the bytes of each 32-bit beat taken least-significant byte first. Every input beat is 4 valid bytes (TKEEP is ignored:
//     the packet length is a multiple of 4 bytes). One output beat: the CRC, with TLAST, after the last input beat.
//   FIR mode (CTRL.MODE = 1): y[n] = sum h[k] x[n-k], 16 taps, x = the low 16 bits of each input beat as a signed number,
//     h = COEFk signed 12 bits, y = signed 32 bits (16 + 12 + 4 bits: no rounding, no overflow). One output beat per input beat
//     (the filter starts from zero history at START), TLAST on the output beat of the input beat that had TLAST.
//
// Interfaces: AXI4-Lite slave (the register block); AXI4-Stream slave and master, 32 bits.
// Clock aclk, reset aresetn (active low, synchronous). Fabric clocks are counted in JOB_CYCLES from the START command to the
// last output beat leaving.
module zb_accel (
    (* X_INTERFACE_INFO = "xilinx.com:signal:clock:1.0 aclk CLK" *)
    (* X_INTERFACE_PARAMETER = "ASSOCIATED_BUSIF s_axil:s_axis:m_axis, ASSOCIATED_RESET aresetn" *)
    input  logic        aclk,
    (* X_INTERFACE_INFO = "xilinx.com:signal:reset:1.0 aresetn RST" *)
    (* X_INTERFACE_PARAMETER = "POLARITY ACTIVE_LOW" *)
    input  logic        aresetn,
    input  logic [11:0] s_axil_awaddr,
    input  logic [2:0]  s_axil_awprot,
    input  logic        s_axil_awvalid,
    output logic        s_axil_awready,
    input  logic [31:0] s_axil_wdata,
    input  logic [3:0]  s_axil_wstrb,
    input  logic        s_axil_wvalid,
    output logic        s_axil_wready,
    output logic [1:0]  s_axil_bresp,
    output logic        s_axil_bvalid,
    input  logic        s_axil_bready,
    input  logic [11:0] s_axil_araddr,
    input  logic [2:0]  s_axil_arprot,
    input  logic        s_axil_arvalid,
    output logic        s_axil_arready,
    output logic [31:0] s_axil_rdata,
    output logic [1:0]  s_axil_rresp,
    output logic        s_axil_rvalid,
    input  logic        s_axil_rready,
    input  logic [31:0] s_axis_tdata,
    input  logic [3:0]  s_axis_tkeep,
    input  logic        s_axis_tlast,
    input  logic        s_axis_tvalid,
    output logic        s_axis_tready,
    output logic [31:0] m_axis_tdata,
    output logic [3:0]  m_axis_tkeep,
    output logic        m_axis_tlast,
    output logic        m_axis_tvalid,
    input  logic        m_axis_tready
);
    logic        mode, start;
    logic [11:0] coef [16];
    logic        busy, ready;
    logic [31:0] job_cycles, in_beats, out_beats;

    zb_accel_regs u_regs (
        .aclk(aclk), .aresetn(aresetn),
        .s_axil_awaddr, .s_axil_awprot, .s_axil_awvalid, .s_axil_awready, .s_axil_wdata, .s_axil_wstrb, .s_axil_wvalid,
        .s_axil_wready, .s_axil_bresp, .s_axil_bvalid, .s_axil_bready, .s_axil_araddr, .s_axil_arprot, .s_axil_arvalid,
        .s_axil_arready, .s_axil_rdata, .s_axil_rresp, .s_axil_rvalid, .s_axil_rready,
        .ctrl_mode_o(mode), .cmd_start_pulse_o(start), .status_busy_i(busy), .status_ready_i(ready),
        .job_cycles_value_i(job_cycles), .in_beats_value_i(in_beats), .out_beats_value_i(out_beats),
        .coef0_value_o(coef[0]), .coef1_value_o(coef[1]), .coef2_value_o(coef[2]), .coef3_value_o(coef[3]),
        .coef4_value_o(coef[4]), .coef5_value_o(coef[5]), .coef6_value_o(coef[6]), .coef7_value_o(coef[7]),
        .coef8_value_o(coef[8]), .coef9_value_o(coef[9]), .coef10_value_o(coef[10]), .coef11_value_o(coef[11]),
        .coef12_value_o(coef[12]), .coef13_value_o(coef[13]), .coef14_value_o(coef[14]), .coef15_value_o(coef[15]),
        .scratch_value_o()
    );

    // ---- CRC-32, one 32-bit beat per clock
    function automatic logic [31:0] crc_word(input logic [31:0] c, input logic [31:0] d);
        logic [31:0] r;
        r = c;
        for (int i = 0; i < 32; i++) r = (r >> 1) ^ ((r[0] ^ d[i]) ? 32'hEDB88320 : 32'h0);
        return r;
    endfunction

    // ---- FIR (fully parallel variant: one result per clock, so the DMA and not the filter sets the rate)
    logic        fir_rst, fir_busy, fir_c_valid, fir_c_ready, fir_c_last, fir_s_valid, fir_s_ready, fir_m_valid, fir_m_ready;
    logic signed [11:0] fir_c_data;
    logic signed [31:0] fir_m_data;
    fir #(.IMPL("lut_mult"), .TAPS(16), .DATA_W(16), .COEF_W(12), .FOLD(4)) u_fir (
        .clk(aclk), .rst(fir_rst), .busy(fir_busy),
        .c_valid(fir_c_valid), .c_ready(fir_c_ready), .c_data(fir_c_data), .c_last(fir_c_last),
        .s_valid(fir_s_valid), .s_ready(fir_s_ready), .s_data(s_axis_tdata[15:0]),
        .m_valid(fir_m_valid), .m_ready(fir_m_ready), .m_data(fir_m_data));

    typedef enum logic [2:0] {IDLE, F_RST, F_WAIT, F_LOAD, RUN, DRAIN} st_t;
    st_t         st;
    logic        job_mode;
    logic [31:0] crc;
    logic        crc_out_v;
    logic [4:0]  ci;
    logic [31:0] n_in, n_out, last_idx;
    logic        last_seen;

    assign busy  = (st != IDLE);
    assign ready = (st == RUN);

    // input side
    wire in_ok = (st == RUN) && !last_seen;
    assign s_axis_tready = job_mode ? (in_ok && fir_s_ready) : (in_ok && !crc_out_v);
    wire in_fire = s_axis_tvalid && s_axis_tready;
    assign fir_s_valid = job_mode && in_ok && s_axis_tvalid;

    // output side
    assign m_axis_tkeep  = 4'hF;
    assign m_axis_tvalid = job_mode ? fir_m_valid : crc_out_v;
    assign m_axis_tdata  = job_mode ? fir_m_data : ~crc;
    assign m_axis_tlast  = job_mode ? (last_seen && n_out == last_idx - 1) : 1'b1;
    assign fir_m_ready   = m_axis_tready;
    wire out_fire = m_axis_tvalid && m_axis_tready;

    // coefficient load beats
    assign fir_c_valid = (st == F_LOAD);
    assign fir_c_data  = coef[ci[3:0]];
    assign fir_c_last  = (ci == 5'd15);

    always_ff @(posedge aclk) begin
        fir_rst <= 1'b0;
        if (!aresetn) begin
            st <= IDLE; job_mode <= 1'b0; crc <= '1; crc_out_v <= 1'b0; ci <= '0; n_in <= '0; n_out <= '0; last_idx <= '0;
            last_seen <= 1'b0; job_cycles <= '0; in_beats <= '0; out_beats <= '0; fir_rst <= 1'b1;
        end else begin
            if (busy) job_cycles <= job_cycles + 32'd1;
            case (st)
                IDLE: if (start) begin
                    job_mode <= mode; job_cycles <= 32'd1; in_beats <= '0; out_beats <= '0; n_in <= '0; n_out <= '0;
                    last_seen <= 1'b0; crc <= '1; crc_out_v <= 1'b0; ci <= '0;
                    if (mode) begin fir_rst <= 1'b1; st <= F_RST; end else st <= RUN;
                end
                F_RST:  st <= F_WAIT;                         // rst is seen by the FIR in this clock
                F_WAIT: if (!fir_busy) st <= F_LOAD;
                F_LOAD: if (fir_c_ready) begin
                    ci <= ci + 5'd1;
                    if (ci == 5'd15) st <= RUN;
                end
                RUN: begin
                    if (in_fire) begin
                        n_in <= n_in + 32'd1; in_beats <= in_beats + 32'd1;
                        if (!job_mode) crc <= crc_word(crc, s_axis_tdata);
                        if (s_axis_tlast) begin
                            last_seen <= 1'b1; last_idx <= n_in + 32'd1;
                            if (!job_mode) crc_out_v <= 1'b1;
                        end
                    end
                    if (out_fire) begin
                        n_out <= n_out + 32'd1; out_beats <= out_beats + 32'd1;
                        if (job_mode ? m_axis_tlast : 1'b1) begin st <= IDLE; crc_out_v <= 1'b0; end
                    end
                end
                default: st <= IDLE;
            endcase
        end
    end
endmodule
