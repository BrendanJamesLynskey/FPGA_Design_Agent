// source: labs/p16_crypto/uart_rxtx.sv (course file, unchanged below this line)
// Part 16 labs: a minimal 8N1 UART receiver and transmitter (the same style as Part 15's vector-search lab). CLKS_PER_BIT = 868 for 115200 baud at 100 MHz.
module uart_rx #(
    parameter int CLKS_PER_BIT = 868
) (
    input  logic       clk,
    input  logic       rst_n,
    input  logic       rxd,
    output logic       vld,
    output logic [7:0] data
);
    logic        s1, s2, run;
    logic [15:0] cnt;
    logic [3:0]  bitn;
    always_ff @(posedge clk) begin
        s1 <= rxd;
        s2 <= s1;
        vld <= 1'b0;
        if (!rst_n) run <= 1'b0;
        else if (!run) begin
            if (!s2) begin run <= 1'b1; cnt <= CLKS_PER_BIT / 2; bitn <= 4'd0; end
        end else if (cnt != 0) cnt <= cnt - 1'b1;
        else begin
            cnt <= CLKS_PER_BIT - 1;
            bitn <= bitn + 1'b1;
            if (bitn == 4'd0) begin if (s2) run <= 1'b0; end
            else if (bitn <= 4'd8) data <= {s2, data[7:1]};
            else begin run <= 1'b0; vld <= s2; end
        end
    end
endmodule

module uart_tx #(
    parameter int CLKS_PER_BIT = 868
) (
    input  logic       clk,
    input  logic       rst_n,
    input  logic       go,
    input  logic [7:0] data,
    output logic       busy,
    output logic       txd
);
    logic [9:0]  sh;
    logic [15:0] cnt;
    logic [3:0]  n;
    always_ff @(posedge clk) begin
        if (!rst_n) begin busy <= 1'b0; txd <= 1'b1; end
        else if (!busy) begin
            txd <= 1'b1;
            if (go) begin busy <= 1'b1; sh <= {1'b1, data, 1'b0}; cnt <= CLKS_PER_BIT - 1; n <= 4'd0; end
        end else begin
            txd <= sh[0];
            if (cnt != 0) cnt <= cnt - 1'b1;
            else begin
                cnt <= CLKS_PER_BIT - 1;
                sh <= {1'b1, sh[9:1]};
                n <= n + 1'b1;
                if (n == 4'd9) busy <= 1'b0;
            end
        end
    end
endmodule
