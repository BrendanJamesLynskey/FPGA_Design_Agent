// c13_hough_lines_regs.sv: the shell window of course task c13_hough_lines.
module c13_hough_lines_regs (
    input  logic        clk,
    input  logic        rst,
    output logic [15:0] led,
    input  logic [6:0]  win_addr,
    input  logic        win_wr,
    input  logic        win_rd,
    input  logic [31:0] win_wdata,
    output logic [31:0] win_rdata
);
    logic        pt_v, clr, busy;
    logic [7:0]  pt_x, pt_y;
    logic [3:0]  rd_theta;
    logic [6:0]  rd_rho;
    logic [15:0] rd_cnt;

    assign led = {15'd0, busy};

    hough #(.NT(16), .NR(96), .ROFF(48)) u_core (.clk(clk), .rst_n(!rst), .pt_valid(pt_v), .pt_x(pt_x), .pt_y(pt_y), .busy(busy),
                                                  .clear(clr), .rd_theta(rd_theta), .rd_rho(rd_rho), .rd_cnt(rd_cnt));

    always_ff @(posedge clk) begin
        pt_v <= 1'b0; clr <= 1'b0;
        if (win_wr) begin
            case (win_addr)
                7'd0: begin pt_x <= win_wdata[7:0]; pt_y <= win_wdata[15:8]; pt_v <= 1'b1; end
                7'd1: clr <= 1'b1;
                7'd2: begin rd_theta <= win_wdata[3:0]; rd_rho <= win_wdata[14:8]; end
                default: ;
            endcase
        end
        win_rdata <= 32'd0;
        if (win_rd) begin
            case (win_addr)
                7'd2: win_rdata <= {17'd0, rd_rho, 4'd0, rd_theta};
                7'd3: win_rdata <= {16'd0, rd_cnt};
                7'd4: win_rdata <= {31'd0, busy};
                default: ;
            endcase
        end
        if (rst) begin pt_v <= 1'b0; clr <= 1'b0; rd_theta <= '0; rd_rho <= '0; win_rdata <= 32'd0; end
    end
endmodule
