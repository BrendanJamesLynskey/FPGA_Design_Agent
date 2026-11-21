// divider_hr_pipe: radix-4 SRT divider with a carry-save remainder, unrolled, PIPE digit steps per pipeline stage (brief 139c).
//   Same function as divider_hr_iter. One result per clock; latency ceil((K + 1) / PIPE) + 1 (the last stage is the fix: us + uc, and the add-back).
// Primitive use (intended, not yet measured): K + 1 carry-save steps (a LUT3 row of W + 3 bits and a 7-bit estimate adder each; the first step
// has constant control), PIPE of them in series per stage, then one W + 3 bit and one W + 1 bit adder. Flip-flops per stage: two remainder words,
// the divisor, Q and Q - 1.
module divider_hr_pipe #(
    parameter int W    = 16,
    parameter int K    = 8,
    parameter int PIPE = 1                // digit steps per register stage, 1 to K + 1
) (
    input  logic                clk,
    input  logic                rst,
    input  logic                in_valid,
    output logic                in_ready,
    input  logic [W-1:0]        a,
    input  logic [W-1:0]        b,
    output logic                out_valid,
    output logic [2*K:0]        quo,
    output logic [W-1:0]        rem
);
    localparam int WW = W + 3;
    localparam int QW = 2 * K + 1;
    localparam int NS = K + 1;
    localparam int S  = (NS + PIPE - 1) / PIPE;

    logic [WW-1:0] us_q [S];
    logic [WW-1:0] uc_q [S];
    logic [W-1:0]  b_q  [S];
    logic [QW-1:0] qq_q [S];
    logic [QW-1:0] qm_q [S];
    logic [S:0]    v_q;
    logic [QW-1:0] quo_f;
    logic [W-1:0]  rem_f;

    assign in_ready = 1'b1;

    for (genvar s = 0; s < S; s++) begin : g_stage
        localparam int IT = (NS - s * PIPE < PIPE) ? (NS - s * PIPE) : PIPE;
        logic [WW-1:0] us_i, uc_i, us_c, uc_c;
        logic [W-1:0]  b_i;
        logic [QW-1:0] qq_i, qm_i, qq_c, qm_c;
        logic          v_i;
        if (s == 0) begin : g_first
            assign us_i = {{3{1'b0}}, a};
            assign uc_i = '0;
            assign b_i  = b;
            assign qq_i = '0;
            assign qm_i = '1;
            assign v_i  = in_valid;
        end else begin : g_next
            assign us_i = us_q[s-1];
            assign uc_i = uc_q[s-1];
            assign b_i  = b_q[s-1];
            assign qq_i = qq_q[s-1];
            assign qm_i = qm_q[s-1];
            assign v_i  = v_q[s-1];
        end
        // the steps of this stage in series; step index t = s * PIPE + n, the first division step is t = 0
        for (genvar n = 0; n < IT; n++) begin : g_step
            logic [WW-1:0] us_in, uc_in, us_o, uc_o;
            logic [QW-1:0] qq_in, qm_in, qq_o, qm_o;
            logic [2:0]    dig;
            if (n == 0) begin : g_in
                assign us_in = us_i;
                assign uc_in = uc_i;
                assign qq_in = qq_i;
                assign qm_in = qm_i;
            end else begin : g_in
                assign us_in = g_step[n-1].us_o;
                assign uc_in = g_step[n-1].uc_o;
                assign qq_in = g_step[n-1].qq_o;
                assign qm_in = g_step[n-1].qm_o;
            end
            divider_hr_cs_step #(.W(W)) u_step (.first(1'(s * PIPE + n == 0)), .us(us_in), .uc(uc_in), .b(b_i), .us_n(us_o), .uc_n(uc_o), .q(dig));
            divider_hr_otf #(.QW(QW)) u_otf (.q(dig), .qi(qq_in), .qmi(qm_in), .qo(qq_o), .qmo(qm_o));
        end
        assign us_c = g_step[IT-1].us_o;
        assign uc_c = g_step[IT-1].uc_o;
        assign qq_c = g_step[IT-1].qq_o;
        assign qm_c = g_step[IT-1].qm_o;
        always_ff @(posedge clk) begin
            us_q[s] <= us_c;
            uc_q[s] <= uc_c;
            b_q[s]  <= b_i;
            qq_q[s] <= qq_c;
            qm_q[s] <= qm_c;
        end
        always_ff @(posedge clk) begin
            if (rst) v_q[s] <= 1'b0;
            else     v_q[s] <= v_i;
        end
    end

    divider_hr_fix #(.W(W), .QW(QW), .CS(1'b1)) u_fix (.us(us_q[S-1]), .uc(uc_q[S-1]), .b(b_q[S-1]), .qq(qq_q[S-1]), .qm(qm_q[S-1]), .quo(quo_f), .rem(rem_f));
    always_ff @(posedge clk) begin
        quo <= quo_f;
        rem <= rem_f;
    end
    always_ff @(posedge clk) begin
        if (rst) v_q[S] <= 1'b0;
        else     v_q[S] <= v_q[S-1];
    end
    assign out_valid = v_q[S];
endmodule
