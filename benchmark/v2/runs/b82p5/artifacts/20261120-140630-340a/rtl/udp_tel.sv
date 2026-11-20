// Telemetry: tick burst generator, tick (uptime) count, period counter, one held frame with its CRC-32.
module udp_tel #(
    parameter int          DEFAULT_PERIOD_TICKS = 100,
    parameter int          MIN_PERIOD_TICKS     = 4,
    parameter logic [31:0] CRC_POLY             = 32'hEDB88320,
    parameter logic [31:0] CRC_INIT             = 32'hFFFFFFFF
) (
    input  logic        clk,
    input  logic        rst,
    input  logic        tick_we,
    input  logic [7:0]  tick_n,
    input  logic        take,
    input  logic        start_p,
    input  logic [15:0] start_per,
    input  logic        stop_p,
    input  logic [15:0] cmds16,
    input  logic [15:0] refused16,
    input  logic        tidx_we,
    input  logic [6:0]  tidx_wd,
    output logic [6:0]  tidx,
    output logic        tel_on,
    output logic [15:0] period,
    output logic [31:0] uptime,
    output logic [15:0] fcount,
    output logic        held,
    output logic [31:0] tword
);
    typedef enum logic [1:0] {T_IDLE, T_WALK, T_TRL} tstate_t;

    tstate_t     tstate;
    logic [7:0]  burst;
    logic [15:0] pc;
    logic [3:0]  ti;
    logic [7:0]  tbuf [0:31];
    logic [31:0] tcrc, tcrc_n;

    wire        tick = (burst != 8'd0);
    wire [31:0] up_n = uptime + 32'd1;
    wire [15:0] pc_n = pc + 16'd1;
    wire        hit  = tel_on && tick && (pc_n == period);
    wire        due  = hit && !held;
    wire [31:0] fin  = ~tcrc;

    crc32_byte #(.CRC_POLY(CRC_POLY)) u_crc (.crc_i(tcrc), .d(tbuf[{1'b0, ti}]), .crc_o(tcrc_n));

    // control and counters (reset)
    always_ff @(posedge clk) begin
        if (rst) begin
            burst  <= 8'd0;
            pc     <= 16'd0;
            uptime <= 32'd0;
            fcount <= 16'd0;
            held   <= 1'b0;
            tel_on <= 1'b0;
            period <= 16'(DEFAULT_PERIOD_TICKS);
            tstate <= T_IDLE;
            ti     <= 4'd0;
            tidx   <= 7'd0;
        end else begin
            if (tick) begin
                burst  <= burst - 8'd1;
                uptime <= up_n;
            end
            if (tick_we) burst <= tick_n;          // a write restarts the burst
            if (tel_on && tick) pc <= hit ? 16'd0 : pc_n;
            if (tidx_we) tidx <= tidx_wd;

            case (tstate)
                T_WALK: begin
                    if (ti == 4'd12) tstate <= T_TRL;
                    else             ti <= ti + 4'd1;
                end
                T_TRL:   tstate <= T_IDLE;
                default: ;
            endcase

            if (take) begin
                held   <= 1'b0;
                tstate <= T_IDLE;
            end
            if (due) begin
                held   <= 1'b1;
                fcount <= fcount + 16'd1;
                tstate <= T_WALK;
                ti     <= 4'd0;
            end
            if (stop_p) begin
                tel_on <= 1'b0;
                held   <= 1'b0;
                tstate <= T_IDLE;
            end
            if (start_p) begin
                tel_on <= 1'b1;
                pc     <= 16'd0;
                if (start_per != 16'd0)
                    period <= (start_per < 16'(MIN_PERIOD_TICKS)) ? 16'(MIN_PERIOD_TICKS) : start_per;
            end
        end
    end

    // frame bytes and CRC (datapath, no reset)
    always_ff @(posedge clk) begin
        if (due) begin
            tbuf[0]  <= 8'hC0;
            tbuf[1]  <= 8'h00;
            tbuf[2]  <= fcount[15:8];
            tbuf[3]  <= fcount[7:0];
            tbuf[4]  <= 8'd8;
            tbuf[5]  <= up_n[31:24];
            tbuf[6]  <= up_n[23:16];
            tbuf[7]  <= up_n[15:8];
            tbuf[8]  <= up_n[7:0];
            tbuf[9]  <= cmds16[15:8];
            tbuf[10] <= cmds16[7:0];
            tbuf[11] <= refused16[15:8];
            tbuf[12] <= refused16[7:0];
            tcrc     <= CRC_INIT;
        end else if (tstate == T_WALK) begin
            tcrc <= tcrc_n;
        end
        if (tstate == T_TRL) begin
            tbuf[13] <= fin[7:0];
            tbuf[14] <= fin[15:8];
            tbuf[15] <= fin[23:16];
            tbuf[16] <= fin[31:24];
        end
    end

    // word read: bytes 4i..4i+3, first byte on top, zero past the end or when nothing is held
    always_comb begin
        tword = 32'h0;
        for (int k = 0; k < 4; k++) begin
            logic [8:0] idx;
            idx = {tidx, 2'b00} + 9'(k);
            if (held && idx < 9'd17) tword[31 - 8 * k -: 8] = tbuf[idx[4:0]];
        end
    end
endmodule
