// C10: asynchronous FIFO, Gray pointers through 2-flop ASYNC_REG chains (constrained: see the xdc), 16 x 16.
module cdcfx_c10 (input logic clk_a, input logic clk_b, input logic rst, input logic winc, input logic [15:0] wdata,
                  output logic wfull, input logic rinc, output logic [15:0] rdata, output logic rempty);
    localparam int AW = 4;
    logic [15:0] mem [2**AW];
    logic [AW:0] wbin = '0, wptr = '0, rbin = '0, rptr = '0;
    (* ASYNC_REG = "TRUE" *) logic [AW:0] wq1 = '0;
    (* ASYNC_REG = "TRUE" *) logic [AW:0] wq2 = '0;
    (* ASYNC_REG = "TRUE" *) logic [AW:0] rq1 = '0;
    (* ASYNC_REG = "TRUE" *) logic [AW:0] rq2 = '0;
    logic full = 1'b0, empty = 1'b1;
    always_ff @(posedge clk_a) begin wq1 <= rptr; wq2 <= wq1; end
    always_ff @(posedge clk_b) begin rq1 <= wptr; rq2 <= rq1; end
    wire [AW:0] wbn = wbin + (AW+1)'(winc & ~full);
    wire [AW:0] wgn = (wbn >> 1) ^ wbn;
    always_ff @(posedge clk_a) begin
        wbin <= wbn; wptr <= wgn;
        full <= wgn == {~wq2[AW:AW-1], wq2[AW-2:0]};
        if (winc && !full) mem[wbin[AW-1:0]] <= wdata;
    end
    wire [AW:0] rbn = rbin + (AW+1)'(rinc & ~empty);
    wire [AW:0] rgn = (rbn >> 1) ^ rbn;
    always_ff @(posedge clk_b) begin
        rbin <= rbn; rptr <= rgn;
        empty <= rgn == rq2;
    end
    assign wfull = full;
    assign rempty = empty;
    logic [15:0] rd_q = '0;
    always_ff @(posedge clk_b) if (rinc && !empty) rd_q <= mem[rbin[AW-1:0]];
    assign rdata = rd_q;
endmodule
