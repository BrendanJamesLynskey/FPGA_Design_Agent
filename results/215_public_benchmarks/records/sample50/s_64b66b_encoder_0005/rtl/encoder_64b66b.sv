module encoder_64b66b (
    input  logic         clk_in,              // Clock signal
    input  logic         rst_in,              // Reset (active high): output forced to 0 at once, registers cleared synchronously
    input  logic [63:0]  encoder_data_in,     // 64-bit data input
    input  logic [7:0]   encoder_control_in,  // 8-bit control input
    output logic [65:0]  encoder_data_out     // 66-bit encoded output
);

    logic [1:0]  sync_word;
    logic [63:0] encoded_data;

    // Synchronous reset on the registers (STD-RST-01).
    always_ff @(posedge clk_in) begin
        if (rst_in) begin
            sync_word    <= 2'b00;
            encoded_data <= 64'b0;
        end else if (encoder_control_in == 8'b00000000) begin
            sync_word    <= 2'b01;
            encoded_data <= encoder_data_in;
        end else begin
            sync_word    <= 2'b10;
            encoded_data <= 64'b0;
        end
    end

    // Output is forced to zero combinationally while rst_in is 1 (no clock edge needed).
    assign encoder_data_out = rst_in ? 66'b0 : {sync_word, encoded_data};

endmodule
