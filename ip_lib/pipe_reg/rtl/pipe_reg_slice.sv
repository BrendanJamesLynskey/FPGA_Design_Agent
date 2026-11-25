// pipe_reg_slice.sv: the five one-stage building blocks of pipe_reg (brief 151). Every slice has the same ports:
// a valid/ready input (s_*) and a valid/ready output (m_*), one clock, one synchronous reset, no reset on data.
// A beat is accepted when s_valid and s_ready are both high at a clock edge; it leaves when m_valid and m_ready are.
// Latency is counted from the edge that accepts a beat into an empty slice to the first clock in which it is visible
// at m_*: one clock for every slice here.
// What a user could guess wrong (also in ip.yaml):
//   * s_ready of the comb slice depends on m_ready in the same clock (a combinational path through the slice);
//     in the other three slices it is a flop (or the inverse of one) and never depends on m_ready in the same clock.
//   * The half slice moves one beat per two clocks, never one per clock.
//   * No slice accepts a beat while rst is high: a source must hold s_valid low during reset (the registers are
//     cleared whatever the handshake says). The comb slice's s_ready is not held low in reset.
//   * m_data is undefined (not reset) while m_valid is low.

// One entry, ready combinational from m_ready: full throughput, one register on the forward path.
module pipe_slice_comb #(
    parameter int W = 32
) (
    input  logic         clk,
    input  logic         rst,
    input  logic         s_valid,
    output logic         s_ready,
    input  logic [W-1:0] s_data,
    output logic         m_valid,
    input  logic         m_ready,
    output logic [W-1:0] m_data
`ifdef FORMAL
    , output logic [W-1:0] f_in_o, f_out_o
`endif
);
    assign s_ready = !m_valid || m_ready;
    always_ff @(posedge clk) begin
        if (rst) m_valid <= 1'b0;
        else if (s_ready) m_valid <= s_valid;
        if (s_ready && s_valid) m_data <= s_data;
    end

`ifdef FORMAL
    // Properties for SymbiYosys (formal/pipe.sby), proved by k-induction together with the wrapper's. Ghost counters
    // (W bits, wrapping) count the beats accepted and delivered; the wrapper makes the source number its beats 0, 1, 2 ...
    // so a beat's data is its place in the stream, and every stored beat must hold the number its position implies.
    logic f_init = 1'b1;
    always_ff @(posedge clk) f_init <= rst;
    logic [W-1:0] f_in, f_out;
    assign f_in_o = f_in;
    assign f_out_o = f_out;
    wire f_push = s_valid && s_ready;
    wire f_pop  = m_valid && m_ready;
    always_ff @(posedge clk) begin
        if (rst) begin f_in <= '0; f_out <= '0; end
        else begin
            if (f_push) f_in <= f_in + W'(1);
            if (f_pop)  f_out <= f_out + W'(1);
        end
    end
    always_ff @(posedge clk) if (!f_init && !rst) begin
        comb_count: assert (W'(f_in - f_out) == W'(m_valid));
        if (m_valid) comb_data: assert (m_data == f_out);
        comb_holds__ante: cover (m_valid);
    end
`endif
endmodule

// One entry, ready a flop: a beat is accepted only into an empty slice, so throughput is one beat per two clocks.
module pipe_slice_half #(
    parameter int W = 32
) (
    input  logic         clk,
    input  logic         rst,
    input  logic         s_valid,
    output logic         s_ready,
    input  logic [W-1:0] s_data,
    output logic         m_valid,
    input  logic         m_ready,
    output logic [W-1:0] m_data
`ifdef FORMAL
    , output logic [W-1:0] f_in_o, f_out_o
`endif
);
    logic v_next;
    always_comb begin
        v_next = m_valid;
        if (s_ready && s_valid) v_next = 1'b1;
        else if (m_valid && m_ready) v_next = 1'b0;
    end
    always_ff @(posedge clk) begin
        if (rst) begin
            m_valid <= 1'b0;
            s_ready <= 1'b0;
        end else begin
            m_valid <= v_next;
            s_ready <= !v_next;
        end
        if (s_ready && s_valid) m_data <= s_data;
    end

