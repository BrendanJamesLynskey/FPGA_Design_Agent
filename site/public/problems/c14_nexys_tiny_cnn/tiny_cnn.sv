// Part 14 lesson 10 exercise: a whole tiny CNN in RTL, one multiply-accumulate unit, bit-exact against the numpy integer model (tools/ml_models.int_forward).
//
// The network (12 x 12 grey image, int8 values 0 .. 127) is   conv 3x3, 1 -> 4 channels, ReLU, requantise   (4 x 10 x 10)
//                                                             max-pool 2 x 2                                 (4 x 5 x 5)
//                                                             conv 3x3, 4 -> 8 channels, ReLU, requantise   (8 x 3 x 3)
//                                                             dense 72 -> 4, raw int32 logits (no requantisation); cls = index of the largest (the lowest index wins a tie).
// Layout, all row-major with the channel first: image[y*12 + x]; conv1 weights w[oc*9 + ky*3 + kx]; conv2 weights w[oc*36 + ic*9 + ky*3 + kx]; dense weights w[o*72 + i] where i is the
// flatten index c*9 + y*3 + x of the 8 x 3 x 3 map. A layer output y = clamp(requant(acc), 0, 127) with requant(acc) = (acc * M + 2^(S-1)) >>> S (M unsigned 16 bit, S 1 .. 31).
//
// Loading (any time while busy = 0): write ld_we = 1 with ld_sel and ld_addr, ld_data (the low bits are used, as signed numbers):
//   ld_sel 0: weight memory, addresses 0 .. 611 (conv1 0 .. 35, conv2 36 .. 323, dense 324 .. 611), 8-bit signed;
//   ld_sel 1: bias memory, addresses 0 .. 15 (conv1 0 .. 3, conv2 4 .. 11, dense 12 .. 15), 32-bit signed;
//   ld_sel 2: configuration, address 0 = M1, 1 = S1, 2 = M2, 3 = S2;
//   ld_sel 3: image, addresses 0 .. 143, 8-bit signed.
// Run: start = 1 for one clock (while busy = 0) begins an inference; busy is high until done pulses high for one clock; then logits[k*32 +: 32] (signed) and cls hold the result
// until the next start. The weights and the image stay loaded.
module tiny_cnn (
    input  logic          clk,
    input  logic          rst_n,
    input  logic          ld_we,
    input  logic [1:0]    ld_sel,
    input  logic [9:0]    ld_addr,
    input  logic [31:0]   ld_data,
    input  logic          start,
    output logic          busy,
    output logic          done,
    output logic [127:0]  logits,
    output logic [1:0]    cls
);
    logic signed [7:0]  wmem [0:611];
    logic signed [31:0] bmem [0:15];
    logic [15:0]        cfg_m1, cfg_m2;
    logic [4:0]         cfg_s1, cfg_s2;
    logic signed [7:0]  img [0:143];
    logic signed [7:0]  a1  [0:399];
    logic signed [7:0]  p1  [0:99];
    logic signed [7:0]  a2  [0:71];
    logic signed [31:0] lg  [0:3];

    always_ff @(posedge clk) begin
        if (ld_we) begin
            case (ld_sel)
                2'd0: wmem[ld_addr] <= ld_data[7:0];
                2'd1: bmem[ld_addr[3:0]] <= ld_data;
                2'd2: case (ld_addr[1:0])
                          2'd0: cfg_m1 <= ld_data[15:0];
                          2'd1: cfg_s1 <= ld_data[4:0];
                          2'd2: cfg_m2 <= ld_data[15:0];
                          default: cfg_s2 <= ld_data[4:0];
                      endcase
                default: img[ld_addr[7:0]] <= ld_data[7:0];
            endcase
        end
    end

    // ---- layer 1: conv, 1 -> 4, 12 x 12 -> 10 x 10
    logic l1_start, l1_done, l1_we;
    logic [15:0] l1_ia, l1_wa, l1_oa;
    logic [7:0]  l1_ba;
    logic signed [31:0] l1_od;
    mac_layer #(.CIN(1), .COUT(4), .IH(12), .IW(12), .K(3), .WB(0), .BB(0), .RAW(0)) u_l1 (
        .clk, .rst_n, .start(l1_start), .done(l1_done), .in_addr(l1_ia), .in_data(img[l1_ia[7:0]]), .w_addr(l1_wa), .w_data(wmem[l1_wa[9:0]]),
        .b_addr(l1_ba), .b_data(bmem[l1_ba[3:0]]), .mult(cfg_m1), .shift(cfg_s1), .out_we(l1_we), .out_addr(l1_oa), .out_data(l1_od));
    always_ff @(posedge clk) if (l1_we) a1[l1_oa[8:0]] <= l1_od[7:0];

    // ---- pool: 4 x 10 x 10 -> 4 x 5 x 5
    logic pl_start, pl_done, pl_we;
    logic [15:0] pl_ia, pl_oa;
    logic signed [7:0] pl_od;
    pool_layer #(.C(4), .IH(10), .IW(10)) u_pl (
        .clk, .rst_n, .start(pl_start), .done(pl_done), .in_addr(pl_ia), .in_data(a1[pl_ia[8:0]]), .out_we(pl_we), .out_addr(pl_oa), .out_data(pl_od));
    always_ff @(posedge clk) if (pl_we) p1[pl_oa[6:0]] <= pl_od;

    // ---- layer 2: conv, 4 -> 8, 5 x 5 -> 3 x 3
    logic l2_start, l2_done, l2_we;
    logic [15:0] l2_ia, l2_wa, l2_oa;
    logic [7:0]  l2_ba;
    logic signed [31:0] l2_od;
    mac_layer #(.CIN(4), .COUT(8), .IH(5), .IW(5), .K(3), .WB(36), .BB(4), .RAW(0)) u_l2 (
        .clk, .rst_n, .start(l2_start), .done(l2_done), .in_addr(l2_ia), .in_data(p1[l2_ia[6:0]]), .w_addr(l2_wa), .w_data(wmem[l2_wa[9:0]]),
        .b_addr(l2_ba), .b_data(bmem[l2_ba[3:0]]), .mult(cfg_m2), .shift(cfg_s2), .out_we(l2_we), .out_addr(l2_oa), .out_data(l2_od));
    always_ff @(posedge clk) if (l2_we) a2[l2_oa[6:0]] <= l2_od[7:0];

    // ---- layer 3: dense 72 -> 4 (a convolution with K = 1 over a 1 x 1 map), raw logits
    logic l3_start, l3_done, l3_we;
    logic [15:0] l3_ia, l3_wa, l3_oa;
    logic [7:0]  l3_ba;
    logic signed [31:0] l3_od;
    mac_layer #(.CIN(72), .COUT(4), .IH(1), .IW(1), .K(1), .WB(324), .BB(12), .RAW(1)) u_l3 (
        .clk, .rst_n, .start(l3_start), .done(l3_done), .in_addr(l3_ia), .in_data(a2[l3_ia[6:0]]), .w_addr(l3_wa), .w_data(wmem[l3_wa[9:0]]),
        .b_addr(l3_ba), .b_data(bmem[l3_ba[3:0]]), .mult(16'd0), .shift(5'd1), .out_we(l3_we), .out_addr(l3_oa), .out_data(l3_od));
    always_ff @(posedge clk) if (l3_we) lg[l3_oa[1:0]] <= l3_od;

    // ---- sequencer
    typedef enum logic [2:0] {IDLE, S1, SP, S2, S3, FIN} st_t;
    st_t st;
    assign busy = (st != IDLE);
    always_ff @(posedge clk) begin
        l1_start <= 1'b0; pl_start <= 1'b0; l2_start <= 1'b0; l3_start <= 1'b0; done <= 1'b0;
        if (!rst_n) st <= IDLE;
        else case (st)
            IDLE: if (start) begin st <= S1; l1_start <= 1'b1; end
            S1:   if (l1_done) begin st <= SP; pl_start <= 1'b1; end
            SP:   if (pl_done) begin st <= S2; l2_start <= 1'b1; end
            S2:   if (l2_done) begin st <= S3; l3_start <= 1'b1; end
            S3:   if (l3_done) begin st <= FIN; end
            FIN:  begin st <= IDLE; done <= 1'b1; end
            default: st <= IDLE;
        endcase
    end
    always_comb begin
        for (int k = 0; k < 4; k++) logits[k*32 +: 32] = lg[k];
        cls = 2'd0;
        for (int k = 1; k < 4; k++) if (lg[k] > lg[cls]) cls = 2'(k);
    end
