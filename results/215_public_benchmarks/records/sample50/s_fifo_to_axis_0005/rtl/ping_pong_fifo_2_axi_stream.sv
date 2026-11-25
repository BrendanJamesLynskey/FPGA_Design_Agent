// Ping-pong FIFO to AXI-Stream style bridge with flush and pause.
// rst is sampled synchronously at i_axi_clk (clears every register at the next edge);
// i_flush is a synchronous clear with priority over every other input.
module ping_pong_fifo_2_axi_stream #(
    parameter int DATA_WIDTH = 32
)(
    input  logic                           rst,

    // Ping Pong FIFO read interface
    input  logic                           i_block_fifo_rdy,
    output logic                           o_block_fifo_act,
    input  logic [23:0]                    i_block_fifo_size,
    input  logic [DATA_WIDTH:0]            i_block_fifo_data,
    output logic                           o_block_fifo_stb,
    input  logic [3:0]                     i_axi_user,
    input  logic                           i_flush,
    input  logic                           i_pause,

    // AXI-Stream style output
    input  logic                           i_axi_clk,
    output logic [3:0]                     o_axi_user,
    input  logic                           i_axi_ready,
    output logic [DATA_WIDTH-1:0]          o_axi_data,
    output logic                           o_axi_last,
    output logic                           o_axi_valid
);

    typedef enum logic [1:0] {
        IDLE      = 2'd0,
        READ_FIFO = 2'd1,
        SEND_AXI  = 2'd2
    } state_t;

    state_t             state;
    logic [23:0]        block_size_reg;
    logic [23:0]        data_count;
    logic [DATA_WIDTH-1:0] fifo_data_reg;
    logic               fifo_data_valid;
    logic               data_pending;

    logic clr;
    assign clr = rst | i_flush;

    always_ff @(posedge i_axi_clk) begin
        if (clr) begin
            state            <= IDLE;
            block_size_reg   <= 24'd0;
            data_count       <= 24'd0;
            fifo_data_reg    <= '0;
            fifo_data_valid  <= 1'b0;
            data_pending     <= 1'b0;
            o_block_fifo_act <= 1'b0;
            o_block_fifo_stb <= 1'b0;
            o_axi_valid      <= 1'b0;
            o_axi_last       <= 1'b0;
            o_axi_user       <= 4'd0;
            o_axi_data       <= '0;
        end else begin
            o_block_fifo_act <= 1'b0;
            o_block_fifo_stb <= 1'b0;
            o_axi_valid      <= 1'b0;
            o_axi_last       <= 1'b0;
            o_axi_user       <= 4'd0;

            case (state)
                IDLE: begin
                    if (i_block_fifo_rdy) begin
                        o_block_fifo_act <= 1'b1;
                        block_size_reg   <= i_block_fifo_size;
                        data_count       <= 24'd0;
                        data_pending     <= 1'b1;
                        state            <= READ_FIFO;
                    end
                end

                READ_FIFO: begin
                    o_block_fifo_stb <= 1'b1;
                    fifo_data_reg    <= i_block_fifo_data[DATA_WIDTH-1:0];
                    fifo_data_valid  <= 1'b1;
                    data_count       <= data_count + 24'd1;
                    data_pending     <= 1'b0;
                    state            <= SEND_AXI;
                end

                // SEND_AXI (state 3 is unreachable and treated the same)
                default: begin
                    if (fifo_data_valid && i_axi_ready && !i_pause) begin
                        o_axi_valid     <= 1'b1;
                        o_axi_data      <= fifo_data_reg;
                        o_axi_user      <= i_axi_user;
                        fifo_data_valid <= 1'b0;
                        if (data_count >= block_size_reg) begin
                            o_axi_last <= 1'b1;
                            state      <= IDLE;
                        end else begin
                            data_pending <= 1'b1;
                            state        <= READ_FIFO;
                        end
                    end
                end
            endcase
        end
    end

    // data_pending is internal state kept per the spec; unused by outputs.
    /* verilator lint_off UNUSEDSIGNAL */
    logic unused_ok;
    assign unused_ok = data_pending ^ i_block_fifo_data[DATA_WIDTH];
    /* verilator lint_on UNUSEDSIGNAL */

endmodule
