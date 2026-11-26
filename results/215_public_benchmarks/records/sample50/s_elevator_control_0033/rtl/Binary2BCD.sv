module Binary2BCD (
    input  wire [7:0] num,
    output wire [3:0] thousand,
    output wire [3:0] hundred,
    output wire [3:0] ten,
    output wire [3:0] one
);

    logic [19:0] shift;

    always_comb begin
        shift = {12'd0, num};
        for (int i = 0; i < 8; i++) begin
            if (shift[11:8] >= 4'd5)  shift[11:8]  = shift[11:8] + 4'd3;
            if (shift[15:12] >= 4'd5) shift[15:12] = shift[15:12] + 4'd3;
            if (shift[19:16] >= 4'd5) shift[19:16] = shift[19:16] + 4'd3;
            shift = shift << 1;
        end
    end

    assign hundred  = shift[19:16];
    assign ten      = shift[15:12];
    assign one      = shift[11:8];
    assign thousand = 4'd0;

endmodule
