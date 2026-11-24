// adder_pipelined: integer adder/subtractor split into STAGES chunks, one chunk per clock (arith brief 139a, variant "pipelined").
//
// Function: as adder_ripple (arith/adder/spec.md). Latency STAGES clocks (1 <= STAGES <= WIDTH), throughput one operation per clock.
// Stage k adds bits [LO_k, HI_k) of the operands with the carry registered by stage k-1; the operands of the higher chunks and the finished
// lower chunks travel along in registers (the skew and de-skew registers). The carry out, the sum and the overflow flag appear together,
// STAGES clocks after the operands. There is no reset: the pipeline holds only data and nothing is valid until STAGES clocks have passed.
//
// Intended primitive use (stated before any Vivado run; not yet measured): one carry chain per chunk (CARRY4/CARRY8 cells for chunk width
// bits), flip-flops for the chunk carries and the skew registers, about WIDTH * (STAGES - 1) in each direction in total (a triangle each for
// the operands and for the finished sum bits), none of it in a DSP. The register depth costs flip-flops and latency, and buys a shorter
// carry path: the longest path is the chunk's chain, not the whole adder's.
module adder_pipelined #(
    parameter int WIDTH  = 32,
    parameter int STAGES = 4
) (
    input  logic             clk,
    input  logic [WIDTH-1:0] a,
    input  logic [WIDTH-1:0] b,
    input  logic             cin,
    input  logic             sub,
    output logic [WIDTH-1:0] s,
    output logic             co,
    output logic             ovf
);
    // verilator lint_off UNUSEDSIGNAL
    logic [WIDTH-1:0] be;
    logic             ce;
    assign be = b ^ {WIDTH{sub}};
    assign ce = cin ^ sub;

    for (genvar k = 0; k < STAGES; k++) begin : g_st
        localparam int LO = (k * WIDTH) / STAGES;
        localparam int HI = ((k + 1) * WIDTH) / STAGES;
        localparam int CW = HI - LO;
        logic [WIDTH-1:0] a_in, b_in, s_in;      // what stage k sees this clock
        logic             c_in;
        logic [WIDTH-1:0] a_q, b_q, s_q;         // registered for stage k+1
        logic             c_q;
        logic [CW:0]      sum;
        logic [WIDTH-1:0] s_nxt;
        if (k == 0) begin : g_in0
            assign a_in = a;
            assign b_in = be;
            assign s_in = '0;
            assign c_in = ce;
        end else begin : g_inn
            assign a_in = g_st[k-1].a_q;
            assign b_in = g_st[k-1].b_q;
            assign s_in = g_st[k-1].s_q;
            assign c_in = g_st[k-1].c_q;
        end
        assign sum = {1'b0, a_in[LO +: CW]} + {1'b0, b_in[LO +: CW]} + {{CW{1'b0}}, c_in};
        if (LO > 0) begin : g_lo
            assign s_nxt[LO-1:0] = s_in[LO-1:0];          // the chunks finished by earlier stages pass through
        end
        assign s_nxt[HI-1:LO] = sum[CW-1:0];
        if (HI < WIDTH) begin : g_hi
            assign s_nxt[WIDTH-1:HI] = s_in[WIDTH-1:HI];  // (zero: no later chunk is finished yet)
        end
        always_ff @(posedge clk) begin
            a_q <= a_in;
            b_q <= b_in;
            s_q <= s_nxt;
            c_q <= sum[CW];
        end
        if (k == STAGES - 1) begin : g_last
            logic ovf_q;
            always_ff @(posedge clk) ovf_q <= (a_in[WIDTH-1] == b_in[WIDTH-1]) && (sum[CW-1] != a_in[WIDTH-1]);
            assign ovf = ovf_q;
        end
    end

    assign s  = g_st[STAGES-1].s_q;
    assign co = g_st[STAGES-1].c_q;
    // verilator lint_on UNUSEDSIGNAL
endmodule
