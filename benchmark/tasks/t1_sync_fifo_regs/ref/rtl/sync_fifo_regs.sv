// sync_fifo_regs.sv: 16 x 8 first-word-fall-through FIFO driven from the
// shell's register window, with sticky W1C error flags, for t1_sync_fifo_regs.
module sync_fifo_regs (
    input  logic        clk,
    input  logic        rst,
    output logic [15:0] led,
    input  logic [6:0]  win_addr,
    input  logic        win_wr,
    input  logic        win_rd,
    input  logic [31:0] win_wdata,
    output logic [31:0] win_rdata
);
    localparam logic [6:0] R_PUSH = 7'h00, R_POP = 7'h01, R_HEAD = 7'h02, R_LEVEL = 7'h03,
                           R_FLAGS = 7'h04, R_AF = 7'h05;

    logic [7:0]  mem [16];
    logic [3:0]  wp, rp;
    logic [4:0]  level, af_th;
    logic        ovf, unf;
    logic [7:0]  head;

    wire empty = level == 5'd0;
    wire full  = level == 5'd16;
    wire afull = level >= af_th;
    wire push  = win_wr && win_addr == R_PUSH;
    wire pop   = win_rd && win_addr == R_POP;

    assign head = empty ? 8'd0 : mem[rp];

    always_ff @(posedge clk)
        if (push && !full) mem[wp] <= win_wdata[7:0];

    always_ff @(posedge clk) begin
        if (rst) begin
            wp <= '0; rp <= '0; level <= '0; ovf <= 1'b0; unf <= 1'b0; af_th <= 5'd12;
        end else begin
            if (push) begin
                if (full) ovf <= 1'b1;
                else begin
                    wp    <= wp + 4'd1;
                    level <= level + 5'd1;
                end
            end
            if (pop) begin
                if (empty) unf <= 1'b1;
                else begin
                    rp    <= rp + 4'd1;
                    level <= level - 5'd1;
                end
            end
            if (win_wr && win_addr == R_FLAGS) begin
                if (win_wdata[8]) ovf <= 1'b0;
                if (win_wdata[9]) unf <= 1'b0;
            end
            if (win_wr && win_addr == R_AF) af_th <= win_wdata[4:0];
        end
    end

    always_ff @(posedge clk) begin
        if (rst) led <= '0;
        else     for (int k = 0; k < 16; k++) led[k] <= 5'(k) < level;
    end

    always_ff @(posedge clk) begin
        if (rst) win_rdata <= '0;
        else if (win_rd) begin
            case (win_addr)
                R_POP:   win_rdata <= {24'd0, head};
                R_HEAD:  win_rdata <= {24'd0, head};
                R_LEVEL: win_rdata <= {27'd0, level};
                R_FLAGS: win_rdata <= {22'd0, unf, ovf, 5'd0, afull, full, empty};
                R_AF:    win_rdata <= {27'd0, af_th};
                default: win_rdata <= '0;
            endcase
        end
    end
endmodule
