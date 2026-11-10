// Fixture for the contract-test generator (brief 27B P0): two AXI4-Lite registers (AW and W taken together).
// MUT: 9 answers writes with SLVERR, 10 drops bit 31 of CTRL.
module fx_axil_regs #(
    parameter int MUT = 0
) (
    input  logic        clk,
    input  logic        rst_n,
    input  logic [3:0]  s_axil_awaddr,
    input  logic        s_axil_awvalid,
    output logic        s_axil_awready,
    input  logic [31:0] s_axil_wdata,
    input  logic [3:0]  s_axil_wstrb,
    input  logic        s_axil_wvalid,
    output logic        s_axil_wready,
    output logic [1:0]  s_axil_bresp,
    output logic        s_axil_bvalid,
    input  logic        s_axil_bready,
    input  logic [3:0]  s_axil_araddr,
    input  logic        s_axil_arvalid,
    output logic        s_axil_arready,
    output logic [31:0] s_axil_rdata,
    output logic [1:0]  s_axil_rresp,
    output logic        s_axil_rvalid,
    input  logic        s_axil_rready
);
    logic [31:0] ctrl;
    wire do_w = s_axil_awvalid && s_axil_wvalid && !s_axil_bvalid;
    assign s_axil_awready = do_w;
    assign s_axil_wready  = do_w;
    assign s_axil_arready = !s_axil_rvalid;
    always_ff @(posedge clk) begin
        if (!rst_n) begin
            ctrl <= 32'h1;
            s_axil_bvalid <= 1'b0;
            s_axil_bresp <= 2'b00;
            s_axil_rvalid <= 1'b0;
            s_axil_rresp <= 2'b00;
            s_axil_rdata <= '0;
        end else begin
            if (do_w) begin
                if (s_axil_awaddr[3:2] == 2'd0) ctrl <= (MUT == 10) ? {1'b0, s_axil_wdata[30:0]} : s_axil_wdata;
                s_axil_bvalid <= 1'b1;
                s_axil_bresp <= (MUT == 9) ? 2'b10 : 2'b00;
            end else if (s_axil_bvalid && s_axil_bready) begin
                s_axil_bvalid <= 1'b0;
            end
            if (s_axil_arvalid && s_axil_arready) begin
                s_axil_rvalid <= 1'b1;
                s_axil_rdata <= (s_axil_araddr[3:2] == 2'd0) ? ctrl : 32'h0000_00A5;
            end else if (s_axil_rvalid && s_axil_rready) begin
                s_axil_rvalid <= 1'b0;
            end
        end
    end
endmodule