endmodule

// A sequential convolution / dense layer: one MAC per clock. For every output (oc, oy, ox): load the bias, accumulate CIN*K*K products, then (unless RAW) requantise
// with mult and shift and clamp to 0 .. 127 (the ReLU), and write. Reads are combinational (in_addr -> in_data and w_addr -> w_data in the same clock).
module mac_layer #(
    parameter int CIN = 1, COUT = 1, IH = 4, IW = 4, K = 3, WB = 0, BB = 0, RAW = 0
) (
    input  logic                clk,
    input  logic                rst_n,
    input  logic                start,
    output logic                done,
    output logic [15:0]         in_addr,
    input  logic signed [7:0]   in_data,
    output logic [15:0]         w_addr,
    input  logic signed [7:0]   w_data,
    output logic [7:0]          b_addr,
    input  logic signed [31:0]  b_data,
    input  logic [15:0]         mult,
    input  logic [4:0]          shift,
    output logic                out_we,
    output logic [15:0]         out_addr,
    output logic signed [31:0]  out_data
);
    localparam int OH = IH - K + 1, OW = IW - K + 1;
    typedef enum logic [1:0] {IDLE, INIT, MAC, WR} st_t;
    st_t st;
    int oc, oy, ox, ic, ky, kx;
    logic signed [31:0] acc;
    assign in_addr = 16'(ic * IH * IW + (oy + ky) * IW + ox + kx);
    assign w_addr  = 16'(WB + oc * CIN * K * K + ic * K * K + ky * K + kx);
    assign b_addr  = 8'(BB + oc);
    assign out_addr = 16'(oc * OH * OW + oy * OW + ox);
    logic signed [63:0] p, r, rnd;
    always_comb begin
        p = acc * $signed({1'b0, mult});
        rnd = 64'sd1 <<< (shift - 5'd1);
        r = (p + rnd) >>> shift;
        if (RAW) out_data = acc;
        else if (r > 64'sd127) out_data = 32'sd127;
        else if (r < 64'sd0) out_data = 32'sd0;
        else out_data = r[31:0];
    end
    assign out_we = (st == WR);
    always_ff @(posedge clk) begin
        done <= 1'b0;
        if (!rst_n) st <= IDLE;
        else case (st)
            IDLE: if (start) begin oc <= 0; oy <= 0; ox <= 0; st <= INIT; end
            INIT: begin acc <= b_data; ic <= 0; ky <= 0; kx <= 0; st <= MAC; end
            MAC: begin
                acc <= acc + in_data * w_data;
                if (kx == K - 1) begin
                    kx <= 0;
                    if (ky == K - 1) begin
                        ky <= 0;
                        if (ic == CIN - 1) st <= WR;
                        else ic <= ic + 1;
                    end else ky <= ky + 1;
                end else kx <= kx + 1;
            end
            WR: begin
                if (ox == OW - 1) begin
                    ox <= 0;
                    if (oy == OH - 1) begin
                        oy <= 0;
                        if (oc == COUT - 1) begin st <= IDLE; done <= 1'b1; end
                        else begin oc <= oc + 1; st <= INIT; end
                    end else begin oy <= oy + 1; st <= INIT; end
                end else begin ox <= ox + 1; st <= INIT; end
            end
        endcase
    end
endmodule

// 2 x 2 max-pool, stride 2, over C maps of IH x IW values (read from a memory, written to another), four reads per output.
module pool_layer #(
    parameter int C = 1, IH = 4, IW = 4
) (
    input  logic                clk,
    input  logic                rst_n,
    input  logic                start,
    output logic                done,
    output logic [15:0]         in_addr,
    input  logic signed [7:0]   in_data,
    output logic                out_we,
    output logic [15:0]         out_addr,
    output logic signed [7:0]   out_data
);
    localparam int OH = IH / 2, OW = IW / 2;
    typedef enum logic [1:0] {IDLE, RD, WR} st_t;
    st_t st;
    int c, y, x, k;
    logic signed [7:0] m;
    assign in_addr = 16'(c * IH * IW + (2 * y + k / 2) * IW + 2 * x + (k % 2));
    assign out_addr = 16'(c * OH * OW + y * OW + x);
    assign out_we = (st == WR);
    assign out_data = m;
    always_ff @(posedge clk) begin
        done <= 1'b0;
        if (!rst_n) st <= IDLE;
        else case (st)
            IDLE: if (start) begin c <= 0; y <= 0; x <= 0; k <= 0; st <= RD; end
            RD: begin
                m <= (k == 0 || in_data > m) ? in_data : m;
                if (k == 3) st <= WR;
                else k <= k + 1;
            end
            WR: begin
                k <= 0;
                st <= RD;
                if (x == OW - 1) begin
                    x <= 0;
                    if (y == OH - 1) begin
                        y <= 0;
                        if (c == C - 1) begin st <= IDLE; done <= 1'b1; end
                        else c <= c + 1;
                    end else y <= y + 1;
                end else x <= x + 1;
            end
            default: st <= IDLE;
        endcase
    end
endmodule
