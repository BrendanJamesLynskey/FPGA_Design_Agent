// sat_add.sv: 16-bit adder with signed/unsigned mode, optional saturation and flags, for v2_a_sat_add.
module sat_add (
    input  logic        clk,
    input  logic        rst,
    output logic [15:0] led,
    input  logic [6:0]  win_addr,
    input  logic        win_wr,
    input  logic        win_rd,
    input  logic [31:0] win_wdata,
    output logic [31:0] win_rdata
);
    logic [15:0] a, b;
    logic        sgn, sat;

    wire [16:0] raw   = {1'b0, a} + {1'b0, b};
    wire        ovf_u = raw[16];
    wire        ovf_s = (a[15] == b[15]) && (raw[15] != a[15]);
    wire        ovf   = sgn ? ovf_s : ovf_u;
    wire [15:0] satv  = sgn ? (a[15] ? 16'h8000 : 16'h7FFF) : 16'hFFFF;
    wire [15:0] sum   = (sat && ovf) ? satv : raw[15:0];
    wire [2:0]  flags = {sum[15], sum == 16'd0, ovf};

    always_ff @(posedge clk) begin
        if (rst) begin
            a <= '0; b <= '0; sgn <= 1'b0; sat <= 1'b0; led <= '0;
        end else begin
            if (win_wr && win_addr == 7'h00) a <= win_wdata[15:0];
            if (win_wr && win_addr == 7'h01) b <= win_wdata[15:0];
            if (win_wr && win_addr == 7'h02) begin
                sgn <= win_wdata[0];
                sat <= win_wdata[1];
            end
            led <= sum;
        end
    end

    always_ff @(posedge clk) begin
        if (rst) win_rdata <= '0;
        else if (win_rd) begin
            case (win_addr)
                7'h00:   win_rdata <= 32'(a);
                7'h01:   win_rdata <= 32'(b);
                7'h02:   win_rdata <= {30'd0, sat, sgn};
                7'h03:   win_rdata <= 32'(sum);
                7'h04:   win_rdata <= 32'(flags);
                default: win_rdata <= '0;
            endcase
        end
    end
endmodule
