// rp_freqcount: P1 frequency and period meter block (spec.yaml, ARCHITECTURE.md).
//
// Single clock domain (clk, 125 MHz). Reset rstn is active low at the port and is
// inverted once (rst, active high) for the synchronous reset of control and result
// registers. Datapath registers (adc_a compare, gate counter, first/last edge cycle)
// take no reset: they are loaded at each accepted START before use.
//
// Blocks (ARCHITECTURE.md):
//   reg_bus     : register decode, ack/err/rdata one cycle after the access, SCRATCH,
//                 CTRL (START/CONT), GATE_LEN, THR_HIGH, THR_LOW.
//   gate_ctrl   : gate sequencer, latches GATE_LEN and thresholds at START, counts the
//                 gate, BUSY/DONE, MEAS_DONE, publishes the results at the gate end.
//   edge_detect : signed 14-bit compare, armed state (carried across gates), BAD_THRESH.
//   span_meter  : EDGES count, first and last counted edge index, SPAN, FEW_EDGES.
//
// Cycle convention (matches model.py): an access driven in cycle k is answered by
// sys_ack, sys_rdata and sys_err after edge k, and reads the register state before
// edge k. An accepted START at edge s opens the gate for the samples of edges
// s+1 .. s+GATE_ACTUAL; the results are published at edge s+GATE_ACTUAL.

