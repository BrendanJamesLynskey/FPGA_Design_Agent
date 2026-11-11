// adc_capture.sv: the ADC sample register (in the IOBs), LAST, MIN and MAX (d20_adc_capture). One clock.
module adc_capture (
    input  logic        clk,
    input  logic        rst,
    input  logic [7:0]  adc_d,
    output logic [15:0] led,
    input  logic [6:0]  win_addr,
    input  logic        win_wr,
    input  logic        win_rd,
    input  logic [31:0] win_wdata,
    output logic [31:0] win_rdata
);
    // the capture register: driven by the pads alone, so it can sit in the input flip-flops of the IOBs
    (* IOB = "TRUE" *) logic [7:0] adc_q;
    always_ff @(posedge clk) adc_q <= adc_d;

    logic [7:0] last, mn, mx;
    wire clear = win_wr && win_addr == 7'h03;
    always_ff @(posedge clk) begin
        if (rst) begin
            last <= '0; mn <= 8'hFF; mx <= '0;
        end else begin
            last <= adc_q;
            if (clear) begin
                mn <= 8'hFF; mx <= '0;
            end else begin
                if (adc_q < mn) mn <= adc_q;
                if (adc_q > mx) mx <= adc_q;
            end
        end
    end
    assign led = {8'd0, last};

    always_ff @(posedge clk) begin
        if (rst) win_rdata <= '0;
        else if (win_rd) begin
            case (win_addr)
                7'h00:   win_rdata <= 32'(last);
                7'h01:   win_rdata <= 32'(mn);
                7'h02:   win_rdata <= 32'(mx);
                default: win_rdata <= '0;
            endcase
        end
    end
endmodule
