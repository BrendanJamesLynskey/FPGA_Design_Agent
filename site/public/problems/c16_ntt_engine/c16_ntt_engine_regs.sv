// c16_ntt_engine_regs.sv: the shell window of course task c16_ntt_engine.
module c16_ntt_engine_regs (
    input  logic        clk,
    input  logic        rst,
    output logic [15:0] led,
    input  logic [6:0]  win_addr,
    input  logic        win_wr,
    input  logic        win_rd,
    input  logic [31:0] win_wdata,
    output logic [31:0] win_rdata
);
    logic [7:0]  rd_ptr;
    logic [11:0] ld_lo, ld_hi, ld_d, rd_d, plo, phi;
    logic [7:0]  ld_a;
    logic [1:0]  ld_ph;
    logic        ld_en, start, inv, busy, done, dn, rd_ph;
    logic [11:0] cyc;

    assign led = {14'd0, busy, dn};
    logic [6:0] ld_ptr_q;
    assign ld_a = {ld_ptr_q, ld_ph[1]};

    ntt_engine u_core (.clk(clk), .rst_n(!rst), .ld_en(ld_en), .ld_addr(ld_a), .ld_data(ld_d), .start(start), .inverse(inv),
                       .busy(busy), .done(done), .rd_addr({rd_ptr[6:0], rd_ph}), .rd_data(rd_d));

    always_ff @(posedge clk) begin
        start <= 1'b0;
        rd_ph <= ~rd_ph;
        if (rd_ph) phi <= rd_d; else plo <= rd_d;
        if (ld_ph != 2'd0) begin
            ld_ph <= ld_ph + 2'd1;
            if (ld_ph == 2'd1) begin ld_d <= ld_hi; ld_en <= 1'b1; end
            if (ld_ph == 2'd2) begin ld_en <= 1'b0; ld_ph <= 2'd0; ld_ptr_q <= ld_ptr_q + 7'd1; end
        end
        if (busy) cyc <= cyc + 12'd1;
        if (done) dn <= 1'b1;
        if (win_wr) begin
            case (win_addr)
                7'd0: ld_ptr_q <= win_wdata[6:0];
                7'd1: rd_ptr <= win_wdata[7:0];
                7'd2: begin ld_lo <= win_wdata[11:0]; ld_hi <= win_wdata[27:16]; ld_d <= win_wdata[11:0]; ld_en <= 1'b1; ld_ph <= 2'd1; end
                7'd3: begin start <= 1'b1; inv <= 1'b0; dn <= 1'b0; cyc <= 12'd0; end
                7'd4: begin start <= 1'b1; inv <= 1'b1; dn <= 1'b0; cyc <= 12'd0; end
                default: ;
            endcase
        end
        win_rdata <= 32'd0;
        if (win_rd) begin
            case (win_addr)
                7'd0: win_rdata <= {25'd0, ld_ptr_q};
                7'd1: win_rdata <= {24'd0, rd_ptr};
                7'd5: win_rdata <= {30'd0, dn, busy};
                7'd6: begin win_rdata <= {4'd0, phi, 4'd0, plo}; rd_ptr <= rd_ptr + 8'd1; end
                7'd7: win_rdata <= {20'd0, cyc};
                default: ;
            endcase
        end
        if (rst) begin
            ld_ptr_q <= '0; rd_ptr <= '0; rd_ph <= 1'b0; inv <= 1'b0; ld_en <= 1'b0; ld_ph <= '0; start <= 1'b0; dn <= 1'b0; cyc <= '0; win_rdata <= 32'd0;
        end
    end
endmodule
