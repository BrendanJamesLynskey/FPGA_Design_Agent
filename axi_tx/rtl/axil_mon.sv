// axil_mon: passive performance and coverage counters for one AXI4-Lite interface (brief 59A). Port-only, like axil_rules.
// Latency is counted per transaction for up to 4 outstanding transactions per direction (AXI4-Lite answers in order):
// a write from the first cycle of the earlier of its AW and W transfers to the cycle of its B handshake, a read from the
// first cycle of its AR transfer to its R handshake. Counters are 32-bit and saturate; clear zeroes them.
// Read-out by index (rd_sel, valid the cycle after it changes); axi_tx/host/regs.py names every index:
//   0 cycles out of reset           1-5 handshakes AW W B AR R        6-10 stall cycles (VALID high, READY low) AW W B AR R
//   11-35 READY-wait bins, channel c (AW W B AR R) x bin b: 11 + 5c + b, bins 0, 1, 2-3, 4-15, 16+ cycles
//   36-39 BRESP OKAY EXOKAY SLVERR DECERR      40-43 RRESP the same      44-46 WSTRB full, partial, zero
//   47-49 write order at the ports (which VALID rose first, n-th AW paired with n-th W): AW first, W first, same cycle
//   50-53 write latency count, min, max, sum     54-61 write latency bins 0-3 4-7 8-15 16-31 32-63 64-127 128-255 256+
//   62-65 read latency count, min, max, sum      66-73 read latency bins      74 max writes outstanding  75 max reads
/* verilator lint_off UNUSEDSIGNAL */   // the busy flags of the B and R channels are not used (no transfer starts there)
module axil_mon #(
    parameter int DATA_W = 32
) (
    input  logic                aclk,
    input  logic                aresetn,
    input  logic                clear,
    input  logic                awvalid,
    input  logic                awready,
    input  logic [DATA_W/8-1:0] wstrb,
    input  logic                wvalid,
    input  logic                wready,
    input  logic [1:0]          bresp,
    input  logic                bvalid,
    input  logic                bready,
    input  logic                arvalid,
    input  logic                arready,
    input  logic [1:0]          rresp,
    input  logic                rvalid,
    input  logic                rready,
    input  logic [6:0]          rd_sel,
    output logic [31:0]         rd_data
);
    localparam int NC = 76;
    localparam int SW = DATA_W / 8;
    logic [NC-1:0][31:0] cnt;                    // packed: reset and updated in loops (Verilator 5.020 BLKLOOPINIT)
    logic [31:0] now = '0;

    wire [4:0] v  = {rvalid, arvalid, bvalid, wvalid, awvalid};
    wire [4:0] r  = {rready, arready, bready, wready, awready};
    wire [4:0] hs = v & r;
    wire awhs = hs[0], whs = hs[1], bhs = hs[2], arhs = hs[3], rhs = hs[4];

    // cycles each channel's current transfer has waited for READY
    logic [4:0][4:0] wait_c;
    logic [4:0] busy = '0;                       // VALID was high without READY last cycle
    function automatic logic [2:0] wbin(input logic [4:0] w);
        if (w == 0) wbin = 3'd0; else if (w == 1) wbin = 3'd1; else if (w < 4) wbin = 3'd2;
        else if (w < 16) wbin = 3'd3; else wbin = 3'd4;
    endfunction
    function automatic logic [2:0] lbin(input logic [31:0] l);
        if (l < 4) lbin = 3'd0; else if (l < 8) lbin = 3'd1; else if (l < 16) lbin = 3'd2; else if (l < 32) lbin = 3'd3;
        else if (l < 64) lbin = 3'd4; else if (l < 128) lbin = 3'd5; else if (l < 256) lbin = 3'd6; else lbin = 3'd7;
    endfunction

    // start-time FIFOs (depth 4): AW starts, W starts, AR starts
    logic [31:0] aw_t [4], w_t [4], ar_t [4];
    logic [1:0]  aw_wp = '0, aw_rp = '0, w_wp = '0, w_rp = '0, ar_wp = '0, ar_rp = '0;
    logic [2:0]  aw_n = '0, w_n = '0, ar_n = '0;
    wire aw_start = awvalid && !busy[0], w_start = wvalid && !busy[1], ar_start = arvalid && !busy[3];
    // order: signed difference of AW and W transfers started so far (pairing the n-th AW with the n-th W)
    logic signed [7:0] d_aw_w = '0;
    logic [7:0] out_w = '0, out_r = '0;          // outstanding (handshaken address, no response yet)

    wire [31:0] w_lat = now - ((aw_t[aw_rp] < w_t[w_rp]) ? aw_t[aw_rp] : w_t[w_rp]);
    wire [31:0] r_lat = now - ar_t[ar_rp];
    wire        w_lat_ok = bhs && aw_n != 0 && w_n != 0;
    wire        r_lat_ok = rhs && ar_n != 0;
    // the latency statistics take the measured latency one cycle later (timing: the subtraction, the bin compare and the
    // counter enables do not fit one 10 ns cycle on the Artix-7 -1; brief 59A's first build failed setup by 0.88 ns here)
    logic        w_ev = 1'b0, r_ev = 1'b0;
    logic [31:0] w_lq = '0, r_lq = '0;
    always_ff @(posedge aclk) begin
        w_ev <= w_lat_ok && aresetn && !clear; w_lq <= w_lat;
        r_ev <= r_lat_ok && aresetn && !clear; r_lq <= r_lat;
    end

    logic [NC-1:0] inc;
    always_comb begin
        inc = '0;
        inc[0] = 1'b1;
        for (int c = 0; c < 5; c++) begin
            if (hs[c]) inc[1 + c] = 1'b1;
            if (v[c] && !r[c]) inc[6 + c] = 1'b1;
            if (hs[c]) inc[11 + 5 * c + 32'(wbin(wait_c[c]))] = 1'b1;
        end
        if (bhs) inc[36 + 32'(bresp)] = 1'b1;
        if (rhs) inc[40 + 32'(rresp)] = 1'b1;
        if (whs) inc[(wstrb == {SW{1'b1}}) ? 44 : (wstrb == '0) ? 46 : 45] = 1'b1;
        if (aw_start && w_start)          inc[(d_aw_w == 0) ? 49 : (d_aw_w > 0) ? 47 : 48] = 1'b1;
        else if (aw_start && d_aw_w < 0)  inc[48] = 1'b1;
        else if (w_start  && d_aw_w > 0)  inc[47] = 1'b1;
        if (w_ev) begin inc[50] = 1'b1; inc[54 + 32'(lbin(w_lq))] = 1'b1; end
        if (r_ev) begin inc[62] = 1'b1; inc[66 + 32'(lbin(r_lq))] = 1'b1; end
    end

    initial begin
        for (int i = 0; i < NC; i++) cnt[i] = '0;
        cnt[51] = 32'hFFFF_FFFF; cnt[63] = 32'hFFFF_FFFF;
        for (int i = 0; i < 5; i++) wait_c[i] = '0;
        for (int i = 0; i < 4; i++) begin aw_t[i] = '0; w_t[i] = '0; ar_t[i] = '0; end
    end

    always_ff @(posedge aclk) begin
        if (clear) begin
            for (int i = 0; i < NC; i++) cnt[i] <= '0;
            cnt[51] <= 32'hFFFF_FFFF; cnt[63] <= 32'hFFFF_FFFF;
        end else if (aresetn) begin
            for (int i = 0; i < NC; i++)
                if (inc[i] && i != 51 && i != 52 && i != 53 && i != 63 && i != 64 && i != 65 && cnt[i] != 32'hFFFF_FFFF)
                    cnt[i] <= cnt[i] + 1'b1;
            if (w_ev) begin
                if (w_lq < cnt[51]) cnt[51] <= w_lq;
                if (w_lq > cnt[52]) cnt[52] <= w_lq;
                cnt[53] <= cnt[53] + w_lq;
            end
            if (r_ev) begin
                if (r_lq < cnt[63]) cnt[63] <= r_lq;
                if (r_lq > cnt[64]) cnt[64] <= r_lq;
                cnt[65] <= cnt[65] + r_lq;
            end
            if (32'(out_w) > cnt[74]) cnt[74] <= 32'(out_w);
            if (32'(out_r) > cnt[75]) cnt[75] <= 32'(out_r);
        end
    end

    always_ff @(posedge aclk) begin
        if (!aresetn || clear) begin
            now <= '0; busy <= '0; d_aw_w <= '0; out_w <= '0; out_r <= '0;
            aw_wp <= '0; aw_rp <= '0; aw_n <= '0; w_wp <= '0; w_rp <= '0; w_n <= '0; ar_wp <= '0; ar_rp <= '0; ar_n <= '0;
            for (int i = 0; i < 5; i++) wait_c[i] <= '0;
        end else begin
            now  <= now + 1'b1;
            busy <= v & ~r;
            for (int c = 0; c < 5; c++)
                if (hs[c] || !v[c]) wait_c[c] <= '0;
                else if (wait_c[c] != 5'h1F) wait_c[c] <= wait_c[c] + 1'b1;
            d_aw_w <= d_aw_w + (aw_start ? 8'sd1 : 8'sd0) - (w_start ? 8'sd1 : 8'sd0);
            out_w  <= out_w + (awhs ? 8'd1 : 8'd0) - ((bhs && out_w != 0) ? 8'd1 : 8'd0);
            out_r  <= out_r + (arhs ? 8'd1 : 8'd0) - ((rhs && out_r != 0) ? 8'd1 : 8'd0);
            // start FIFOs: push at the first cycle of a transfer, pop at the response
            if (aw_start && aw_n != 4) begin aw_t[aw_wp] <= now; aw_wp <= aw_wp + 1'b1; end
            if (w_start  && w_n  != 4) begin w_t[w_wp]   <= now; w_wp  <= w_wp + 1'b1;  end
            if (ar_start && ar_n != 4) begin ar_t[ar_wp] <= now; ar_wp <= ar_wp + 1'b1; end
            if (w_lat_ok) begin aw_rp <= aw_rp + 1'b1; w_rp <= w_rp + 1'b1; end
            if (r_lat_ok) ar_rp <= ar_rp + 1'b1;
            aw_n <= aw_n + ((aw_start && aw_n != 4) ? 3'd1 : 3'd0) - (w_lat_ok ? 3'd1 : 3'd0);
            w_n  <= w_n  + ((w_start  && w_n  != 4) ? 3'd1 : 3'd0) - (w_lat_ok ? 3'd1 : 3'd0);
            ar_n <= ar_n + ((ar_start && ar_n != 4) ? 3'd1 : 3'd0) - (r_lat_ok ? 3'd1 : 3'd0);
        end
    end

    always_ff @(posedge aclk) rd_data <= (rd_sel < 7'(NC)) ? cnt[rd_sel] : 32'h0;
endmodule
/* verilator lint_on UNUSEDSIGNAL */
