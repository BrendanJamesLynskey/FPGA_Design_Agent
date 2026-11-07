// c10_dds_sine_regs.sv: the shell window of course task c10_dds_sine (frequency word, recording of 1200 samples, packed read port).
module c10_dds_sine_regs (
    input  logic        clk,
    input  logic        rst,
    output logic [15:0] led,
    input  logic [6:0]  win_addr,
    input  logic        win_wr,
    input  logic        win_rd,
    input  logic [31:0] win_wdata,
    output logic [31:0] win_rdata
);
    localparam int NS = 1200;
    logic [23:0]        fw_r;
    logic [11:0]        mem [NS];
    logic [10:0]        wptr;
    logic [9:0]         rptr;
    logic [2:0]         rst_cnt;
    logic               go, rec, done, ov;
    logic signed [11:0] od;
    wire                core_rst_n = !rst && (rst_cnt == 3'd0);

    assign led = 16'd0;

    dds u_core (.clk(clk), .rst_n(core_rst_n), .fw(fw_r), .out_valid(ov), .out_data(od));

    always_ff @(posedge clk) begin
        go <= 1'b0;
        if (go) begin rst_cnt <= 3'd2; rec <= 1'b1; done <= 1'b0; wptr <= '0; rptr <= '0; end
        else if (rst_cnt != 3'd0) rst_cnt <= rst_cnt - 3'd1;
        else if (rec && ov) begin
            mem[wptr] <= od;
            wptr <= wptr + 1'b1;
            if (wptr == NS - 1) begin rec <= 1'b0; done <= 1'b1; end
        end
        if (win_wr) begin
            if (win_addr == 7'h00) fw_r <= win_wdata[23:0];
            if (win_addr == 7'h01) go <= 1'b1;
            if (win_addr == 7'h03 || win_addr == 7'h04) rptr <= win_wdata[9:0];
        end
        win_rdata <= 32'd0;
        if (win_rd) begin
            if (win_addr == 7'h00) win_rdata <= {8'd0, fw_r};
            if (win_addr == 7'h02) win_rdata <= {31'd0, done};
            if (win_addr == 7'h03) win_rdata <= {22'd0, rptr};
            if (win_addr == 7'h04) begin
                if (done && rptr < NS / 2) win_rdata <= {4'd0, mem[{rptr, 1'b1}], 4'd0, mem[{rptr, 1'b0}]};
                rptr <= rptr + 1'b1;
            end
        end
        if (rst) begin
            fw_r <= '0; wptr <= '0; rptr <= '0; rst_cnt <= '0; go <= 1'b0; rec <= 1'b0; done <= 1'b0; win_rdata <= 32'd0;
        end
    end
endmodule
