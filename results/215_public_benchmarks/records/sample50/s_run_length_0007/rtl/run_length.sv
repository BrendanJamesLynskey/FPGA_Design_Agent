/* verilator lint_off DECLFILENAME */
// One run-length encoder stream. Synchronous reset (STD-RST-01), synchronous enable clear.
module run_length #(
    parameter int DATA_WIDTH = 8
) (
    input  wire                         clk,
    input  wire                         reset_n,
    input  wire                         enable,
    input  wire                         data_in,
    output reg                          data_out,
    output reg  [$clog2(DATA_WIDTH):0]  run_value,
    output reg                          valid
);

    localparam int CW = $clog2(DATA_WIDTH) + 1;
    localparam logic [CW-1:0] MAXRUN = CW'(DATA_WIDTH);
    localparam logic [CW-1:0] ONE    = CW'(1);

    reg [CW-1:0] run_length;
    reg          prev_data_in;

    wire run_end = (run_length == MAXRUN) || (data_in != prev_data_in);

    always @(posedge clk) begin
        if (!reset_n || !enable) begin
            run_length   <= '0;
            run_value    <= '0;
            prev_data_in <= 1'b0;
            valid        <= 1'b0;
            data_out     <= 1'b0;
        end else begin
            prev_data_in <= data_in;
            valid        <= run_end;
            data_out     <= run_end ? prev_data_in : 1'b0;
            if (run_end) begin
                run_value  <= run_length;
                run_length <= ONE;
            end else begin
                run_length <= run_length + ONE;
            end
        end
    end

endmodule

module parallel_run_length #(
    parameter int DATA_WIDTH  = 8,
    parameter int NUM_STREAMS = 4
) (
    input  wire                                           clk,
    input  wire                                           reset_n,
    input  wire [NUM_STREAMS-1:0]                         data_in,
    input  wire [NUM_STREAMS-1:0]                         stream_enable,
    output wire [NUM_STREAMS-1:0]                         data_out,
    output wire [NUM_STREAMS*($clog2(DATA_WIDTH)+1)-1:0]  run_value,
    output wire [NUM_STREAMS-1:0]                         valid
);

    localparam int RW = $clog2(DATA_WIDTH) + 1;

    for (genvar i = 0; i < NUM_STREAMS; i++) begin : g_stream
        run_length #(.DATA_WIDTH(DATA_WIDTH)) u_rl (
            .clk      (clk),
            .reset_n  (reset_n),
            .enable   (stream_enable[i]),
            .data_in  (data_in[i]),
            .data_out (data_out[i]),
            .run_value(run_value[i*RW +: RW]),
            .valid    (valid[i])
        );
    end

endmodule
