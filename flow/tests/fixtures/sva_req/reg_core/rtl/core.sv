// reg_core: a scratch register behind a register port (fixture of brief 218): a write is visible on h_rdata one clock later.
module reg_core (
    input  logic        clk,
    input  logic        rst,
    input  logic        h_we,
    input  logic [11:0] h_addr,
    input  logic [31:0] h_wdata,
    output logic [31:0] h_rdata
);
    always_ff @(posedge clk) begin
        if (rst) h_rdata <= 32'd0;
        else if (h_we && h_addr == 12'h008) h_rdata <= h_wdata;
    end
endmodule
