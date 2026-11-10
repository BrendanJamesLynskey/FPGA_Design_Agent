// c13_nexys_blob_tracker_regs.sv: the shell window of course task c13_nexys_blob_tracker: a parked picture, a stream generator and the report registers.
module c13_nexys_blob_tracker_regs (
    input  logic        clk,
    input  logic        rst,
    output logic [15:0] led,
    input  logic [6:0]  win_addr,
    input  logic        win_wr,
    input  logic        win_rd,
    input  logic [31:0] win_wdata,
    output logic [31:0] win_rdata
);
    localparam int NPIX = 1200;
    logic [31:0] ram [0:37];
    logic [5:0]  ptr;
    logic        streaming, have_report, rep_done;
    logic [10:0] tx_i;
    logic [7:0]  s_tdata, cx, cy;
    logic        s_tvalid, s_tready, s_tuser, s_tlast;
    logic [15:0] area;
    logic [5:0]  tx_x;
    logic [31:0] nxt_w;
    wire busy = streaming;
    assign led = {15'd0, busy};

    blob_report #(.W(40), .H(30)) u_core (.clk(clk), .rst_n(!rst), .s_tdata(s_tdata), .s_tvalid(s_tvalid), .s_tready(s_tready), .s_tuser(s_tuser), .s_tlast(s_tlast),
                                            .done(rep_done), .area(area), .cx(cx), .cy(cy));

    assign nxt_w = ram[tx_i[10:5]];
    wire slot_free = !s_tvalid || s_tready;

    always_ff @(posedge clk) begin
        if (win_wr) begin
            case (win_addr)
                7'd0: ptr <= win_wdata[5:0];
                7'd1: begin ram[ptr] <= win_wdata; ptr <= ptr + 6'd1; end
                7'd2: begin streaming <= 1'b1; have_report <= 1'b0; tx_i <= 11'd0; tx_x <= 6'd0; s_tvalid <= 1'b0; end
                default: ;
            endcase
        end
        if (streaming && slot_free) begin
            if (tx_i < NPIX) begin
                s_tvalid <= 1'b1;
                s_tdata  <= {7'd0, nxt_w[tx_i[4:0]]};
                s_tuser  <= (tx_i == 11'd0);
                s_tlast  <= (tx_x == 6'd39);
                tx_i     <= tx_i + 11'd1;
                tx_x     <= (tx_x == 6'd39) ? 6'd0 : tx_x + 6'd1;
            end else s_tvalid <= 1'b0;
        end
        if (rep_done) begin streaming <= 1'b0; have_report <= 1'b1; end
        win_rdata <= 32'd0;
        if (win_rd) begin
            case (win_addr)
                7'd0: win_rdata <= {26'd0, ptr};
                7'd3: win_rdata <= {30'd0, have_report, busy};
                7'd4: win_rdata <= {16'd0, area};
                7'd5: win_rdata <= {24'd0, cx};
                7'd6: win_rdata <= {24'd0, cy};
                default: ;
            endcase
        end
        if (rst) begin
            ptr <= '0; streaming <= 1'b0; have_report <= 1'b0; tx_i <= '0; tx_x <= '0; s_tvalid <= 1'b0; win_rdata <= 32'd0; s_tdata <= '0; s_tuser <= 1'b0; s_tlast <= 1'b0;
        end
    end
endmodule
