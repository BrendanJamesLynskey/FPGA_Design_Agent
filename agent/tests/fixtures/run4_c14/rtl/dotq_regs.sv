// dotq_regs: register map 0x00-0x0A of the shell window, GO pulse, READY flag.
module dotq_regs (
    input  logic        clk,
    input  logic        rst,
    input  logic [6:0]  win_addr,
    input  logic        win_wr,
    input  logic        win_rd,
    input  logic [31:0] win_wdata,
    output logic [31:0] win_rdata,
    // to the core
    output logic        go,
    output logic [63:0] act,
    output logic [63:0] wgt,
    output logic [31:0] bias,
    output logic [15:0] mult,
    output logic [4:0]  shift,
    output logic        relu,
    input  logic        done,
    input  logic [7:0]  y,
    input  logic [31:0] acc,
    output logic        ready
);
    logic [31:0] a_lo, a_hi, w_lo, w_hi;

    assign act = {a_hi, a_lo};
    assign wgt = {w_hi, w_lo};

    always_ff @(posedge clk) begin
        if (rst) begin
            a_lo  <= 32'd0;
            a_hi  <= 32'd0;
            w_lo  <= 32'd0;
            w_hi  <= 32'd0;
            bias  <= 32'd0;
            mult  <= 16'd0;
            shift <= 5'd1;
            relu  <= 1'b0;
            go    <= 1'b0;
            ready <= 1'b0;
        end else begin
            go <= 1'b0;
            if (done) ready <= 1'b1;
            if (win_wr) begin
                case (win_addr)
                    7'h00: a_lo  <= win_wdata;
                    7'h01: a_hi  <= win_wdata;
                    7'h02: w_lo  <= win_wdata;
                    7'h03: w_hi  <= win_wdata;
                    7'h04: bias  <= win_wdata;
                    7'h05: mult  <= win_wdata[15:0];
                    7'h06: begin
                        shift <= win_wdata[4:0];
                        relu  <= win_wdata[8];
                    end
                    7'h07: begin
                        go    <= 1'b1;
                        ready <= 1'b0;
                    end
                    default: ;
                endcase
            end
        end
    end

    always_ff @(posedge clk) begin
        if (rst) begin
            win_rdata <= 32'd0;
        end else if (win_rd) begin
            case (win_addr)
                7'h00: win_rdata <= a_lo;
                7'h01: win_rdata <= a_hi;
                7'h02: win_rdata <= w_lo;
                7'h03: win_rdata <= w_hi;
                7'h04: win_rdata <= bias;
                7'h05: win_rdata <= {16'd0, mult};
                7'h06: win_rdata <= {23'd0, relu, 3'd0, shift};
                7'h08: win_rdata <= ready ? {24'd0, y} : 32'd0;
                7'h09: win_rdata <= ready ? acc : 32'd0;
                7'h0A: win_rdata <= {31'd0, ready};
                default: win_rdata <= 32'd0;
            endcase
        end
    end
endmodule
