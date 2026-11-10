// Fixture for the contract-test generator (brief 27B P0): three registers behind the test shell's window.
// MUT: 7 gives CTRL the wrong reset value, 8 makes the read-only ID writable.
module fx_win_regs #(
    parameter int MUT = 0
) (
    input  logic        clk,
    input  logic        rst,
    input  logic [6:0]  win_addr,
    input  logic        win_wr,
    input  logic        win_rd,
    input  logic [31:0] win_wdata,
    output logic [31:0] win_rdata
);
    logic [31:0] id, scratch;
    logic [3:0]  ctrl;
    always_ff @(posedge clk) begin
        if (rst) begin
            id <= 32'h4658_0001;
            ctrl <= (MUT == 7) ? 4'h4 : 4'h5;
            scratch <= '0;
        end else if (win_wr) begin
            case (win_addr)
                7'h00: if (MUT == 8) id <= win_wdata;
                7'h01: ctrl <= win_wdata[3:0];
                7'h02: scratch <= win_wdata;
                default: ;
            endcase
        end
    end
    always_ff @(posedge clk) begin
        if (win_rd) begin
            case (win_addr)
                7'h00: win_rdata <= id;
                7'h01: win_rdata <= {28'h0, ctrl};
                7'h02: win_rdata <= scratch;
                default: win_rdata <= '0;
            endcase
        end
    end
endmodule
