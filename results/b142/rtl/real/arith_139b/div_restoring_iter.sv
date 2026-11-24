// div_restoring_iter: unsigned W-bit restoring divider, one quotient bit per clock (brief 139b). Interface and latency: ../spec.md.
//   n / d -> q, r; d = 0 gives q = all ones, r = n. in_ready is high while idle; one result per W + 1 clocks.
// Primitive use (intended, not yet measured by Vivado): one (W+1)-bit subtractor = ceil((W+1)/4) CARRY4 (CARRY8 on UltraScale+) whose
// borrow is the quotient bit and the select of the restore mux (one LUT per partial-remainder bit); the partial remainder, the shared
// dividend/quotient shift register and the divisor are plain FDRE; no DSP, no block RAM. Clock enables come from the busy flag.
module div_restoring_iter #(
    parameter int W = 8                   // operand width, 2 or more
) (
    input  logic         clk,
    input  logic         rst,             // synchronous, active high
    input  logic         in_valid,
    output logic         in_ready,
    input  logic [W-1:0] n,
    input  logic [W-1:0] d,
    output logic         out_valid,       // one clock, W + 1 clocks after the accepting edge
    output logic [W-1:0] q,
    output logic [W-1:0] r
);
    localparam int CW = $clog2(W + 1);

    logic          busy;
    logic [CW-1:0] cnt;
    logic [W-1:0]  rn;                    // dividend bits still to come (top) and quotient bits so far (bottom)
    logic [W-1:0]  dd;
    logic [W-1:0]  p;                     // partial remainder (below the divisor, so W bits)
    logic [W-1:0]  sh;                    // 2p + next dividend bit: below 2**W, because p is below 2**(iterations done)
    logic [W:0]    t;

    assign in_ready = ~busy;
    assign sh = {p[W-2:0], rn[W-1]};   // p[W-1] is zero before every iteration (a prefix of n of fewer than W bits)
    assign t  = {1'b0, sh} - {1'b0, dd};  // t[W] = borrow: the trial subtraction failed
    assign q  = rn;
    assign r  = p;

    always_ff @(posedge clk) begin
        if (rst) begin
            busy      <= 1'b0;
            out_valid <= 1'b0;
            cnt       <= '0;
        end else begin
            out_valid <= 1'b0;
            if (in_valid && in_ready) begin
                busy <= 1'b1;
                cnt  <= '0;
            end else if (busy) begin
                cnt <= cnt + 1'b1;
                if (cnt == CW'(W - 1)) begin
                    busy      <= 1'b0;
                    out_valid <= 1'b1;
                end
            end
        end
    end

    always_ff @(posedge clk) begin        // data path: no reset (every use is gated by out_valid)
        if (in_valid && in_ready) begin
            rn <= n;
            dd <= d;
            p  <= '0;
        end else if (busy) begin
            p  <= t[W] ? sh : t[W-1:0];
            rn <= {rn[W-2:0], ~t[W]};
        end
    end
endmodule
