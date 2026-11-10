// c14_systolic_matmul_regs.sv: the shell window of course task c14_systolic_matmul.
module c14_systolic_matmul_regs (
    input  logic        clk,
    input  logic        rst,
    output logic [15:0] led,
    input  logic [6:0]  win_addr,
    input  logic        win_wr,
    input  logic        win_rd,
    input  logic [31:0] win_wdata,
    output logic [31:0] win_rdata
);
    logic [127:0] w_r, c_row;
    logic [31:0]  rowm [0:15];
    logic [127:0] resm [0:15];
    logic [4:0]   n_tot, tx_i, rx_i;
    logic [7:0]   cnt;
    logic [4:0]   lat;
    logic         txing, wl, ov, done, running, got_first;
    logic [31:0]  a_row;

    assign a_row = rowm[tx_i[3:0]];
    assign led   = {15'd0, done};

    matmul4_rows u_core (.clk(clk), .rst_n(!rst), .w_load(wl), .w_in(w_r), .row_valid(txing), .a_row(a_row),
                         .out_valid(ov), .c_row(c_row));

    always_ff @(posedge clk) begin
        wl <= 1'b0;
        if (win_wr) begin
            if (win_addr <= 7'd3) w_r[win_addr[1:0]*32 +: 32] <= win_wdata;
            else if (win_addr == 7'd4) wl <= 1'b1;
            else if (win_addr >= 7'h08 && win_addr <= 7'h17) rowm[4'(win_addr - 7'h08)] <= win_wdata;
            else if (win_addr == 7'h18) begin
                n_tot <= (win_wdata[4:0] == 5'd0) ? 5'd1 : win_wdata[4:0];
                tx_i <= 5'd0; rx_i <= 5'd0; txing <= 1'b1; done <= 1'b0; running <= 1'b0; got_first <= 1'b0; cnt <= 8'd0;
            end
        end
        if (txing) begin
            tx_i <= tx_i + 5'd1;
            if (tx_i + 5'd1 == n_tot) txing <= 1'b0;
            if (tx_i == 5'd0) begin running <= 1'b1; cnt <= 8'd1; end
        end
        if (running && !(txing && tx_i == 5'd0)) cnt <= cnt + 8'd1;
        if (ov && !done) begin
            resm[rx_i[3:0]] <= c_row;
            rx_i <= rx_i + 5'd1;
            if (!got_first) begin got_first <= 1'b1; lat <= cnt[4:0]; running <= 1'b0; end
            if (rx_i + 5'd1 == n_tot) done <= 1'b1;
        end
        win_rdata <= 32'd0;
        if (win_rd) begin
            if (win_addr <= 7'd3) win_rdata <= w_r[win_addr[1:0]*32 +: 32];
            else if (win_addr >= 7'h08 && win_addr <= 7'h17) win_rdata <= rowm[4'(win_addr - 7'h08)];
            else if (win_addr == 7'h19) win_rdata <= {31'd0, done};
            else if (win_addr == 7'h1A) win_rdata <= {27'd0, lat};
            else if (win_addr == 7'h1B) win_rdata <= {27'd0, rx_i};
            else if (win_addr >= 7'h20 && win_addr <= 7'h5F)
                win_rdata <= resm[4'(win_addr[6:2] - 5'd8)][win_addr[1:0]*32 +: 32];
        end
        if (rst) begin
            txing <= 1'b0; done <= 1'b0; running <= 1'b0; got_first <= 1'b0; wl <= 1'b0; w_r <= '0;
            tx_i <= '0; rx_i <= '0; n_tot <= '0; lat <= '0; cnt <= '0; win_rdata <= 32'd0;
            for (int i = 0; i < 16; i++) begin rowm[i] <= '0; resm[i] <= '0; end
        end
    end
endmodule