module rp_freqcount #(
    parameter int GATE_LEN_RESET_CYCLES = 125000000,
    parameter int MIN_GATE_CYCLES       = 1000,
    parameter int THR_HIGH_RESET        = 256,
    parameter int THR_LOW_RESET         = -256,
    parameter int BLOCK_WINDOW_BITS     = 20
) (
    input  logic        clk,
    input  logic        rstn,
    input  logic [31:0] sys_addr,
    input  logic [31:0] sys_wdata,
    input  logic        sys_wen,
    input  logic        sys_ren,
    output logic [31:0] sys_rdata,
    output logic        sys_err,
    output logic        sys_ack,
    input  logic [13:0] adc_a,
    /* verilator lint_off UNUSEDSIGNAL */
    input  logic [13:0] adc_b,       // IN2: not used by the block
    /* verilator lint_on UNUSEDSIGNAL */
    output logic [13:0] dac_a,
    output logic [13:0] dac_b
);

    // ------------------------------------------------------------------ constants
    localparam logic [31:0] WIN_MASK      = (32'd1 << BLOCK_WINDOW_BITS) - 32'd1;
    localparam logic [31:0] ID_VALUE      = 32'hFDA1_0101;
    localparam logic [31:0] GATE_LEN_RST  = 32'(GATE_LEN_RESET_CYCLES);
    localparam logic [31:0] MIN_GATE      = 32'(MIN_GATE_CYCLES);
    localparam logic [13:0] THR_HIGH_RST  = 14'(THR_HIGH_RESET);
    localparam logic [13:0] THR_LOW_RST   = 14'(THR_LOW_RESET);

    localparam logic [4:0] SEL_NONE        = 5'd0;
    localparam logic [4:0] SEL_ID          = 5'd1;
    localparam logic [4:0] SEL_SCRATCH     = 5'd2;
    localparam logic [4:0] SEL_CTRL        = 5'd3;
    localparam logic [4:0] SEL_GATE_LEN    = 5'd4;
    localparam logic [4:0] SEL_THR_HIGH    = 5'd5;
    localparam logic [4:0] SEL_THR_LOW     = 5'd6;
    localparam logic [4:0] SEL_STATUS      = 5'd7;
    localparam logic [4:0] SEL_EDGES       = 5'd8;
    localparam logic [4:0] SEL_GATE_ACTUAL = 5'd9;
    localparam logic [4:0] SEL_SPAN        = 5'd10;
    localparam logic [4:0] SEL_MEAS_DONE   = 5'd11;

    // one active-high reset inside the block, inverted once at the port
    wire rst = ~rstn;

    // ------------------------------------------------------------- reg_bus: decode
    // Only the window bits [BLOCK_WINDOW_BITS-1:0] are used; bits [1:0] must be 00.
    wire [31:0] off = sys_addr & WIN_MASK;

    logic [4:0] sel;
    always_comb begin
        sel = SEL_NONE;
        if (off[1:0] == 2'b00) begin
            case (off)
                32'h0000_0000: sel = SEL_ID;
                32'h0000_0004: sel = SEL_SCRATCH;
                32'h0000_0008: sel = SEL_CTRL;
                32'h0000_000C: sel = SEL_GATE_LEN;
                32'h0000_0010: sel = SEL_THR_HIGH;
                32'h0000_0014: sel = SEL_THR_LOW;
                32'h0000_0018: sel = SEL_STATUS;
                32'h0000_001C: sel = SEL_EDGES;
                32'h0000_0020: sel = SEL_GATE_ACTUAL;
                32'h0000_0024: sel = SEL_SPAN;
                32'h0000_0028: sel = SEL_MEAS_DONE;
                default:       sel = SEL_NONE;
            endcase
        end
    end

    wire is_ro = (sel == SEL_ID) || (sel == SEL_STATUS) || (sel == SEL_EDGES) ||
                 (sel == SEL_GATE_ACTUAL) || (sel == SEL_SPAN) || (sel == SEL_MEAS_DONE);

    // one access per cycle; a write takes precedence over a read (as in model.py)
    wire rd_acc   = sys_ren && !sys_wen;
    wire wr_rw    = sys_wen && (sel != SEL_NONE) && !is_ro;   // accepted write
    wire start_wr = wr_rw && (sel == SEL_CTRL) && sys_wdata[0];

    // ----------------------------------------------------------- state declarations
    logic [31:0] scratch;
    logic        cont;           // CTRL bit 1
    logic        busy;           // STATUS bit 0
    logic        done;           // STATUS bit 1
    logic [31:0] gate_len_reg;   // GATE_LEN register
    logic [13:0] thr_high_reg;   // THR_HIGH register (14 bits)
    logic [13:0] thr_low_reg;    // THR_LOW register (14 bits)

    logic [31:0] r_edges;        // published results
    logic [31:0] r_gate_actual;
    logic [31:0] r_span;
    logic [31:0] r_meas_done;
    logic        r_few;
    logic        r_bad;

    logic        armed;          // edge_detect: armed state, carried across gates
    logic [31:0] g_len;          // gate_ctrl: latched gate length
    logic [31:0] g_cnt;          // gate_ctrl: samples taken in this gate
    logic signed [13:0] g_hi;    // latched thresholds
    logic signed [13:0] g_lo;
    logic        g_bad;          // latched BAD_THRESH condition
    logic [31:0] g_edges;        // span_meter: counted edges in this gate
    logic [31:0] g_first;        // span_meter: index of first counted edge
    logic [31:0] g_last;         // span_meter: index of last counted edge

    // ------------------------------------------------------- gate_ctrl: sequencing
    wire start_acc = start_wr && !busy;          // START accepted (busy 0)
    wire gate_run  = busy;                       // a gate covers this edge's sample
    wire [31:0] cnt_nxt  = g_cnt + 32'd1;        // this sample's index in the gate
    wire gate_last = gate_run && (cnt_nxt == g_len);
    wire relatch   = gate_last && cont;          // CONT: next gate opens on this edge
    wire latch     = start_acc || relatch;

    // ------------------------------------------------------- edge_detect
    wire signed [13:0] a_s   = adc_a;
    wire               edge_hit = gate_run && armed && (a_s >= g_hi) && !g_bad;
    wire               arm_set  = gate_run && (a_s <= g_lo);

    always_ff @(posedge clk) begin
        if (rst)           armed <= 1'b0;
        else if (edge_hit) armed <= 1'b0;
        else if (arm_set)  armed <= 1'b1;
    end

    // ------------------------------------------------------- span_meter
    wire [31:0] edges_nxt  = g_edges + {31'd0, edge_hit};
    wire        first_edge = edge_hit && (g_edges == 32'd0);
    wire [31:0] first_nxt  = first_edge ? cnt_nxt : g_first;
    wire [31:0] last_nxt   = edge_hit ? cnt_nxt : g_last;

    // gate datapath: loaded at START (or CONT re-latch), no reset
    always_ff @(posedge clk) begin
        if (latch) begin
            g_len   <= gate_len_reg;
            g_hi    <= $signed(thr_high_reg);
            g_lo    <= $signed(thr_low_reg);
            g_bad   <= ($signed(thr_high_reg) <= $signed(thr_low_reg));
            g_cnt   <= 32'd0;
            g_edges <= 32'd0;
            g_first <= 32'd0;
            g_last  <= 32'd0;
        end else if (gate_run) begin
            g_cnt   <= cnt_nxt;
            g_edges <= edges_nxt;
            g_first <= first_nxt;
            g_last  <= last_nxt;
        end
    end

    // ------------------------------------------------ control registers (reset)
    always_ff @(posedge clk) begin
        if (rst) begin
            cont <= 1'b0;
            busy <= 1'b0;
            done <= 1'b0;
        end else begin
            if (wr_rw && (sel == SEL_CTRL)) begin
                if (!sys_wdata[0]) begin
                    cont <= sys_wdata[1];
                end else if (!busy) begin          // START accepted
                    cont <= sys_wdata[1];
                    busy <= 1'b1;
                    done <= 1'b0;
                end
                // START while busy: no register changes
            end
            if (gate_last) begin                   // gate ends this edge
                done <= 1'b1;
                if (!cont) busy <= 1'b0;
            end
        end
    end

    // ------------------------------------------ writable data registers (reset)
    always_ff @(posedge clk) begin
        if (rst) begin
            scratch      <= 32'd0;
            gate_len_reg <= GATE_LEN_RST;
            thr_high_reg <= THR_HIGH_RST;
            thr_low_reg  <= THR_LOW_RST;
        end else if (wr_rw) begin
            case (sel)
                SEL_SCRATCH:  scratch      <= sys_wdata;
                SEL_GATE_LEN: gate_len_reg <= (sys_wdata < MIN_GATE) ? MIN_GATE : sys_wdata;
                SEL_THR_HIGH: thr_high_reg <= sys_wdata[13:0];
                SEL_THR_LOW:  thr_low_reg  <= sys_wdata[13:0];
                default: ;
            endcase
        end
    end

    // ------------------------------------ published results, all at gate end (reset)
    always_ff @(posedge clk) begin
        if (rst) begin
            r_edges       <= 32'd0;
            r_gate_actual <= 32'd0;
            r_span        <= 32'd0;
            r_meas_done   <= 32'd0;
            r_few         <= 1'b0;
            r_bad         <= 1'b0;
        end else if (gate_last) begin
            r_edges       <= edges_nxt;
            r_gate_actual <= g_len;
            r_span        <= (edges_nxt >= 32'd2) ? (last_nxt - first_nxt) : 32'd0;
            r_few         <= (edges_nxt < 32'd2);
            r_bad         <= g_bad;
            r_meas_done   <= r_meas_done + 32'd1;
        end
    end

    // ------------------------------------------------ reg_bus: read mux and answers
    logic [31:0] rd_val;
    always_comb begin
        case (sel)
            SEL_ID:          rd_val = ID_VALUE;
            SEL_SCRATCH:     rd_val = scratch;
            SEL_CTRL:        rd_val = {30'd0, cont, 1'b0};
            SEL_GATE_LEN:    rd_val = gate_len_reg;
            SEL_THR_HIGH:    rd_val = {{18{thr_high_reg[13]}}, thr_high_reg};
            SEL_THR_LOW:     rd_val = {{18{thr_low_reg[13]}}, thr_low_reg};
            SEL_STATUS:      rd_val = {28'd0, r_bad, r_few, done, busy};
            SEL_EDGES:       rd_val = r_edges;
            SEL_GATE_ACTUAL: rd_val = r_gate_actual;
            SEL_SPAN:        rd_val = r_span;
            SEL_MEAS_DONE:   rd_val = r_meas_done;
            default:         rd_val = 32'd0;
        endcase
    end

    always_ff @(posedge clk) begin
        if (rst) begin
            sys_ack <= 1'b0;
            sys_err <= 1'b0;
        end else begin
            sys_ack <= sys_wen || sys_ren;
            sys_err <= (sys_wen || sys_ren) && ((sel == SEL_NONE) || (sys_wen && is_ro));
        end
        sys_rdata <= rd_acc ? rd_val : 32'd0;
    end

    // ------------------------------------------------------------ DAC outputs
    assign dac_a = 14'd0;
    assign dac_b = 14'd0;

endmodule
