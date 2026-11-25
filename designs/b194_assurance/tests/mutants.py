"""RTL mutants of the development design (brief 194): functional bugs a verification profile should catch. Each is one textual change.
Used by flow/assurance_profiles.py to measure which method catches which bug, and how long the method takes."""

MUTANTS = [
    # (id, file, old, new, what)
    ("m1_last_word", "a194_ctrl.sv", "assign run  = (state_q == RUN) && (rem_v != 16'd0);", "assign run  = (state_q == RUN) && (rem_v > 16'd1);",
     "the sequencer stops accepting one word early: the last word of every burst is never taken"),
    ("m2_checksum_clear", "a194_core.sv", "if (rst || start) checksum <= '0;", "if (rst) checksum <= '0;",
     "the checksum is not cleared by start: the second burst adds to the first"),
    ("m3_early_done", "a194_ctrl.sv", "DRAIN: if (drained) state_d = DONE;", "DRAIN: state_d = DONE;",
     "done is signalled without waiting for the FIFO and the output stage to drain"),
    ("m4_count_low_byte", "a194_ctrl.sv", "assign rem_d = load_rem ? len : dec_rem ? rem_v - 16'd1 : rem_v;",
     "assign rem_d = load_rem ? len : dec_rem ? {rem_v[15:8], rem_v[7:0] - 8'd1} : rem_v;",
     "the remaining count is decremented in its low byte only: wrong across a multiple of 256 (bursts above 256 words)"),
    ("m5_len_zero", "a194_ctrl.sv", "if (len == 16'd0) state_d = DONE;\n                else              state_d = RUN;", "state_d = RUN;",
     "a burst of length 0 is not special-cased: the sequencer waits for words that never come"),
    ("m6_double_pop", "a194_core.sv", "assign pop     = !empty && !rd_vld && (!bus_v || m_axis_tready);", "assign pop     = !empty && (!bus_v || m_axis_tready);",
     "the FIFO is read again while a read is in flight: a word is overwritten in the output register under back-pressure"),
    ("m7_wrap_pointer", "a194_fifo.sv", "if (do_wr) wptr <= wptr + 1'b1;", "if (do_wr) wptr <= (wptr[8:0] == 9'd500) ? {wptr[9], 9'd0} + 10'd0 : wptr + 1'b1;",
     "the write pointer wraps at 500 instead of 512: wrong only when the FIFO holds more than 500 words"),
]
