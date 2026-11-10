// c11_nco_mixer_regs.sv: the shell window of course task c11_nco_mixer (burst of samples, result pairs, a valid record).
module c11_nco_mixer_regs (
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
    logic [15:0] fw_r;
    logic [11:0] samp [16];
    logic [27:0] outq [16];
    logic [5:0]  nout;
    logic        go, active, en, done, ov;
    logic [6:0]  cnt;
    logic [5:0]  idx;
    logic signed [11:0] io, qo;

    assign led = 16'd0;

    burst_ctl u_burst (.clk(clk), .rst(rst), .go(go), .mask(mask_r), .active(active), .cnt(cnt), .en(en), .idx(idx), .done(done));
    nco_mixer u_core (.clk(clk), .rst_n(!rst), .en(en), .fw(fw_r), .x(samp[idx[3:0]]), .out_valid(ov), .i_out(io), .q_out(qo));

    always_ff @(posedge clk) begin
        go <= 1'b0;
        if (go) begin nout <= '0; vmask <= '0; end
        else if (active && ov) begin
            if (nout < 6'd16) outq[nout[3:0]] <= {4'd0, qo[11:0], 4'd0, io[11:0]};
            nout <= nout + 1'b1;
            if (cnt >= LAT && cnt - LAT < 7'd32) vmask[cnt - LAT] <= 1'b1;
        end
        if (win_wr) begin
            if (win_addr == 7'h00) mask_r <= win_wdata;
            if (win_addr == 7'h01) go <= 1'b1;
            if (win_addr == 7'h05) fw_r <= win_wdata[15:0];
            if (win_addr[6:4] == 3'd1) samp[win_addr[3:0]] <= win_wdata[11:0];
        end
        win_rdata <= 32'd0;
        if (win_rd) begin
            if (win_addr == 7'h00) win_rdata <= mask_r;
            if (win_addr == 7'h02) win_rdata <= {31'd0, done};
            if (win_addr == 7'h03) win_rdata <= {26'd0, nout};
            if (win_addr == 7'h04) win_rdata <= vmask;
            if (win_addr == 7'h05) win_rdata <= {16'd0, fw_r};
            if (win_addr[6:4] == 3'd1) win_rdata <= {20'd0, samp[win_addr[3:0]]};
            if (win_addr[6:4] == 3'd2) win_rdata <= (6'(win_addr[3:0]) < nout) ? {4'd0, outq[win_addr[3:0]]} : 32'd0;
        end
        if (rst) begin
            mask_r <= '0; vmask <= '0; fw_r <= '0; nout <= '0; go <= 1'b0; win_rdata <= 32'd0;
            for (int i = 0; i < 16; i++) begin samp[i] <= '0; outq[i] <= '0; end
        end
    end
endmodule
