// telemetry.sv: uptime, period counter and the (at most one) held telemetry frame.
module telemetry #(
    parameter logic [15:0] PERIOD_RESET = 16'd100,
    parameter logic [15:0] PERIOD_MIN   = 16'd4,
    parameter logic [31:0] CRC_POLY     = 32'hEDB88320,
    parameter logic [31:0] CRC_INIT     = 32'hFFFFFFFF
) (
    input  logic        clk,
    input  logic        rst,
    input  logic        tick,
    input  logic        start,
    input  logic [15:0] start_period,
    input  logic        stop,
    input  logic        take,
    input  logic [15:0] cmds16,
    input  logic [15:0] refused16,
    input  logic [6:0]  tidx,
    output logic [31:0] uptime,
    output logic [15:0] period,
    output logic        tel_on,
    output logic [15:0] fcount,
    output logic [5:0]  tlen,
    output logic [31:0] tword,
    output logic        busy
);
    typedef enum logic [1:0] {T_IDLE, T_CRC, T_FIN} tstate_t;
    tstate_t tstate;

    logic [15:0] tickc;
    logic [15:0] fseq;
    logic        held;
    logic        ready;
    logic [7:0]  tf [0:16];
    logic [4:0]  ti;
    logic [31:0] crc;
    logic [31:0] crc_nxt;

    crc32_byte #(.POLY(CRC_POLY)) u_crc (.crc_in(crc), .data(tf[ti]), .crc_out(crc_nxt));

    wire [31:0] up_next = uptime + 32'd1;
    wire [15:0] tc_next = tickc + 16'd1;
    wire        due     = tick && tel_on && (tc_next >= period);

    // Control registers: reset.
    always_ff @(posedge clk) begin
        if (rst) begin
            uptime <= 32'd0;
            period <= PERIOD_RESET;
            tel_on <= 1'b0;
            tickc  <= 16'd0;
            fseq   <= 16'd0;
            fcount <= 16'd0;
            held   <= 1'b0;
            ready  <= 1'b0;
            tstate <= T_IDLE;
        end else begin
            if (tick) begin
                uptime <= up_next;
                if (tel_on) tickc <= due ? 16'd0 : tc_next;
            end
            if (due && !held) begin
                held   <= 1'b1;
                fseq   <= fseq + 16'd1;
                fcount <= fcount + 16'd1;
                tstate <= T_CRC;
            end
            case (tstate)
                T_CRC:   if (ti == 5'd12) tstate <= T_FIN;
                T_FIN:   begin ready <= 1'b1; tstate <= T_IDLE; end
                default: ;
            endcase
            if (start) begin
                tel_on <= 1'b1;
                tickc  <= 16'd0;
                if (start_period != 16'd0)
                    period <= (start_period < PERIOD_MIN) ? PERIOD_MIN : start_period;
            end
            if (stop || take) begin
                held   <= 1'b0;
                ready  <= 1'b0;
                tstate <= T_IDLE;
                if (stop) tel_on <= 1'b0;
            end
        end
    end

    // Datapath: frame bytes and CRC, no reset.
    always_ff @(posedge clk) begin
        if (due && !held) begin
            tf[0]  <= 8'hC0;
            tf[1]  <= 8'h00;
            tf[2]  <= fseq[15:8];
            tf[3]  <= fseq[7:0];
            tf[4]  <= 8'd8;
            tf[5]  <= up_next[31:24];
            tf[6]  <= up_next[23:16];
            tf[7]  <= up_next[15:8];
            tf[8]  <= up_next[7:0];
            tf[9]  <= cmds16[15:8];
            tf[10] <= cmds16[7:0];
            tf[11] <= refused16[15:8];
            tf[12] <= refused16[7:0];
            crc    <= CRC_INIT;
            ti     <= 5'd0;
        end else if (tstate == T_CRC) begin
            crc <= crc_nxt;
            ti  <= ti + 5'd1;
        end else if (tstate == T_FIN) begin
            tf[13] <= ~crc[7:0];
            tf[14] <= ~crc[15:8];
            tf[15] <= ~crc[23:16];
            tf[16] <= ~crc[31:24];
        end
    end

    assign tlen = ready ? 6'd17 : 6'd0;
    assign busy = (tstate != T_IDLE);

    always_comb begin
        logic [8:0] j;
        logic [7:0] bv [0:3];
        for (int k = 0; k < 4; k++) begin
            j = {tidx, 2'b00} + 9'(k);
            bv[k] = (ready && j < 9'd17) ? tf[j[4:0]] : 8'h00;
        end
        tword = {bv[0], bv[1], bv[2], bv[3]};
    end
endmodule
