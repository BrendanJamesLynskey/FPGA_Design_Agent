// prio_enc.sv: 16-request priority encoder with a mask, for v2_a_prio_enc.
module prio_enc (
    input  logic        clk,
    input  logic        rst,
    input  logic [15:0] sw_async,
    output logic [15:0] led,
    input  logic [6:0]  win_addr,
    input  logic        win_wr,
    input  logic        win_rd,
    input  logic [31:0] win_wdata,
    output logic [31:0] win_rdata
);
    logic [15:0] s1, req, mask, grant;
    logic [3:0]  idx;
    logic        valid;

    wire [15:0] eff = req & ~mask;

    always_comb begin
        idx = 4'hF; valid = 1'b0; grant = '0;
        for (int i = 0; i < 16; i++) begin
            if (eff[i]) begin
                idx   = i[3:0];
                valid = 1'b1;
                grant = 16'd1 << i;
            end
        end
    end

    always_ff @(posedge clk) begin
        s1  <= sw_async;
        req <= s1;
        if (rst) begin
            mask <= '0; led <= '0;
        end else begin
            if (win_wr && win_addr == 7'h01) mask <= win_wdata[15:0];
            led <= grant;
        end
    end

    always_ff @(posedge clk) begin
        if (rst) win_rdata <= '0;
        else if (win_rd) begin
            case (win_addr)
                7'h00:   win_rdata <= 32'(req);
                7'h01:   win_rdata <= 32'(mask);
                7'h02:   win_rdata <= {27'd0, valid, idx};
                default: win_rdata <= '0;
            endcase
        end
    end
endmodule
