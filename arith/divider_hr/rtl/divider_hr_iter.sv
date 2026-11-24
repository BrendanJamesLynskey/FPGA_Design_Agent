// divider_hr_iter: radix-4 SRT divider with a carry-save remainder, one quotient digit (two bits) per clock (brief 139c).
//   a, b: W-bit normalised significands (MSB set). quo = floor(a * 4**K / b) (2K + 1 bits), rem = a * 4**K - quo * b (W bits), 0 <= rem < b.
//   in_ready is high while idle; K + 1 digit steps (the first is the integer digit), one clock to fix the result; latency K + 3, one division per
//   K + 3 clocks.
// Primitive use (intended, not yet measured): per step one LUT3 per bit for the 3:2 compressor with the +-b / +-2b select folded in, a 7-bit
// adder for the digit estimate (two CARRY4), no carry chain across the W-bit remainder; at the end one W + 3 bit adder (us + uc) and one W + 1 bit
// adder (+ b). Flip-flops: two remainder words, divisor, Q and Q-1, output registers, counter.
module divider_hr_iter #(
    parameter int W = 16,                 // operand width, 7 or more
    parameter int K = 8                   // fractional radix-4 digits, 1 or more
) (
    input  logic                clk,
    input  logic                rst,
    input  logic                in_valid,
    output logic                in_ready,
    input  logic [W-1:0]        a,
    input  logic [W-1:0]        b,
    output logic                out_valid,   // one clock, K + 3 clocks after the accepting edge
    output logic [2*K:0]        quo,
    output logic [W-1:0]        rem
);
    localparam int WW = W + 3;
    localparam int QW = 2 * K + 1;
    localparam int CW = $clog2(K + 2);

    logic              busy, first, fin;
    logic [CW-1:0]     cnt;
    logic [WW-1:0]     us, uc, us_n, uc_n;
    logic [W-1:0]      bb;
    logic [QW-1:0]     qq, qm, qq_n, qm_n, quo_f;
    logic [W-1:0]      rem_f;
    logic [2:0]        dig;

    assign in_ready = ~busy;

    divider_hr_cs_step #(.W(W)) u_step (.first, .us, .uc, .b(bb), .us_n, .uc_n, .q(dig));
    divider_hr_otf #(.QW(QW)) u_otf (.q(dig), .qi(qq), .qmi(qm), .qo(qq_n), .qmo(qm_n));
    divider_hr_fix #(.W(W), .QW(QW), .CS(1'b1)) u_fix (.us, .uc, .b(bb), .qq, .qm, .quo(quo_f), .rem(rem_f));

    always_ff @(posedge clk) begin
        if (rst) begin
            busy      <= 1'b0;
            fin       <= 1'b0;
            out_valid <= 1'b0;
            first     <= 1'b0;
            cnt       <= '0;
        end else begin
            out_valid <= 1'b0;
            fin       <= 1'b0;
            if (in_valid && in_ready) begin
                busy  <= 1'b1;
                first <= 1'b1;
                cnt   <= '0;
            end else if (busy && !fin) begin
                first <= 1'b0;
                cnt   <= cnt + 1'b1;
                if (cnt == CW'(K)) fin <= 1'b1;
            end else if (fin) begin
                busy      <= 1'b0;
                out_valid <= 1'b1;
            end
        end
    end

    always_ff @(posedge clk) begin        // data path: no reset
        if (in_valid && in_ready) begin
            us <= {{3{1'b0}}, a};
            uc <= '0;
            bb <= b;
            qq <= '0;
            qm <= '1;
        end else if (busy && !fin) begin
            us <= us_n;
            uc <= uc_n;
            qq <= qq_n;
            qm <= qm_n;
        end
        if (fin) begin
            quo <= quo_f;
            rem <= rem_f;
        end
    end
endmodule
