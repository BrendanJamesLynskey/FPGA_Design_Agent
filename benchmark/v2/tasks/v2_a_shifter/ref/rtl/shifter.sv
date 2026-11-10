// shifter.sv: 32-bit shifter / rotator with a 6-bit amount, for v2_a_shifter.
module shifter (
    input  logic        clk,
    input  logic        rst,
    output logic [15:0] led,
    input  logic [6:0]  win_addr,
    input  logic        win_wr,
    input  logic        win_rd,
    input  logic [31:0] win_wdata,
    output logic [31:0] win_rdata
);
    logic [31:0] a, res;
    logic [5:0]  amt;
    logic [1:0]  mode;
    wire  [4:0]  r = amt[4:0];

    always_comb begin
        case (mode)
            2'd0:    res = amt[5] ? 32'd0 : a << r;
            2'd1:    res = amt[5] ? 32'd0 : a >> r;
            2'd2:    res = amt[5] ? {32{a[31]}} : 32'($signed(a) >>> r);
            default: res = (a << r) | (a >> (6'd32 - {1'b0, r}));
        endcase
    end

    always_ff @(posedge clk) begin
        if (rst) begin
            a <= '0; amt <= '0; mode <= '0; led <= '0;
        end else begin
            if (win_wr && win_addr == 7'h00) a <= win_wdata;
            if (win_wr && win_addr == 7'h01) begin
                amt  <= win_wdata[5:0];
                mode <= win_wdata[9:8];
            end
            led <= res[15:0];
        end
    end

    always_ff @(posedge clk) begin
        if (rst) win_rdata <= '0;
        else if (win_rd) begin
            case (win_addr)
                7'h00:   win_rdata <= a;
                7'h01:   win_rdata <= {22'd0, mode, 2'b00, amt};
                7'h02:   win_rdata <= res;
                default: win_rdata <= '0;
            endcase
        end
    end
endmodule
