// seq_detect.sv: overlapping detector for the bit pattern 1,0,1,1 on a serial input, for v2_a_seq_detect.
module seq_detect (
    input  logic        clk,
    input  logic        rst,
    input  logic        sig_async,
    output logic [15:0] led,
    input  logic [6:0]  win_addr,
    input  logic        win_wr,
    input  logic        win_rd,
    input  logic [31:0] win_wdata,
    output logic [31:0] win_rdata
);
    localparam logic [3:0] PATTERN = 4'b1011;
    logic        s1, s2, hit;
    logic [7:0]  hist;
    logic [15:0] count;

    wire wr_cnt = win_wr && win_addr == 7'h00;

    always_ff @(posedge clk) begin
        s1 <= sig_async;
        s2 <= s1;
        if (rst) begin
            hist <= '0;
            hit  <= 1'b0;
        end else begin
            hist <= {hist[6:0], s2};
            hit  <= {hist[2:0], s2} == PATTERN;
        end
    end

    always_ff @(posedge clk) begin
        if (rst) count <= '0;
        else if (wr_cnt) count <= '0;
        else if (hit) count <= count + 1'b1;
    end

    assign led = {15'd0, hit};

    always_ff @(posedge clk) begin
        if (rst) win_rdata <= '0;
        else if (win_rd) begin
            case (win_addr)
                7'h00:   win_rdata <= 32'(count);
                7'h01:   win_rdata <= {31'd0, s2};
                default: win_rdata <= '0;
            endcase
        end
    end
endmodule
