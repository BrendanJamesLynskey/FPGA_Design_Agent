// c9_median3x3_regs.sv: the shell window of course task c9_median3x3 (burst of windows, medians, a valid record).
module c9_median3x3_regs (
    input  logic        clk,
    input  logic        rst,
    output logic [15:0] led,
    input  logic [6:0]  win_addr,
    input  logic        win_wr,
    input  logic        win_rd,
    input  logic [31:0] win_wdata,
    output logic [31:0] win_rdata
);
    localparam int LAT = 1;
    logic [31:0] mask_r, vmask;
    logic [23:0] wd [24];
    logic [7:0]  outq [8];
    logic [5:0]  nout;
    logic        go, active, en, done, ov;
    logic [6:0]  cnt;
    logic [5:0]  idx;
    logic [7:0]  med;
    wire  [4:0]  base = 5'({2'b00, idx[2:0]} * 3);
    wire  [71:0] cur = {wd[base + 5'd2], wd[base + 5'd1], wd[base]};

    assign led = 16'd0;

    burst_ctl u_burst (.clk(clk), .rst(rst), .go(go), .mask(mask_r), .active(active), .cnt(cnt), .en(en), .idx(idx), .done(done));
    median3x3 u_core (.clk(clk), .rst_n(!rst), .in_valid(en), .win(cur), .out_valid(ov), .med(med));

    always_ff @(posedge clk) begin
        go <= 1'b0;
        if (go) begin nout <= '0; vmask <= '0; end
        else if (active && ov) begin
            if (nout < 6'd8) outq[nout[2:0]] <= med;
            nout <= nout + 1'b1;
            if (cnt >= LAT && cnt - LAT < 7'd32) vmask[cnt - LAT] <= 1'b1;
        end
        if (win_wr) begin
            if (win_addr == 7'h00) mask_r <= win_wdata;
            if (win_addr == 7'h01) go <= 1'b1;
            if (win_addr >= 7'h10 && win_addr < 7'h28) wd[win_addr - 7'h10] <= win_wdata[23:0];
        end
        win_rdata <= 32'd0;
        if (win_rd) begin
            if (win_addr == 7'h00) win_rdata <= mask_r;
            if (win_addr == 7'h02) win_rdata <= {31'd0, done};
            if (win_addr == 7'h03) win_rdata <= {26'd0, nout};
            if (win_addr == 7'h04) win_rdata <= vmask;
            if (win_addr >= 7'h10 && win_addr < 7'h28) win_rdata <= {8'd0, wd[win_addr - 7'h10]};
            if (win_addr >= 7'h30 && win_addr < 7'h38) win_rdata <= (6'(win_addr[2:0]) < nout) ? {24'd0, outq[win_addr[2:0]]} : 32'd0;
        end
        if (rst) begin
            mask_r <= '0; vmask <= '0; nout <= '0; go <= 1'b0; win_rdata <= 32'd0;
            for (int i = 0; i < 24; i++) wd[i] <= '0;
            for (int i = 0; i < 8; i++) outq[i] <= '0;
        end
    end
endmodule
