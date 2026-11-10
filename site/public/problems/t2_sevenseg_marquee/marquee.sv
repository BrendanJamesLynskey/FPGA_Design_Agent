// marquee.sv: 16-byte raw-segment message, an 8-digit window that wraps
// modulo LENGTH, scrolling every SCROLL_CYCLES, and a dimmed digit scan.
module marquee #(
    parameter int SCROLL_CYCLES = 25_000_000,
    parameter int REFRESH_BITS  = 17
) (
    input  logic        clk,
    input  logic        rst,
    output logic [7:0]  an,
    output logic [7:0]  seg_n,        // {DP, G, F, E, D, C, B, A}, active low
    input  logic [6:0]  win_addr,
    input  logic        win_wr,
    input  logic        win_rd,
    input  logic [31:0] win_wdata,
    output logic [31:0] win_rdata
);
    localparam int SW = $clog2(SCROLL_CYCLES + 1);

    logic [7:0]  msg [16];
    logic [1:0]  ctrl;
    logic [4:0]  len;
    logic [3:0]  pos;
    logic [2:0]  dim;
    logic [SW-1:0] sc;

    wire wr_ctrl = win_wr && win_addr == 7'h00;
    wire wr_len  = win_wr && win_addr == 7'h01 && win_wdata[4:0] != 5'd0 && win_wdata[31:0] <= 32'd16;
    wire wr_pos  = win_wr && win_addr == 7'h02 && win_wdata[31:0] < {27'd0, len};
    wire step    = ctrl[0] && sc == SW'(SCROLL_CYCLES - 1);

    always_ff @(posedge clk) begin
        if (rst) begin
            for (int i = 0; i < 16; i++) msg[i] <= 8'h00;
            ctrl <= '0; len <= 5'd8; pos <= '0; dim <= 3'd7; sc <= '0;
        end else begin
            if (win_wr && win_addr[6:4] == 3'b001) msg[win_addr[3:0]] <= win_wdata[7:0];
            if (wr_ctrl) ctrl <= win_wdata[1:0];
            if (win_wr && win_addr == 7'h03) dim <= win_wdata[2:0];
            // scroll counter
            if (wr_ctrl || wr_pos || !ctrl[0] || step) sc <= '0;
            else                                     sc <= sc + 1'b1;
            // position
            if (wr_len) begin
                len <= win_wdata[4:0];
                if (win_wdata[4:0] <= {1'b0, pos}) pos <= '0;
            end else if (wr_pos) begin
                pos <= win_wdata[3:0];
            end else if (step) begin
                if (!ctrl[1]) pos <= ({1'b0, pos} + 5'd1 >= len) ? 4'd0 : pos + 1'b1;
                else          pos <= (pos == 4'd0) ? 4'(len - 5'd1) : pos - 1'b1;
            end
        end
    end

    // display scan. The message index of each digit comes from a short pipeline instead of a modulo:
    // dix[7] = POS (the leftmost digit), dix[k-1] = dix[k] + 1 wrapped at LENGTH. Each stage is one
    // increment and compare, so a change of POS or LENGTH settles within 8 clocks (far inside a digit slot).
    logic [REFRESH_BITS+2:0] t;
    logic [2:0] k;
    logic       lit;
    logic [3:0] dix [8];
    logic [7:0] cur;

    assign k   = t[REFRESH_BITS+2:REFRESH_BITS];
    assign lit = t[REFRESH_BITS-1:REFRESH_BITS-3] <= dim;
    assign cur = msg[dix[k]];

    always_ff @(posedge clk) begin
        if (rst) begin
            for (int i = 0; i < 8; i++) dix[i] <= '0;
        end else begin
            dix[7] <= pos;
            for (int i = 0; i < 7; i++)
                dix[i] <= ({1'b0, dix[i + 1]} + 5'd1 >= len) ? 4'd0 : dix[i + 1] + 4'd1;
        end
    end

    always_ff @(posedge clk) begin
        if (rst) begin
            t <= '0; an <= 8'hFF; seg_n <= 8'hFF;
        end else begin
            t     <= t + 1'b1;
            an    <= lit ? ~(8'b1 << k) : 8'hFF;
            seg_n <= ~cur;
        end
    end

    always_ff @(posedge clk) begin
        if (rst) win_rdata <= '0;
        else if (win_rd) begin
            if (win_addr[6:4] == 3'b001) win_rdata <= {24'd0, msg[win_addr[3:0]]};
            else case (win_addr)
                7'h00:   win_rdata <= {30'd0, ctrl};
                7'h01:   win_rdata <= {27'd0, len};
                7'h02:   win_rdata <= {28'd0, pos};
                7'h03:   win_rdata <= {29'd0, dim};
                default: win_rdata <= '0;
            endcase
        end
    end
endmodule
