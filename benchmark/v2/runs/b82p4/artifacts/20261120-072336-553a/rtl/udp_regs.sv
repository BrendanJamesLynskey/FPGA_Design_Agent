// udp_regs: window register decode. Read data is registered, valid the cycle after win_rd.
module udp_regs (
    input  logic        clk,
    input  logic        rst,
    input  logic [6:0]  win_addr,
    input  logic        win_wr,
    input  logic        win_rd,
    input  logic [8:0]  win_wdata,     // low bits of the window write data (the rest is unused)
    output logic [31:0] win_rdata,
    // to the design
    output logic        in_wr,
    output logic [8:0]  in_data,
    output logic        tick_wr,
    output logic [7:0]  tick_n,
    output logic        take_wr,
    output logic [6:0]  ridx,
    output logic [6:0]  tidx,
    // from the design
    input  logic [7:0]  rlen,
    input  logic [31:0] rword,
    input  logic [7:0]  tlen,
    input  logic [31:0] tword,
    input  logic        tel_on,
    input  logic        busy
);
    assign in_wr   = win_wr && (win_addr == 7'd0);
    assign in_data = win_wdata;
    assign tick_wr = win_wr && (win_addr == 7'd1);
    assign tick_n  = win_wdata[7:0];
    assign take_wr = win_wr && (win_addr == 7'd8);

    always_ff @(posedge clk) begin
        if (rst) begin
            ridx <= 7'd0;
            tidx <= 7'd0;
        end else if (win_wr) begin
            if (win_addr == 7'd3) ridx <= win_wdata[6:0];
            if (win_addr == 7'd6) tidx <= win_wdata[6:0];
        end
    end

    always_ff @(posedge clk) begin
        if (win_rd) begin
            case (win_addr)
                7'd2:    win_rdata <= {24'd0, rlen};
                7'd3:    win_rdata <= {25'd0, ridx};
                7'd4:    win_rdata <= rword;
                7'd5:    win_rdata <= {24'd0, tlen};
                7'd6:    win_rdata <= {25'd0, tidx};
                7'd7:    win_rdata <= tword;
                7'd9:    win_rdata <= {30'd0, busy, tel_on};
                default: win_rdata <= 32'd0;
            endcase
        end
    end
endmodule
