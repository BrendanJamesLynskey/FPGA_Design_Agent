module dual_port_memory (
    input logic clk,
    input logic we,
    input logic [7:0] write_addr,
    input logic [7:0] din,
    input logic [7:0] read_addr,
    output logic [7:0] dout
);

    logic [7:0] mem [255:0];

    always_ff @(posedge clk) begin
        if (we) begin
            mem[write_addr] <= din;
        end
    end

    assign dout = mem[read_addr];
endmodule
