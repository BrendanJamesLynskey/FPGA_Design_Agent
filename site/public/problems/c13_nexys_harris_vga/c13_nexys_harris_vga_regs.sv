// c13_nexys_harris_vga_regs.sv: the shell window of course task c13_nexys_harris_vga: a parked picture, a stream generator and the corner-list readback.
module c13_nexys_harris_vga_regs (
    input  logic        clk,
    input  logic        rst,
    output logic [15:0] led,
    input  logic [6:0]  win_addr,
    input  logic        win_wr,
    input  logic        win_rd,
    input  logic [31:0] win_wdata,
    output logic [31:0] win_rdata
);
    localparam int NPIX = 4800;
    logic [31:0] ram [0:1199];
    logic [10:0] ptr;
    logic        streaming, have_report;
    logic [12:0] tx_i;
    logic [6:0]  tx_x;
    logic [7:0]  s_tdata;
    logic        s_tvalid, s_tready, s_tuser, s_tlast, core_done;
    logic [15:0] count;
    logic [5:0]  sel;
    logic [6:0]  rd_x, rd_y;
    wire busy = streaming;
    assign led = count;

    harris_detect #(.W(80), .H(60)) u_core (.clk(clk), .rst_n(!rst), .s_tdata(s_tdata), .s_tvalid(s_tvalid), .s_tready(s_tready), .s_tuser(s_tuser), .s_tlast(s_tlast),
                                              .done(core_done), .count(count), .rd_idx(sel), .rd_x(rd_x), .rd_y(rd_y));

    wire [31:0] nxt_w = ram[tx_i[12:2]];
    wire slot_free = !s_tvalid || s_tready;

    always_ff @(posedge clk) begin
        if (win_wr) begin
            case (win_addr)
                7'd0: ptr <= win_wdata[10:0];
                7'd1: begin ram[ptr] <= win_wdata; ptr <= ptr + 11'd1; end
                7'd2: begin streaming <= 1'b1; have_report <= 1'b0; tx_i <= 13'd0; tx_x <= 7'd0; s_tvalid <= 1'b0; end
                7'd5: sel <= win_wdata[5:0];
                default: ;
            endcase
        end
        if (streaming && slot_free) begin
            if (tx_i < NPIX) begin
                s_tvalid <= 1'b1;
                s_tdata  <= nxt_w[8*tx_i[1:0] +: 8];
                s_tuser  <= (tx_i == 13'd0);
                s_tlast  <= (tx_x == 7'd79);
                tx_i     <= tx_i + 13'd1;
                tx_x     <= (tx_x == 7'd79) ? 7'd0 : tx_x + 7'd1;
            end else s_tvalid <= 1'b0;
        end
        if (streaming && tx_i == NPIX && !s_tvalid && core_done) begin streaming <= 1'b0; have_report <= 1'b1; end
        win_rdata <= 32'd0;
        if (win_rd) begin
            case (win_addr)
                7'd0: win_rdata <= {21'd0, ptr};
                7'd3: win_rdata <= {30'd0, have_report, busy};
                7'd4: win_rdata <= {16'd0, count};
                7'd5: win_rdata <= {26'd0, sel};
                7'd6: win_rdata <= (16'(sel) < count) ? {17'd0, rd_y, 1'b0, rd_x} : 32'd0;
                default: ;
            endcase
        end
        if (rst) begin
            ptr <= '0; sel <= '0; streaming <= 1'b0; have_report <= 1'b0; tx_i <= '0; tx_x <= '0; s_tvalid <= 1'b0; win_rdata <= 32'd0; s_tdata <= '0; s_tuser <= 1'b0; s_tlast <= 1'b0;
        end
    end
endmodule
