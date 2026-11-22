// divider_hr_cpa: radix-4 SRT divider with a carry-propagate remainder, one quotient digit (two bits) per clock (brief 139c).
//   Same function, interface and timing as divider_hr_iter (latency K + 3, one division per K + 3 clocks) but the partial remainder is an ordinary
//   W + 1 bit binary number: one adder per step instead of a 3:2 compressor, no carry-propagate add of two words at the end.
// Primitive use (intended, not yet measured): per step one (W+3)-bit adder (ceil((W+3)/4) CARRY4) in series with the digit selection; the
// carry chain is on the critical path of every step, which the carry-save version avoids at the cost of a second remainder register and a final adder.
module divider_hr_cpa #(
    parameter int W = 16,
    parameter int K = 8
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
    localparam int QW = 2 * K + 1;
    localparam int CW = $clog2(K + 2);

    logic              busy, first, fin;
    logic [CW-1:0]     cnt;
    logic [W:0]        ur, u_n;
    logic [W-1:0]      bb;
    logic [QW-1:0]     qq, qm, qq_n, qm_n, quo_f;
    logic [W-1:0]      rem_f;
    logic [2:0]        dig;

    assign in_ready = ~busy;

    divider_hr_cpa_step #(.W(W)) u_step (.first, .u(ur), .b(bb), .u_n, .q(dig));
    divider_hr_otf #(.QW(QW)) u_otf (.q(dig), .qi(qq), .qmi(qm), .qo(qq_n), .qmo(qm_n));
    divider_hr_fix #(.W(W), .QW(QW), .CS(1'b0)) u_fix (.us({2'b00, ur}), .uc('0), .b(bb), .qq, .qm, .quo(quo_f), .rem(rem_f));

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
            ur  <= {1'b0, a};
            bb <= b;
            qq <= '0;
            qm <= '1;
        end else if (busy && !fin) begin
            ur  <= u_n;
            qq <= qq_n;
            qm <= qm_n;
        end
        if (fin) begin
            quo <= quo_f;
            rem <= rem_f;
        end
    end
endmodule
