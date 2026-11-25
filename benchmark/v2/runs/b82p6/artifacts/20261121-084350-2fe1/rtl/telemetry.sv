// telemetry: uptime, tick-phase count, one held frame, byte-serial CRC of the frame.
module telemetry (
    input  logic        clk,
    input  logic        rst,
    input  logic        tick,
    input  logic        start,
    input  logic        set_period,
    input  logic [15:0] period_val,
    input  logic        stop,
    input  logic        take,
    input  logic [15:0] cmds,
    input  logic [15:0] refused,
    input  logic [6:0]  tidx,
    output logic        on,
    output logic [15:0] period,
    output logic [31:0] uptime,
    output logic [15:0] fseq,
    output logic [31:0] tword,
    output logic [7:0]  tlen
);
    typedef enum logic [1:0] {B_IDLE, B_RUN, B_TRAIL} bst_t;
    bst_t        bst;
    logic        held;
    logic [15:0] phase;
    logic [7:0]  fb [0:16];
    logic [31:0] crc, crc_n;
    logic [4:0]  bi;
    logic [1:0]  k;
    logic [7:0]  crcb;

    wire [31:0] uptime_n = uptime + 32'd1;
    wire [15:0] phase_n  = phase + 16'd1;
    wire        due      = tick && on && (phase_n >= period);
    wire        due_new  = due && !held;

    crc32_engine u_crc (.c(crc), .d(fb[bi]), .n(crc_n));

    always_comb begin
        case (k)
            2'd0:    crcb = ~crc[7:0];
            2'd1:    crcb = ~crc[15:8];
            2'd2:    crcb = ~crc[23:16];
            default: crcb = ~crc[31:24];
        endcase
    end

    // control state
    always_ff @(posedge clk) begin
        if (rst) begin
            on     <= 1'b0;
            period <= 16'd100;
            uptime <= 32'd0;
            phase  <= 16'd0;
            fseq   <= 16'd0;
            held   <= 1'b0;
            bst    <= B_IDLE;
        end else begin
            if (tick) begin
                uptime <= uptime_n;
                if (on) phase <= due ? 16'd0 : phase_n;
            end
            if (due_new) begin
                held <= 1'b1;
                fseq <= fseq + 16'd1;
                bst  <= B_RUN;
            end else if (bst == B_RUN && bi == 5'd12) begin
                bst <= B_TRAIL;
            end else if (bst == B_TRAIL && k == 2'd3) begin
                bst <= B_IDLE;
            end
            if (start) begin
                on    <= 1'b1;
                phase <= 16'd0;
                if (set_period) period <= period_val;
            end
            if (stop) begin
                on   <= 1'b0;
                held <= 1'b0;
                bst  <= B_IDLE;
            end
            if (take) begin
                held <= 1'b0;
                bst  <= B_IDLE;
            end
        end
    end

    // frame buffer and CRC datapath (no reset: masked by held)
    always_ff @(posedge clk) begin
        if (due_new) begin
            fb[0]  <= 8'hC0;
            fb[1]  <= 8'h00;
            fb[2]  <= fseq[15:8];
            fb[3]  <= fseq[7:0];
            fb[4]  <= 8'd8;
            fb[5]  <= uptime_n[31:24];
            fb[6]  <= uptime_n[23:16];
            fb[7]  <= uptime_n[15:8];
            fb[8]  <= uptime_n[7:0];
            fb[9]  <= cmds[15:8];
            fb[10] <= cmds[7:0];
            fb[11] <= refused[15:8];
            fb[12] <= refused[7:0];
            crc    <= 32'hFFFFFFFF;
            bi     <= 5'd0;
            k      <= 2'd0;
        end else if (bst == B_RUN) begin
            crc <= crc_n;
            bi  <= bi + 5'd1;
            k   <= 2'd0;
        end else if (bst == B_TRAIL) begin
            fb[bi] <= crcb;
            bi     <= bi + 5'd1;
            k      <= k + 2'd1;
        end
    end

    assign tlen = held ? 8'd17 : 8'd0;

    // readback: written as always_comb so every simulator re-evaluates it when fb changes
    wire [8:0] base = {tidx, 2'b00};
    logic [7:0] tb [0:3];
    logic [8:0] tj;
    always_comb begin
        for (int n = 0; n < 4; n++) begin
            tj = base + 9'(n);
            if (held && tj < 9'd17) tb[n] = fb[tj[4:0]];
            else                    tb[n] = 8'h00;
        end
    end
    assign tword = {tb[0], tb[1], tb[2], tb[3]};
endmodule
