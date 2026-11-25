// M12 (brief 189, idea from Edwards 2026, ch 12): the C10 asynchronous FIFO with the pointers crossed as plain binary
// counts instead of Gray codes. Several pointer bits change on one increment, so when each bit of the crossing may take
// a different number of destination cycles, the other domain can see a pointer value the writer never held (a torn
// pointer). A zero-delay simulation cannot show it: every bit arrives on the same edge.
module cdcfx_m12 (input logic clk_a, input logic clk_b, input logic rst, input logic winc, input logic [15:0] wdata,
                  output logic wfull, input logic rinc, output logic [15:0] rdata, output logic rempty);
    localparam int AW = 4;
    logic [15:0] mem [2**AW];
    logic [AW:0] wbin = '0, rbin = '0;
    (* ASYNC_REG = "TRUE" *) logic [AW:0] wq1 = '0;      // read pointer, seen from the write domain (binary)
    (* ASYNC_REG = "TRUE" *) logic [AW:0] wq2 = '0;
    (* ASYNC_REG = "TRUE" *) logic [AW:0] rq1 = '0;      // write pointer, seen from the read domain (binary)
    (* ASYNC_REG = "TRUE" *) logic [AW:0] rq2 = '0;
    logic full = 1'b0, empty = 1'b1;
    always_ff @(posedge clk_a) begin wq1 <= rbin; wq2 <= wq1; end
    always_ff @(posedge clk_b) begin rq1 <= wbin; rq2 <= rq1; end
    wire [AW:0] wbn = wbin + (AW+1)'(winc & ~full);
    always_ff @(posedge clk_a) begin
        wbin <= wbn;
        full <= wbn == {~wq2[AW], wq2[AW-1:0]};
        if (winc && !full) mem[wbin[AW-1:0]] <= wdata;
    end
    wire [AW:0] rbn = rbin + (AW+1)'(rinc & ~empty);
    always_ff @(posedge clk_b) begin
        rbin <= rbn;
        empty <= rbn == rq2;
    end
    assign wfull = full;
    assign rempty = empty;
    logic [15:0] rd_q = '0;
    always_ff @(posedge clk_b) if (rinc && !empty) rd_q <= mem[rbin[AW-1:0]];
    assign rdata = rd_q;
endmodule
