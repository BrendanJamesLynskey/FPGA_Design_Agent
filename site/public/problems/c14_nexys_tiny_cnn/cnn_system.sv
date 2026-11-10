// Part 14 lab 1, the working core (checked in Icarus by test_lab_cnn.py): block-RAM parameters and eight test images, a loader that writes them into the course tiny CNN
// (solutions/p14l10_tiny_cnn/tiny_cnn.sv), a start on `go`, and a UART transmitter that sends the class letter (H, V, B or X for a horizontal bar, a vertical bar, a box
// or a cross) and a newline. After reset the 632 parameter words are loaded once (about 650 clocks); `ready` goes high when the system can take a `go`.
module cnn_system #(
    parameter CLKS_PER_BIT = 868,
    parameter PARAMS = "cnn_params.hex",
    parameter IMAGES = "cnn_images.hex"
) (
    input  logic        clk,
    input  logic        rst_n,
    input  logic        go,                 // one clock: classify image img_sel
    input  logic [2:0]  img_sel,
    output logic        ready,
    output logic        result_valid,       // one clock when cls is new
    output logic [1:0]  cls,
    output logic [127:0] logits,
    output logic        uart_tx
);
    logic [31:0] prom [0:631];
    logic [7:0]  irom [0:1151];
    initial begin
`include "cnn_init.svh"
    end
    logic        ld_we, start, busy, done;
    logic [1:0]  ld_sel;
    logic [9:0]  ld_addr;
    logic [31:0] ld_data;
    tiny_cnn u_cnn (.clk, .rst_n, .ld_we, .ld_sel, .ld_addr, .ld_data, .start, .busy, .done, .logits, .cls);

    typedef enum logic [2:0] {LOAD, IDLE, IMG, RUN, WAIT, SEND} st_t;
    st_t st;
    logic [9:0] n;
    logic [2:0] sel_q;
    always_comb begin
        ld_we = 1'b0; ld_sel = 2'd0; ld_addr = 10'd0; ld_data = 32'd0;
        if (st == LOAD) begin
            ld_we = 1'b1;
            ld_data = prom[n];
            if (n < 612) begin ld_sel = 2'd0; ld_addr = n; end
            else if (n < 628) begin ld_sel = 2'd1; ld_addr = n - 612; end
            else begin ld_sel = 2'd2; ld_addr = n - 628; end
        end else if (st == IMG) begin
            ld_we = 1'b1; ld_sel = 2'd3; ld_addr = n;
            ld_data = {24'd0, irom[11'({sel_q, 7'd0}) + 11'({sel_q, 4'd0}) + 11'(n)]};     // sel * 144 + n  (144 = 128 + 16)
        end
    end
    assign ready = (st == IDLE);
    logic tx_start, tx_busy;
    logic [7:0] tx_byte;
    logic send_nl;
    uart_tx #(.CLKS_PER_BIT(CLKS_PER_BIT)) u_tx (.clk, .rst_n, .start(tx_start), .data(tx_byte), .busy(tx_busy), .tx(uart_tx));
    always_ff @(posedge clk) begin
        start <= 1'b0; tx_start <= 1'b0; result_valid <= 1'b0;
        if (!rst_n) begin st <= LOAD; n <= '0; send_nl <= 1'b0; end
        else case (st)
            LOAD: if (n == 631) begin st <= IDLE; n <= '0; end else n <= n + 10'd1;
            IDLE: if (go) begin sel_q <= img_sel; n <= '0; st <= IMG; end
            IMG:  if (n == 143) begin st <= RUN; end else n <= n + 10'd1;
            RUN:  begin start <= 1'b1; st <= WAIT; end
            WAIT: if (done) begin result_valid <= 1'b1; st <= SEND; send_nl <= 1'b0; tx_start <= 1'b1; tx_byte <= "HVBX" >> ((3 - cls) * 8); end
            SEND: if (!tx_busy && !tx_start) begin
                      if (!send_nl) begin send_nl <= 1'b1; tx_start <= 1'b1; tx_byte <= 8'h0A; end
                      else st <= IDLE;
                  end
            default: st <= IDLE;
        endcase
    end
endmodule

// 8N1 UART transmitter, LSB first. start (one clock, only when busy is low) sends data.
module uart_tx #(
    parameter CLKS_PER_BIT = 868
) (
    input  logic       clk,
    input  logic       rst_n,
    input  logic       start,
    input  logic [7:0] data,
    output logic       busy,
    output logic       tx
);
    logic [9:0] sh;
    logic [3:0] bits;
    logic [$clog2(CLKS_PER_BIT+1):0] cnt;
    assign busy = (bits != 0);
    always_ff @(posedge clk) begin
        if (!rst_n) begin tx <= 1'b1; bits <= '0; cnt <= '0; end
        else if (start && !busy) begin sh <= {1'b1, data, 1'b0}; bits <= 4'd10; cnt <= '0; end
        else if (busy) begin
            tx <= sh[0];
            if (cnt == CLKS_PER_BIT - 1) begin cnt <= '0; sh <= {1'b1, sh[9:1]}; bits <= bits - 4'd1; end
            else cnt <= cnt + 1;
        end else tx <= 1'b1;
    end
endmodule