`ifdef FORMAL
    // Properties for SymbiYosys (formal/pipe.sby), proved by k-induction together with the wrapper's. Ghost counters
    // (W bits, wrapping) count the beats accepted and delivered; the wrapper makes the source number its beats 0, 1, 2 ...
    // so a beat's data is its place in the stream, and every stored beat must hold the number its position implies.
    logic f_init = 1'b1;
    always_ff @(posedge clk) f_init <= rst;
    logic [W-1:0] f_in, f_out;
    assign f_in_o = f_in;
    assign f_out_o = f_out;
    wire f_push = s_valid && s_ready;
    wire f_pop  = m_valid && m_ready;
    always_ff @(posedge clk) begin
        if (rst) begin f_in <= '0; f_out <= '0; end
        else begin
            if (f_push) f_in <= f_in + W'(1);
            if (f_pop)  f_out <= f_out + W'(1);
        end
    end
    always_ff @(posedge clk) if (!f_init && !rst) begin
        half_count: assert (W'(f_in - f_out) == W'(m_valid));
        if (m_valid) half_data: assert (m_data == f_out);
        if (s_ready) half_ready_empty: assert (!m_valid);
        half_holds__ante: cover (m_valid);
        half_ready__ante: cover (s_ready);
    end
`endif
endmodule

// Skid buffer: an output register plus one side register that catches the beat that arrives in the clock after
// m_ready falls (the registered s_ready cannot react in time). Full throughput, s_ready a flop, two beats of storage.
// Invariant: the side register holds a beat only while s_ready is low.
module pipe_slice_skid #(
    parameter int W = 32
) (
    input  logic         clk,
    input  logic         rst,
    input  logic         s_valid,
    output logic         s_ready,
    input  logic [W-1:0] s_data,
    output logic         m_valid,
    input  logic         m_ready,
    output logic [W-1:0] m_data
`ifdef FORMAL
    , output logic [W-1:0] f_in_o, f_out_o
`endif
);
    logic         t_valid;
    logic [W-1:0] t_data;
    // s_ready in the next clock: low only when the side register is, or is about to be, occupied
    wire s_ready_next = m_ready || (!t_valid && (!m_valid || !s_valid));
    always_ff @(posedge clk) begin
        if (rst) begin
            m_valid <= 1'b0;
            t_valid <= 1'b0;
            s_ready <= 1'b0;
        end else begin
            s_ready <= s_ready_next;
            if (s_ready) begin
                if (m_ready || !m_valid) m_valid <= s_valid;            // straight to the output register
                else                     t_valid <= s_valid;            // output stalled: park it in the side register
            end else if (m_ready) begin
                m_valid <= t_valid;                                     // side register drains into the output
                t_valid <= 1'b0;
            end
        end
        if (s_ready) begin
            if (m_ready || !m_valid) m_data <= s_data;
            else                     t_data <= s_data;
        end else if (m_ready) m_data <= t_data;
    end

