`timescale 1ns / 1ps

module sync_lifo #(
    parameter int DATA_WIDTH = 8,
    parameter int ADDR_WIDTH = 3,
    parameter int DEPTH      = 8
)(
    input  logic                  clock,
    input  logic                  reset,
    input  logic                  write_en,
    input  logic                  read_en,
    input  logic [DATA_WIDTH-1:0] data_in,
    output logic                  empty,
    output logic                  full,
    output logic [DATA_WIDTH-1:0] data_out,
    output logic                  error,
    output logic                  valid
);

    logic [ADDR_WIDTH:0]   count;
    logic [DATA_WIDTH-1:0] mem [DEPTH];

    assign empty = (count == '0);
    assign full  = (count == (ADDR_WIDTH+1)'(DEPTH));

    wire do_wr = write_en && !full;
    wire do_rd = !do_wr && read_en && !empty;

    always_ff @(posedge clock) begin
        if (do_wr) mem[count[ADDR_WIDTH-1:0]] <= data_in;
    end

    always_ff @(posedge clock) begin
        if (reset) begin
            count    <= '0;
            data_out <= '0;
            error    <= 1'b0;
            valid    <= 1'b0;
        end else begin
            valid <= do_rd;
            error <= (write_en && full) || (read_en && empty && !write_en);
            if (do_wr) count <= count + 1'b1;
            else if (do_rd) begin
                count    <= count - 1'b1;
                data_out <= mem[count[ADDR_WIDTH-1:0] - 1'b1];
            end
        end
    end

endmodule
