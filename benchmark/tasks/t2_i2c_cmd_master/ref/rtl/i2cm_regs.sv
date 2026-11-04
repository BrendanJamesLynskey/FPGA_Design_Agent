// i2cm_regs.sv: CMD / STATUS / RXDATA / INFO of the byte-command I2C master.
module i2cm_regs #(
    parameter int QUARTER = 250
) (
    input  logic        clk,
    input  logic        rst,
    input  logic        scl_in,
    input  logic        sda_in,
    output logic        scl_oe,
    output logic        sda_oe,
    input  logic [6:0]  win_addr,
    input  logic        win_wr,
    input  logic        win_rd,
    input  logic [31:0] win_wdata,
    output logic [31:0] win_rdata
);
    logic       busy, owned, nack;
    logic [7:0] rxdata;

    i2cm_core #(.QUARTER(QUARTER)) u_core (
        .clk(clk), .rst(rst), .go(win_wr && win_addr == 7'h00), .op(win_wdata[2:0]), .wdata(win_wdata[15:8]),
        .rnack(win_wdata[16]), .scl_in(scl_in), .sda_in(sda_in), .scl_oe(scl_oe), .sda_oe(sda_oe),
        .busy(busy), .owned(owned), .nack(nack), .rxdata(rxdata));

    always_ff @(posedge clk) begin
        if (rst) win_rdata <= '0;
        else if (win_rd) begin
            case (win_addr)
                7'h01:   win_rdata <= {29'd0, owned, nack, busy};
                7'h02:   win_rdata <= {24'd0, rxdata};
                7'h03:   win_rdata <= 32'(QUARTER & 16'hFFFF);
                default: win_rdata <= '0;
            endcase
        end
    end
endmodule