`ifdef FORMAL
    // Properties for SymbiYosys (formal/pipe.sby), proved by k-induction together with the wrapper's. Ghost counters
    // (W bits, wrapping) count the beats accepted and delivered; the wrapper makes the source number its beats 0, 1, 2 ...
    // so a beat's data is its place in the stream, and every stored beat must hold the number its position implies.
    logic f_init = 1'b1;
    always_ff @(posedge clk) f_init <= rst;
    logic [W-1:0] f_in, f_out;
    assign f_in_o = f_in;
    assign f_out_o = f_out;
    wire f_push = s_valid && s_ready;
    wire f_pop  = m_valid && m_ready;
    always_ff @(posedge clk) begin
        if (rst) begin f_in <= '0; f_out <= '0; end
        else begin
            if (f_push) f_in <= f_in + W'(1);
            if (f_pop)  f_out <= f_out + W'(1);
        end
    end
    always_ff @(posedge clk) if (!f_init && !rst) begin
        skid_count: assert (W'(f_in - f_out) == W'(m_valid) + W'(t_valid));
        if (m_valid) skid_data: assert (m_data == f_out);
        if (t_valid) begin
            skid_t_main: assert (m_valid);
            skid_t_stall: assert (!s_ready);
            skid_t_data: assert (t_data == f_out + W'(1));
        end
        skid_holds__ante: cover (m_valid);
        skid_spill__ante: cover (t_valid);
    end
`endif
endmodule

