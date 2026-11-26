/* verilator lint_off DECLFILENAME */
module sipo_top #(
    parameter DATA_WIDTH = 16,
    parameter SHIFT_DIRECTION = 1,
    parameter CODE_WIDTH = DATA_WIDTH + $clog2(DATA_WIDTH + 1),
    parameter CRC_WIDTH = DATA_WIDTH / 2,
    parameter [CRC_WIDTH-1:0] POLY = 8'b10101010
) (
    input  logic                  clk,
    input  logic                  reset_n,
    input  logic                  serial_in,
    input  logic                  shift_en,
    input  logic [CODE_WIDTH-1:0] received,
    input  logic [CRC_WIDTH-1:0]  received_crc,
    output logic                  done,
    output logic [DATA_WIDTH-1:0] data_out,
    output logic [CODE_WIDTH-1:0] encoded,
    output logic                  error_detected,
    output logic                  error_corrected,
    output logic [CRC_WIDTH-1:0]  crc_out,
    output logic                  crc_error
);

    logic [DATA_WIDTH-1:0] parallel_out;

    serial_in_parallel_out_8bit #(.WIDTH(DATA_WIDTH), .SHIFT_DIRECTION(SHIFT_DIRECTION)) uut_sipo (
        .clk          (clk),
        .reset_n      (reset_n),
        .sin          (serial_in),
        .shift_en     (shift_en),
        .done         (done),
        .parallel_out (parallel_out)
    );

    onebit_ecc #(.DATA_WIDTH(DATA_WIDTH), .CODE_WIDTH(CODE_WIDTH)) uut_onebit_ecc1 (
        .data_in        (parallel_out),
        .encoded        (encoded),
        .received       (received),
        .data_out       (data_out),
        .error_detected (error_detected),
        .error_corrected(error_corrected)
    );

    crc_generator #(.DATA_WIDTH(DATA_WIDTH), .CRC_WIDTH(CRC_WIDTH), .POLY(POLY)) uut_crc (
        .rst_n        (reset_n),
        .data_in      (parallel_out),
        .received_crc (received_crc),
        .crc_out      (crc_out),
        .crc_error    (crc_error)
    );

endmodule

module serial_in_parallel_out_8bit #(
    parameter WIDTH = 64,
    parameter SHIFT_DIRECTION = 1
) (
    input  logic             clk,
    input  logic             reset_n,
    input  logic             sin,
    input  logic             shift_en,
    output logic             done,
    output logic [WIDTH-1:0] parallel_out
);

    localparam COUNT_WIDTH = (WIDTH > 1) ? $clog2(WIDTH) : 1;

    logic [COUNT_WIDTH-1:0] shift_count;

    // Synchronous reset (design standard STD-RST-01 overrides the provided async reset).
    always_ff @(posedge clk) begin
        if (!reset_n) begin
            parallel_out <= '0;
            done         <= 1'b0;
            shift_count  <= '0;
        end else begin
            done <= 1'b0;
            if (shift_en) begin
                if (SHIFT_DIRECTION != 0) parallel_out <= {parallel_out[WIDTH-2:0], sin};
                else                      parallel_out <= {sin, parallel_out[WIDTH-1:1]};
                if (shift_count == COUNT_WIDTH'(WIDTH - 1)) begin
                    shift_count <= '0;
                    done        <= 1'b1;
                end else begin
                    shift_count <= shift_count + 1'b1;
                end
            end
        end
    end
endmodule

module onebit_ecc #(
    parameter DATA_WIDTH = 4,
    parameter CODE_WIDTH = DATA_WIDTH + $clog2(DATA_WIDTH + 1)
) (
    input  logic [DATA_WIDTH-1:0] data_in,
    output logic [CODE_WIDTH-1:0] encoded,
    input  logic [CODE_WIDTH-1:0] received,
    output logic [DATA_WIDTH-1:0] data_out,
    output logic                  error_detected,
    output logic                  error_corrected
);

    localparam PARITY_BITS = CODE_WIDTH - DATA_WIDTH;

    logic [PARITY_BITS-1:0] syndrome;
    logic [CODE_WIDTH-1:0]  corrected_data;

    always_comb begin
        int k;
        encoded = '0;
        k = 0;
        for (int i = 0; i < CODE_WIDTH; i++) begin
            if (((i + 1) & i) != 0) begin
                encoded[i] = data_in[k];
                k++;
            end
        end
        for (int i = 0; i < PARITY_BITS; i++) begin
            for (int j = 0; j < CODE_WIDTH; j++) begin
                if ((((j + 1) & (1 << i)) != 0) && ((j + 1) != (1 << i)))
                    encoded[(1 << i) - 1] = encoded[(1 << i) - 1] ^ encoded[j];
            end
        end
    end

    always_comb begin
        syndrome = '0;
        for (int m = 0; m < PARITY_BITS; m++)
            for (int n = 0; n < CODE_WIDTH; n++)
                if (((n + 1) & (1 << m)) != 0)
                    syndrome[m] = syndrome[m] ^ received[n];
    end

    assign error_detected  = |syndrome;
    assign error_corrected = error_detected;

    always_comb begin
        corrected_data = received;
        for (int n = 0; n < CODE_WIDTH; n++)
            if (int'(syndrome) == n + 1) corrected_data[n] = ~received[n];
    end

    always_comb begin
        int q;
        data_out = '0;
        q = 0;
        for (int p = 0; p < CODE_WIDTH; p++) begin
            if (((p + 1) & p) != 0) begin
                if (q < DATA_WIDTH) data_out[q] = corrected_data[p];
                q++;
            end
        end
    end

endmodule

module crc_generator #(
    parameter DATA_WIDTH = 16,
    parameter CRC_WIDTH  = DATA_WIDTH / 2,
    parameter [CRC_WIDTH-1:0] POLY = 8'b10101010
) (
    input  logic                  rst_n,
    input  logic [DATA_WIDTH-1:0] data_in,
    input  logic [CRC_WIDTH-1:0]  received_crc,
    output logic [CRC_WIDTH-1:0]  crc_out,
    output logic                  crc_error
);

    logic [CRC_WIDTH-1:0] crc_reg;

    always_comb begin
        crc_reg = '0;
        for (int i = DATA_WIDTH - 1; i >= 0; i--) begin
            if (crc_reg[CRC_WIDTH-1] ^ data_in[i]) crc_reg = (crc_reg << 1) ^ POLY;
            else                                   crc_reg = crc_reg << 1;
        end
    end

    assign crc_out   = rst_n ? crc_reg : '0;
    assign crc_error = (received_crc != crc_out);

endmodule
