// reg_map: window register decode. Read data is registered, valid the cycle after win_rd.
module reg_map (
    input  logic         clk,
    input  logic         rst,
    input  logic [6:0]   win_addr,
    input  logic         win_wr,
    input  logic         win_rd,
    input  logic [31:0]  win_wdata,
    output logic [31:0]  win_rdata,
    // to / from the core
    output logic         byte_valid,
    output logic [8:0]   byte_out,
    input  logic [3:0]   result,
    input  logic [7:0]   ptype,
    input  logic [15:0]  pseq,
    input  logic [15:0]  pay0,
    input  logic [31:0]  pay1,
    input  logic [15:0]  last_seq,
    input  logic         have,
    input  logic         busy,
    input  logic [111:0] ctrs
);
    logic [8:0] byte_reg;

    assign byte_valid = win_wr && (win_addr == 7'h00);
    assign byte_out   = win_wdata[8:0];

    always_ff @(posedge clk) begin
        if (rst) begin
            byte_reg <= 9'd0;
        end else if (byte_valid) begin
            byte_reg <= win_wdata[8:0];
        end
    end

    always_ff @(posedge clk) begin
        if (rst) begin
            win_rdata <= 32'd0;
        end else if (win_rd) begin
            case (win_addr)
                7'h00:   win_rdata <= {23'd0, byte_reg};
                7'h01:   win_rdata <= {28'd0, result};
                7'h02:   win_rdata <= {24'd0, ptype};
                7'h03:   win_rdata <= {16'd0, pseq};
                7'h04:   win_rdata <= {16'd0, pay0};
                7'h05:   win_rdata <= pay1;
                7'h06:   win_rdata <= {15'd0, have, last_seq};
                7'h07:   win_rdata <= {31'd0, busy};
                7'h10:   win_rdata <= {16'd0, ctrs[0*16 +: 16]};
                7'h11:   win_rdata <= {16'd0, ctrs[1*16 +: 16]};
                7'h12:   win_rdata <= {16'd0, ctrs[2*16 +: 16]};
                7'h13:   win_rdata <= {16'd0, ctrs[3*16 +: 16]};
                7'h14:   win_rdata <= {16'd0, ctrs[4*16 +: 16]};
                7'h15:   win_rdata <= {16'd0, ctrs[5*16 +: 16]};
                7'h16:   win_rdata <= {16'd0, ctrs[6*16 +: 16]};
                default: win_rdata <= 32'd0;
            endcase
        end
    end

    /* verilator lint_off UNUSEDSIGNAL */
    logic unused_ok;
    assign unused_ok = &{1'b0, win_wdata[31:9]};
    /* verilator lint_on UNUSEDSIGNAL */
endmodule