// Full register slice: two entries written alternately, every control output a flop (valid and ready). The output
// data is a 2:1 read of the two entries. Full throughput; behaves cycle for cycle like the skid buffer.
module pipe_slice_full #(
    parameter int W = 32
) (
    input  logic         clk,
    input  logic         rst,
    input  logic         s_valid,
    output logic         s_ready,
    input  logic [W-1:0] s_data,
    output logic         m_valid,
    input  logic         m_ready,
    output logic [W-1:0] m_data
`ifdef FORMAL
    , output logic [W-1:0] f_in_o, f_out_o
`endif
);
    logic [W-1:0] e0, e1;
    logic         wp, rp;
    logic [1:0]   cnt;
    wire push = s_valid && s_ready;
    wire pop  = m_valid && m_ready;
    logic [1:0] cnt_next;
    always_comb begin
        cnt_next = cnt;
        if (push && !pop) cnt_next = cnt + 2'd1;
        else if (!push && pop) cnt_next = cnt - 2'd1;
    end
    assign m_data = rp ? e1 : e0;
    always_ff @(posedge clk) begin
        if (rst) begin
            cnt     <= 2'd0;
            wp      <= 1'b0;
            rp      <= 1'b0;
            m_valid <= 1'b0;
            s_ready <= 1'b0;
        end else begin
            cnt     <= cnt_next;
            m_valid <= (cnt_next != 2'd0);
            s_ready <= (cnt_next != 2'd2);
            if (push) wp <= !wp;
            if (pop)  rp <= !rp;
        end
        if (push) begin
            if (wp) e1 <= s_data;
            else    e0 <= s_data;
        end
    end

`ifdef FORMAL
    // Properties for SymbiYosys (formal/pipe.sby), proved by k-induction together with the wrapper's. Ghost counters
    // (W bits, wrapping) count the beats accepted and delivered; the wrapper makes the source number its beats 0, 1, 2 ...
    // so a beat's data is its place in the stream, and every stored beat must hold the number its position implies.
    logic f_init = 1'b1;
    always_ff @(posedge clk) f_init <= rst;
    logic [W-1:0] f_in, f_out;
    assign f_in_o = f_in;
    assign f_out_o = f_out;
    wire f_push = s_valid && s_ready;
    wire f_pop  = m_valid && m_ready;
    always_ff @(posedge clk) begin
        if (rst) begin f_in <= '0; f_out <= '0; end
        else begin
            if (f_push) f_in <= f_in + W'(1);
            if (f_pop)  f_out <= f_out + W'(1);
        end
    end
    always_ff @(posedge clk) if (!f_init && !rst) begin
        full_count: assert (W'(f_in - f_out) == W'(cnt));
        full_cnt_max: assert (cnt <= 2'd2);
        full_valid: assert (m_valid == (cnt != 2'd0));
        full_wp: assert (wp == (rp ^ (cnt == 2'd1)));
        if (s_ready) full_ready_room: assert (cnt != 2'd2);
        if (cnt != 2'd0) full_data: assert (m_data == f_out);
        if (cnt == 2'd2) full_second: assert ((rp ? e0 : e1) == f_out + W'(1));
        full_holds__ante: cover (cnt != 2'd0);
        full_ready__ante: cover (s_ready);
        full_two__ante: cover (cnt == 2'd2);
    end
`endif
endmodule

// Forward-only pipeline of NS stages under one shared enable: the stages advance together when the output is empty or
// being taken, and hold together otherwise. s_ready = m_ready || !m_valid, so it depends on m_ready in the same
// clock (a combinational path through the whole pipeline and a fanout of NS*(W+1) enables). Latency NS clocks, full
// throughput. Bubbles inside the pipeline are not squeezed out while the output is stalled.
module pipe_fwd #(
    parameter int W  = 32,
    parameter int NS = 1
) (
    input  logic         clk,
    input  logic         rst,
    input  logic         s_valid,
    output logic         s_ready,
    input  logic [W-1:0] s_data,
    output logic         m_valid,
    input  logic         m_ready,
    output logic [W-1:0] m_data
`ifdef FORMAL
    , output logic [W-1:0] f_in_o, f_out_o
`endif
);
    logic [NS-1:0]   v;
    logic [NS*W-1:0] d;
    wire en = m_ready || !v[NS-1];
    assign s_ready = en;
    assign m_valid = v[NS-1];
    assign m_data  = d[(NS-1)*W +: W];
    always_ff @(posedge clk) begin
        if (rst) v[0] <= 1'b0;
        else if (en) v[0] <= s_valid;
        if (en) d[0 +: W] <= s_data;
    end
    genvar i;
    generate
        for (i = 1; i < NS; i++) begin : g_stage
            always_ff @(posedge clk) begin
                if (rst) v[i] <= 1'b0;
                else if (en) v[i] <= v[i-1];
                if (en) d[i*W +: W] <= d[(i-1)*W +: W];
            end
        end
    endgenerate

`ifdef FORMAL
    // Properties for SymbiYosys (formal/pipe.sby), proved by k-induction together with the wrapper's. Ghost counters
    // (W bits, wrapping) count the beats accepted and delivered; the wrapper makes the source number its beats 0, 1, 2 ...
    // so a beat's data is its place in the stream, and every stored beat must hold the number its position implies.
    logic f_init = 1'b1;
    always_ff @(posedge clk) f_init <= rst;
    logic [W-1:0] f_in, f_out;
    assign f_in_o = f_in;
    assign f_out_o = f_out;
    wire f_push = s_valid && s_ready;
    wire f_pop  = m_valid && m_ready;
    always_ff @(posedge clk) begin
        if (rst) begin f_in <= '0; f_out <= '0; end
        else begin
            if (f_push) f_in <= f_in + W'(1);
            if (f_pop)  f_out <= f_out + W'(1);
        end
    end
    // stage k holds the beat that has f_ab[k] beats ahead of it in the pipeline (the valid stages above it)
    wire [NS*W-1:0] f_ab;
    wire [NS-1:0] f_stage_ok;
    assign f_ab[(NS-1)*W +: W] = '0;
    genvar gi;
    generate
        for (gi = 0; gi + 1 < NS; gi++) begin : g_ab
            assign f_ab[gi*W +: W] = f_ab[(gi+1)*W +: W] + W'(v[gi+1]);
        end
        for (gi = 0; gi < NS; gi++) begin : g_inv
            assign f_stage_ok[gi] = !v[gi] || (d[gi*W +: W] == f_out + f_ab[gi*W +: W]);
        end
    endgenerate
    // one assertion over every stage (a label inside a generate loop would be created once per stage and clash)
    always_ff @(posedge clk) if (!f_init && !rst) begin
        fwd_stage_data: assert (&f_stage_ok);
        fwd_count: assert (f_in - f_out == f_ab[0 +: W] + W'(v[0]));
        fwd_stage_data__ante: cover (|v);
        fwd_count__ante: cover (f_in != f_out);
    end
`endif
endmodule
