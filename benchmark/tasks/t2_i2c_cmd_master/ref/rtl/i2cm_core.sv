// i2cm_core.sv: byte-command I2C master (open drain). One command at a time:
// START (repeated START when the bus is owned), WRITE byte, READ byte, STOP.
// Q = QUARTER clocks. Every SCL high time counts from SCL seen high, so a
// slave that stretches the clock is waited for.
module i2cm_core #(
    parameter int QUARTER = 250
) (
    input  logic       clk,
    input  logic       rst,
    input  logic       go,          // one clock; ignored while busy
    input  logic [2:0] op,
    input  logic [7:0] wdata,
    input  logic       rnack,
    input  logic       scl_in,      // synchronised bus levels
    input  logic       sda_in,
    output logic       scl_oe,      // 1 = pull low
    output logic       sda_oe,
    output logic       busy,
    output logic       owned,
    output logic       nack,
    output logic [7:0] rxdata
);
    localparam logic [2:0] OP_START = 3'd1, OP_WRITE = 3'd2, OP_READ = 3'd3, OP_STOP = 3'd4;
    localparam int CW = $clog2(2 * QUARTER + 1);

    typedef enum logic [3:0] {
        IDLE, S1, S2, R1, R2, R3, R4, B1, B2, B3, P1, P2, P3
    } st_t;
    st_t st;

    logic [CW-1:0] cnt;
    logic [3:0]    k;               // bit 0..8 of a byte command
    logic          rd, ack_n;
    logic [7:0]    sh;

    localparam logic [CW-1:0] Q1 = CW'(QUARTER - 1), Q2 = CW'(2 * QUARTER - 1);

    always_ff @(posedge clk) begin
        if (rst) begin
            st <= IDLE; cnt <= '0; k <= '0; rd <= 1'b0; ack_n <= 1'b0; sh <= '0;
            scl_oe <= 1'b0; sda_oe <= 1'b0; busy <= 1'b0; owned <= 1'b0; nack <= 1'b0; rxdata <= '0;
        end else begin
            case (st)
                IDLE: if (go) begin
                    case (op)
                        OP_START: begin
                            busy <= 1'b1;
                            if (owned) begin st <= R1; sda_oe <= 1'b0; cnt <= Q1; end
                            else       begin st <= S1; sda_oe <= 1'b1; cnt <= Q2; end
                        end
                        OP_WRITE, OP_READ: if (owned) begin
                            busy <= 1'b1;
                            st <= B1; k <= '0; rd <= op == OP_READ; ack_n <= rnack; sh <= wdata;
                            sda_oe <= (op == OP_WRITE) ? !wdata[7] : 1'b0;
                            cnt <= Q1;
                        end
                        OP_STOP: if (owned) begin
                            busy <= 1'b1;
                            st <= P1; sda_oe <= 1'b1; cnt <= Q1;
                        end
                        default: ;
                    endcase
                end
                // START on a free bus: SDA low (2Q), SCL low (Q)
                S1: if (cnt == '0) begin st <= S2; scl_oe <= 1'b1; cnt <= Q1; end else cnt <= cnt - 1'b1;
                S2: if (cnt == '0) begin st <= IDLE; busy <= 1'b0; owned <= 1'b1; end else cnt <= cnt - 1'b1;
                // repeated START
                R1: if (cnt == '0) begin st <= R2; scl_oe <= 1'b0; cnt <= Q2; end else cnt <= cnt - 1'b1;
                R2: if (!scl_in) cnt <= Q2;
                    else if (cnt == '0) begin st <= R3; sda_oe <= 1'b1; cnt <= Q2; end
                    else cnt <= cnt - 1'b1;
                R3: if (cnt == '0) begin st <= R4; scl_oe <= 1'b1; cnt <= Q1; end else cnt <= cnt - 1'b1;
                R4: if (cnt == '0) begin st <= IDLE; busy <= 1'b0; end else cnt <= cnt - 1'b1;
                // one bit of WRITE / READ: SDA set (Q), SCL high (2Q, sample), SCL low (Q)
                B1: if (cnt == '0) begin st <= B2; scl_oe <= 1'b0; cnt <= Q2; end else cnt <= cnt - 1'b1;
                B2: if (!scl_in) cnt <= Q2;
                    else if (cnt == '0) begin
                        st <= B3; scl_oe <= 1'b1; cnt <= Q1;
                        if (k == 4'd8) begin
                            if (!rd) nack <= sda_in;
                        end else begin
                            sh <= {sh[6:0], sda_in};
                        end
                    end else cnt <= cnt - 1'b1;
                B3: if (cnt == '0) begin
                        if (k == 4'd8) begin
                            st <= IDLE; busy <= 1'b0;
                            if (rd) rxdata <= sh;
                        end else begin
                            st <= B1; k <= k + 1'b1; cnt <= Q1;
                            if (k == 4'd7) sda_oe <= rd ? !ack_n : 1'b0;          // the ACK bit
                            else           sda_oe <= rd ? 1'b0 : !sh[7];           // sh already shifted
                        end
                    end else cnt <= cnt - 1'b1;
                // STOP: SDA low (Q), SCL high (2Q), SDA released (2Q)
                P1: if (cnt == '0) begin st <= P2; scl_oe <= 1'b0; cnt <= Q2; end else cnt <= cnt - 1'b1;
                P2: if (!scl_in) cnt <= Q2;
                    else if (cnt == '0) begin st <= P3; sda_oe <= 1'b0; cnt <= Q2; end
                    else cnt <= cnt - 1'b1;
                P3: if (cnt == '0) begin st <= IDLE; busy <= 1'b0; owned <= 1'b0; end else cnt <= cnt - 1'b1;
                default: st <= IDLE;
            endcase
        end
    end
endmodule
