# t1_sync_fifo_regs: reviewer notes

- **Twin:** the FIFO Generator in its standard (non-FWFT) read mode, as used in the textbook temperature-sensor
  project (Bruno project 7): data appears on dout one read after rd_en.
- **Trap:** `test_fwft_head_and_pop`. The trap variant registers the popped byte into a dout register and returns
  that (each read shows the previous byte); HEAD right after the first push must already be that byte.
- **Left out of spec.md on purpose:** first-word-fall-through (spec.md only says "returns the byte at the head");
  the register map; what a HEAD read of an empty FIFO does (returns 0, no error); W1C as the clear mechanism; the
  almost-full comparison (>=) and its reset threshold (12) and range; that a dropped push leaves the FIFO untouched.
- **Review:** no time constants (the bench only shrinks the shell's baud). The model treats POP as a read with a side
  effect; check_regs never reads POP. Stored bytes are not cleared by reset (spec.yaml says so); an empty POP of an
  RTL that returns a stale (possibly X) byte fails.
