// Fixture for brief 227: the clock-frequency meter of research/228 section 8(e), reduced to a window of N = 8 reference cycles so that the formal
// flow can reach every state, with the status and result on ports (the requirements of a real meter sit on registers; see the report).
module freq_meter #(parameter int N = 8) (
    input  logic        clk_ref,
    input  logic        clk_in,       // asynchronous to clk_ref
    input  logic        rst_n,        // active low, synchronous to clk_ref
    input  logic        start,        // one-cycle request, clk_ref domain
    input  logic        reg_rd,       // read of the count, clk_ref domain
    output logic        busy,
    output logic        valid,
    output logic        ovf,
    output logic [31:0] count,
    output logic [31:0] reg_rdata,
    output logic        reg_rvalid
);
    logic [4:0]  win;
    logic [31:0] edges, last;
    logic [2:0]  sync;                 // 2-flop synchroniser of clk_in into clk_ref, then an edge detector
    wire         rise = sync[1] & ~sync[2];
    always_ff @(posedge clk_ref) begin
        if (!rst_n) begin
            sync <= '0; busy <= 1'b0; valid <= 1'b0; ovf <= 1'b0; win <= '0; edges <= '0; count <= '0; reg_rvalid <= 1'b0; reg_rdata <= '0;
        end else begin
            sync <= {sync[1:0], clk_in};
            reg_rvalid <= reg_rd;
            if (reg_rd) reg_rdata <= count;
            if (start && !busy) begin
                busy <= 1'b1; valid <= 1'b0; win <= '0; edges <= '0;
            end else if (busy) begin
                if (rise) edges <= (edges == 32'hFFFFFFFF) ? edges : edges + 1;
                if (rise && edges == 32'hFFFFFFFF) ovf <= 1'b1;
                if (win == N - 1) begin
                    busy <= 1'b0; valid <= 1'b1; count <= edges;
                end else win <= win + 1;
            end
        end
    end
endmodule
