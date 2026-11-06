// c15_rmsnorm_unit_regs.sv: the shell window of course task c15_rmsnorm_unit.
module c15_rmsnorm_unit_regs (
    input  logic        clk,
    input  logic        rst,
    output logic [15:0] led,
    input  logic [6:0]  win_addr,
    input  logic        win_wr,
    input  logic        win_rd,
    input  logic [31:0] win_wdata,
    output logic [31:0] win_rdata
);
    logic [255:0] x_r;
    logic [255:0] o_w;
    logic go, ov, vld;
    
    assign led = {15'd0, vld};

    rmsnorm_unit #(.N(16)) u_core (.clk(clk), .rst_n(!rst), .in_valid(go), .x(x_r), .out_valid(ov), .y(o_w));

    always_ff @(posedge clk) begin
        go <= 1'b0;
        if (ov) vld <= 1'b1;
        if (win_wr) begin
            if (win_addr < 7'd8) x_r[win_addr*32 +: 32] <= win_wdata;
            else if (win_addr == 7'h10) begin go <= 1'b1; vld <= 1'b0; end
        end
        win_rdata <= 32'd0;
        if (win_rd) begin
            if (win_addr < 7'd8) win_rdata <= x_r[win_addr*32 +: 32];
            else if (win_addr == 7'h11) win_rdata <= {31'd0, vld};
            else if (win_addr >= 7'h20 && win_addr < 7'd40) win_rdata <= vld ? o_w[(win_addr - 7'h20)*32 +: 32] : 32'd0;
        end
        if (rst) begin x_r <= '0; go <= 1'b0; vld <= 1'b0; win_rdata <= 32'd0; end
    end
endmodule
