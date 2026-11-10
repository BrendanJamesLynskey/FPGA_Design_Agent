// P14-1 reference top for the Nexys A7-100T: the course's tiny CNN (tiny_cnn.sv) with the parameters and eight images in block-RAM files (cnn_system.sv loads them), a debounced
// button to classify the picture chosen on SW[2:0], the class (0 .. 3) on the right-hand seven-segment digit, and one letter (H, V, B, X) plus a newline over the USB-UART at 115200 baud.
// Not run on a board; simulated in Icarus by projects/test_p14_projects.py with a shortened debounce and baud divider.
module cnn_nexys_top_ref #(
    parameter DEBOUNCE_CYCLES = 1000000,        // 10 ms at 100 MHz
    parameter CLKS_PER_BIT    = 868,            // 115200 baud at 100 MHz
    parameter PARAMS = "cnn_params.hex",
    parameter IMAGES = "cnn_images.hex"
) (
    input  logic        CLK100MHZ,
    input  logic        CPU_RESETN,
    input  logic        BTNC,
    input  logic [2:0]  SW,
    output logic [7:0]  AN,
    output logic [6:0]  SEG,
    output logic [15:0] LED,
    output logic        UART_RXD_OUT
);
    logic [2:0] rst_sr = '0;
    always_ff @(posedge CLK100MHZ) rst_sr <= {rst_sr[1:0], CPU_RESETN};
    wire rst_n = rst_sr[2];
    // debounce: the button value is accepted when it has been stable for DEBOUNCE_CYCLES clocks
    logic b_sync0 = 1'b0, b_sync1 = 1'b0, b_stable = 1'b0, b_prev = 1'b0;
    logic [$clog2(DEBOUNCE_CYCLES+1):0] cnt = '0;
    always_ff @(posedge CLK100MHZ) begin
        b_sync0 <= BTNC; b_sync1 <= b_sync0;
        if (b_sync1 == b_stable) cnt <= '0;
        else if (cnt == DEBOUNCE_CYCLES - 1) begin b_stable <= b_sync1; cnt <= '0; end
        else cnt <= cnt + 1;
        b_prev <= b_stable;
    end
    wire go = b_stable & ~b_prev;
    logic ready, result_valid;
    logic [1:0] cls, cls_q;
    logic have;
    logic [127:0] logits;
    cnn_system #(.CLKS_PER_BIT(CLKS_PER_BIT), .PARAMS(PARAMS), .IMAGES(IMAGES)) u_sys (
        .clk(CLK100MHZ), .rst_n, .go(go & ready), .img_sel(SW), .ready, .result_valid, .cls, .logits, .uart_tx(UART_RXD_OUT));
    always_ff @(posedge CLK100MHZ) begin
        if (!rst_n) have <= 1'b0;
        else if (result_valid) begin cls_q <= cls; have <= 1'b1; end
    end
    assign AN = 8'hFE;                                         // the right-hand digit only (active low)
    always_comb begin
        SEG = 7'h7F;                                           // blank until the first result
        if (have)
            case (cls_q)                                       // SEG[6:0] = {CG, CF, CE, CD, CC, CB, CA}, active low
                2'd0: SEG = 7'h40;
                2'd1: SEG = 7'h79;
                2'd2: SEG = 7'h24;
                default: SEG = 7'h30;
            endcase
    end
    assign LED = {ready, 13'd0, have ? cls_q : 2'd0};
endmodule
