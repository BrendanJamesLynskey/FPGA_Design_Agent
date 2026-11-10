// bit_count.sv: population count, leading-zero count and bit reverse of a 32-bit word, for v2_a_bit_count.
module bit_count (
    input  logic        clk,
    input  logic        rst,
    output logic [15:0] led,
    input  logic [6:0]  win_addr,
    input  logic        win_wr,
    input  logic        win_rd,
    input  logic [31:0] win_wdata,
    output logic [31:0] win_rdata
);
    logic [31:0] w, rev;
    logic [5:0]  pop, lzc;

    always_comb begin
        lzc = 6'd32; pop = '0;
        for (int i = 0; i < 32; i++) begin
            if (w[i]) pop = pop + 6'd1;
            if (w[i]) lzc = 6'(31 - i);
            rev[i] = w[31 - i];
        end
    end

    always_ff @(posedge clk) begin
        if (rst) begin
            w <= '0; led <= 16'd0;
        end else begin
            if (win_wr && win_addr == 7'h00) w <= win_wdata;
            led <= 16'(pop);
        end
    end

    always_ff @(posedge clk) begin
        if (rst) win_rdata <= '0;
        else if (win_rd) begin
            case (win_addr)
                7'h00:   win_rdata <= w;
                7'h01:   win_rdata <= 32'(pop);
                7'h02:   win_rdata <= 32'(lzc);
                7'h03:   win_rdata <= rev;
                default: win_rdata <= '0;
            endcase
        end
    end
endmodule
