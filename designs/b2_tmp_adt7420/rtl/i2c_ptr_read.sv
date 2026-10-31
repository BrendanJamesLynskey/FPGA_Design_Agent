// i2c_ptr_read.sv: I2C master that does one thing: set a device's register
// pointer, then read 1 or 2 bytes from it (START, address+W, pointer,
// repeated START, address+R, bytes, STOP). It never writes a data byte, so it
// cannot change a device's configuration. Open-drain: *_oe = 1 pulls the line
// low, 0 releases it to the board's pull-up. SCL is held while a device
// stretches it (scl_in low while released).
//
// Each bit is four quarters of QUARTER clocks (250 = 100 kHz at 100 MHz).

module i2c_ptr_read #(
    parameter int          QUARTER  = 250,
    parameter logic [6:0]  DEV_ADDR = 7'h4B
) (
    input  logic        clk,
    input  logic        rst,
    input  logic        go,        // one-cycle start pulse (ignored while busy)
    input  logic [7:0]  ptr,       // register pointer to set
    input  logic [1:0]  nbytes,    // bytes to read: 2 reads two, anything else reads one
    output logic        busy,
    output logic        done,      // set at STOP, cleared by the next go
    output logic        nack,      // a byte was not acknowledged (the transfer stopped there)
    output logic [15:0] rdata,     // bytes read, first byte in the higher half for a 2-byte read
    output logic        scl_oe,
    output logic        sda_oe,
    input  logic        scl_in,    // synchronised line levels
    input  logic        sda_in
);
    typedef enum logic [2:0] {S_IDLE, S_START, S_WBIT, S_RACK, S_RBIT, S_WACK, S_STOP} st_t;
    st_t         st;
    logic [1:0]  q;          // quarter of the current bit
    logic [15:0] div;
    logic [7:0]  sh;
    logic [2:0]  bitn;
    logic [1:0]  seq;        // 0 address+W, 1 pointer, 2 address+R (after the repeated START)
    logic [1:0]  left;       // bytes still to read
    logic        ack_bit;
    logic        scl_high_wanted, stretched, tick;

    // SCL is released in quarters 1 and 2 of every element except IDLE
    assign scl_high_wanted = (st != S_IDLE) && (q == 2'd1 || q == 2'd2);
    assign stretched       = scl_high_wanted && !scl_in;
    assign tick            = (st != S_IDLE) && (div == 16'(QUARTER - 1)) && !stretched;

    always_ff @(posedge clk) begin
        if (rst) begin
            st <= S_IDLE; q <= '0; div <= '0; sh <= '0; bitn <= '0; seq <= '0; left <= '0;
            ack_bit <= 1'b0; busy <= 1'b0; done <= 1'b0; nack <= 1'b0; rdata <= '0;
        end else if (st == S_IDLE) begin
            if (go) begin
                st <= S_START; q <= '0; div <= '0; seq <= '0;
                left <= (nbytes == 2'd2) ? 2'd2 : 2'd1;
                busy <= 1'b1; done <= 1'b0; nack <= 1'b0; rdata <= '0;
            end
        end else begin
            div <= tick ? '0 : (stretched ? div : div + 16'd1);
            if (tick) begin
                q <= q + 2'd1;
                if (q == 2'd2) begin
                    if (st == S_RACK) ack_bit <= sda_in;
                    if (st == S_RBIT) sh <= {sh[6:0], sda_in};
                end
                if (q == 2'd3) begin
                    unique case (st)
                        S_START: begin
                            st <= S_WBIT; bitn <= 3'd7; sh <= {DEV_ADDR, seq == 2'd2};
                        end
                        S_WBIT: begin
                            if (bitn == 3'd0) st <= S_RACK;
                            else begin bitn <= bitn - 3'd1; sh <= {sh[6:0], 1'b0}; end
                        end
                        S_RACK: begin
                            if (ack_bit) begin nack <= 1'b1; st <= S_STOP; end
                            else unique case (seq)
                                2'd0:    begin st <= S_WBIT; sh <= ptr; bitn <= 3'd7; seq <= 2'd1; end
                                2'd1:    begin st <= S_START; seq <= 2'd2; end
                                default: begin st <= S_RBIT; bitn <= 3'd7; end
                            endcase
                        end
                        S_RBIT: begin
                            if (bitn == 3'd0) begin
                                rdata <= {rdata[7:0], sh}; left <= left - 2'd1; st <= S_WACK;
                            end else bitn <= bitn - 3'd1;
                        end
                        S_WACK: begin
                            if (left != 2'd0) begin st <= S_RBIT; bitn <= 3'd7; end
                            else st <= S_STOP;
                        end
                        S_STOP: begin st <= S_IDLE; busy <= 1'b0; done <= 1'b1; end
                        default: st <= S_IDLE;
                    endcase
                end
            end
        end
    end

    // Line levels for each element and quarter (registered: no glitches on the bus)
    always_ff @(posedge clk) begin
        if (rst) begin
            scl_oe <= 1'b0; sda_oe <= 1'b0;
        end else begin
            unique case (st)
                S_IDLE:  begin scl_oe <= 1'b0;             sda_oe <= 1'b0; end
                // a repeated START (seq 2) keeps SCL low in quarter 0 while SDA is released,
                // so the bus never sees SDA rise with SCL high (that would be a STOP)
                S_START: begin scl_oe <= (q == 2'd3) || (q == 2'd0 && seq == 2'd2);
                               sda_oe <= (q >= 2'd2); end
                S_WBIT:  begin scl_oe <= (q == 2'd0 || q == 2'd3); sda_oe <= ~sh[7]; end
                S_RACK,
                S_RBIT:  begin scl_oe <= (q == 2'd0 || q == 2'd3); sda_oe <= 1'b0; end
                S_WACK:  begin scl_oe <= (q == 2'd0 || q == 2'd3); sda_oe <= (left != 2'd0); end
                S_STOP:  begin scl_oe <= (q == 2'd0);      sda_oe <= (q <= 2'd1); end
                default: begin scl_oe <= 1'b0;             sda_oe <= 1'b0; end
            endcase
        end
    end
endmodule
