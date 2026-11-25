// Manchester encoder: registered, synchronous active-high reset, no latches.
// The outputs are also forced to 0 combinationally while rst_in is high, so
// the spec's "while rst_in is high the outputs are 0" holds without an
// asynchronous reset in a sensitivity list.
module manchester_encoder #(
    parameter int N = 8
) (
    input  logic             clk_in,
    input  logic             rst_in,
    input  logic             enc_valid_in,
    input  logic [N-1:0]     enc_data_in,
    output logic             enc_valid_out,
    output logic [2*N-1:0]   enc_data_out
);

    logic [2*N-1:0] enc_next;
    logic [2*N-1:0] data_q;
    logic           valid_q;

    // bit 1 -> 2'b01, bit 0 -> 2'b10, all zero when not valid
    always_comb begin
        enc_next = '0;
        if (enc_valid_in) begin
            for (int i = 0; i < N; i++) begin
                enc_next[2*i]   = enc_data_in[i];
                enc_next[2*i+1] = ~enc_data_in[i];
            end
        end
    end

    always_ff @(posedge clk_in) begin
        if (rst_in) begin
            valid_q <= 1'b0;
            data_q  <= '0;
        end else begin
            valid_q <= enc_valid_in;
            data_q  <= enc_next;
        end
    end

    assign enc_valid_out = valid_q & ~rst_in;
    assign enc_data_out  = rst_in ? '0 : data_q;

endmodule
