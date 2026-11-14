// dds_awg: direct-digital-synthesis stimulus source. A PHASE_W-bit accumulator advances by `step` on every
// `tick`; the wave is a sine from a 2^LUT_W-entry table, a triangle, a rising saw or a square. f_out = f_tick * step /
// 2^PHASE_W. Output is signed OUT_W bits, scaled down by amp_shift (0 = full scale).
// Implementation variants, same ports, function and latency, selected by IMPL:
//   "bram"  the sine table is a ROM with a registered read (block RAM): the read address is the next phase, phase + step,
//           so the registered table output always belongs to the current phase
//   "lut"   the sine table is an asynchronous ROM in LUTs, read straight from the phase register
module dds_awg #(
    parameter     IMPL    = "bram",      // a string: "bram" or "lut"
    parameter int PHASE_W = 32,
    parameter int LUT_W   = 8,           // sine table address bits
    parameter int OUT_W   = 16
) (
    input  logic                     clk,
    input  logic                     rst,
    input  logic                     tick,        // sample-rate enable
    input  logic [PHASE_W-1:0]       step,
    input  logic [1:0]               wave,        // 0 sine, 1 triangle, 2 saw, 3 square
    input  logic [3:0]               amp_shift,
    output logic signed [OUT_W-1:0]  sample,
    output logic [PHASE_W-1:0]       phase_o
);
    initial begin
        if (!(IMPL == "bram" || IMPL == "lut")) $error("dds_awg: IMPL %s is not bram or lut", IMPL);
        if (PHASE_W < 8 || PHASE_W > 48) $error("dds_awg: PHASE_W %0d outside 8..48", PHASE_W);
        if (LUT_W < 4 || LUT_W > 12 || LUT_W > PHASE_W) $error("dds_awg: LUT_W %0d outside 4..12 and <= PHASE_W", LUT_W);
        if (OUT_W < 4 || OUT_W > 24) $error("dds_awg: OUT_W %0d outside 4..24", OUT_W);
    end

    localparam int N = 1 << LUT_W;
    localparam real PI = 3.14159265358979323846;
    // The sine table as one constant: entry i is sin(2*pi*i/N) scaled to the output range and truncated toward zero. It is
    // computed by a constant function, so the tools evaluate it at elaboration (the reset check's front end cannot run
    // real arithmetic inside an initial block; brief 70). The cast int'(real) rounds, so the function undoes the rounding
    // when it went away from zero: the same values as truncating with $rtoi.
    function automatic logic [N*OUT_W-1:0] make_table();
        real v;
        int  t;
        logic [N*OUT_W-1:0] r;
        r = '0;
        for (int i = 0; i < N; i++) begin
            v = $sin(2.0 * PI * i / N) * ((1 << (OUT_W - 1)) - 1);
            t = int'(v);
            if (v >= 0.0 && real'(t) > v) t = t - 1;
            else if (v < 0.0 && real'(t) < v) t = t + 1;
            r[i*OUT_W +: OUT_W] = OUT_W'(t);
        end
        return r;
    endfunction
    localparam logic [N*OUT_W-1:0] TABLE = make_table();
    function automatic logic signed [OUT_W-1:0] sine_entry(input int i);
        return TABLE[i*OUT_W +: OUT_W];
    endfunction

    logic [PHASE_W-1:0] phase, phase_next;
    assign phase_o    = phase;
    assign phase_next = phase + step;
    logic signed [OUT_W-1:0] sine;         // the table entry for the current phase
    generate
        if (IMPL == "lut") begin : g_lut
            (* rom_style = "distributed" *) logic signed [OUT_W-1:0] lut [0:N-1];
            initial for (int i = 0; i < N; i++) lut[i] = sine_entry(i);
            assign sine = lut[phase[PHASE_W-1 -: LUT_W]];
        end else begin : g_bram
            (* rom_style = "block" *) logic signed [OUT_W-1:0] rom [0:N-1];
            initial for (int i = 0; i < N; i++) rom[i] = sine_entry(i);
            // The block RAM has no reset and no enable pin driven from the reset (AMD DRC REQP-1840: a block-RAM control pin
            // must not come from a register with an asynchronous set or reset, and our reset comes from the shell's reset
            // bridge). The reset and the tick choose the address instead: reset reads entry 0 (zero), a tick reads the next
            // phase's entry, otherwise the current entry is read again, so the register holds. Same values as before.
            wire [LUT_W-1:0] rom_addr = rst ? '0 : tick ? phase_next[PHASE_W-1 -: LUT_W] : phase[PHASE_W-1 -: LUT_W];
            always_ff @(posedge clk) sine <= rom[rom_addr];
        end
    endgenerate
    logic signed [OUT_W-1:0] raw;
    logic [OUT_W-1:0] top, tri_u;
    localparam logic [OUT_W-1:0] SIGN = {1'b1, {(OUT_W-1){1'b0}}};
    always_comb begin
        top   = phase[PHASE_W-1 -: OUT_W];
        tri_u = top[OUT_W-1] ? (~top << 1) : (top << 1);
        case (wave)
            2'd0: raw = sine;
            2'd1: raw = tri_u ^ SIGN;
            2'd2: raw = top ^ SIGN;
            default: raw = top[OUT_W-1] ? SIGN : ~SIGN;
        endcase
    end
    always_ff @(posedge clk) begin
        if (rst) begin
            phase <= '0;
            sample <= '0;
        end else if (tick) begin
            phase  <= phase_next;
            sample <= raw >>> amp_shift;
        end
    end
endmodule
