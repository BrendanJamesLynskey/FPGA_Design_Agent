module caesar_cipher (
    input  wire [7:0] input_char,  // 8-bit ASCII character
    input  wire [3:0] key,         // 4-bit shift key
    output reg  [7:0] output_char  // 8-bit shifted output character
);

    logic       is_upper;
    logic       is_lower;
    logic [7:0] base;
    logic [7:0] offset;
    logic [7:0] sum;
    logic [7:0] wrapped;

    always_comb begin
        is_upper = (input_char >= 8'h41) && (input_char <= 8'h5A);
        is_lower = (input_char >= 8'h61) && (input_char <= 8'h7A);
        base     = is_lower ? 8'h61 : 8'h41;
        offset   = input_char - base;
        sum      = offset + {4'b0000, key};
        wrapped  = (sum >= 8'd26) ? (sum - 8'd26) : sum;
        if (is_upper || is_lower) begin
            output_char = base + wrapped;
        end else begin
            output_char = input_char;
        end
    end

endmodule
