// scan_core.sv: I2C address scanner. Probes 0x08..0x77: START, {addr, W},
// ACK bit, STOP. Records answering addresses. Open drain; waits for SCL to be
// seen high after each release (clock stretching).
module scan_core #(
    parameter int QUARTER = 250
) (
    input  logic         clk,
    input  logic         rst,
    input  logic         go,
    input  logic         scl_in,
    input  logic         sda_in,
    output logic         scl_oe,
    output logic         sda_oe,
    output logic         busy,
    output logic         done,
    output logic [7:0]   count,
    output logic [7:0]   lowest,
    output logic [127:0] map
);
    localparam int CW = $clog2(2 * QUARTER + 1);
    localparam logic [CW-1:0] Q1 = CW'(QUARTER - 1), Q2 = CW'(2 * QUARTER - 1);

    typedef enum logic [3:0] {IDLE, S1, S2, B1, B2, B3, P1, P2, P3} st_t;
    st_t st;

    logic [CW-1:0] cnt;
    logic [3:0]    k;
    logic [6:0]    addr;
    logic          acked;
    logic [7:0]    byte_out;

    assign byte_out = {addr, 1'b0};

    always_ff @(posedge clk) begin
        if (rst) begin
            st <= IDLE; cnt <= '0; k <= '0; addr <= 7'h08; acked <= 1'b0;
            scl_oe <= 1'b0; sda_oe <= 1'b0; busy <= 1'b0; done <= 1'b0;
            count <= '0; lowest <= 8'hFF; map <= '0;
        end else begin
            case (st)
                IDLE: if (go) begin
                    busy <= 1'b1; done <= 1'b0; count <= '0; lowest <= 8'hFF; map <= '0;
                    addr <= 7'h08;
                    st <= S1; sda_oe <= 1'b1; cnt <= Q2;
                end
                S1: if (cnt == '0) begin st <= S2; scl_oe <= 1'b1; cnt <= Q1; end else cnt <= cnt - 1'b1;
                S2: if (cnt == '0) begin
                        st <= B1; k <= '0; cnt <= Q1; sda_oe <= !byte_out[7];
                    end else cnt <= cnt - 1'b1;
                B1: if (cnt == '0) begin st <= B2; scl_oe <= 1'b0; cnt <= Q2; end else cnt <= cnt - 1'b1;
                B2: if (!scl_in) cnt <= Q2;
                    else if (cnt == '0) begin
                        st <= B3; scl_oe <= 1'b1; cnt <= Q1;
                        if (k == 4'd8) acked <= !sda_in;
                    end else cnt <= cnt - 1'b1;
                B3: if (cnt == '0) begin
                        if (k == 4'd8) begin
                            st <= P1; sda_oe <= 1'b1; cnt <= Q1;
                            if (acked) begin
                                map[addr] <= 1'b1;
                                count <= count + 1'b1;
                                if (lowest == 8'hFF) lowest <= {1'b0, addr};
                            end
                        end else begin
                            st <= B1; k <= k + 1'b1; cnt <= Q1;
                            sda_oe <= (k == 4'd7) ? 1'b0 : !byte_out[3'd6 - k[2:0]];
                        end
                    end else cnt <= cnt - 1'b1;
                P1: if (cnt == '0) begin st <= P2; scl_oe <= 1'b0; cnt <= Q2; end else cnt <= cnt - 1'b1;
                P2: if (!scl_in) cnt <= Q2;
                    else if (cnt == '0) begin st <= P3; sda_oe <= 1'b0; cnt <= Q2; end
                    else cnt <= cnt - 1'b1;
                P3: if (cnt == '0) begin
                        if (addr == 7'h77) begin
                            st <= IDLE; busy <= 1'b0; done <= 1'b1;
                        end else begin
                            addr <= addr + 1'b1;
                            st <= S1; sda_oe <= 1'b1; cnt <= Q2;
                        end
                    end else cnt <= cnt - 1'b1;
                default: st <= IDLE;
            endcase
        end
    end
endmodule
