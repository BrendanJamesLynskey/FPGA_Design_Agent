# t2_i2c_cmd_master: reviewer notes

- **Twin:** the textbook's ADT7420 reader (a fixed I2C sequence, STOP after the pointer write).
- **Trap:** `test_id_via_repeated_start`: the ADT7420 model (benchmark/lib/i2c_devices.py) loses its pointer when
  a pointer write is closed by a STOP (Nexys A7 RM 12.1); a START on an owned bus must be a repeated START. The
  trap variant inserts a STOP before every START on an owned bus and reads register 0x00 instead of 0xCB.
- **Left out of spec.md on purpose:** register offsets and bit fields (CMD op codes, NACK bit, OWNED), the exact
  waveforms in quarters, what happens to commands while busy / on a free bus (ignored), SDA level after READ's ACK
  bit, INFO register.
- **Review:** the bench checks SCL high times 2Q..2Q+4 (synchroniser latency) and low times 2Q..2Q+2, and that no
  line is ever driven high (an X on the wired-AND bus is an error). Repeated-START setup/hold quarters are not timed
  individually, only the transaction log (no START or STOP inside a byte).
- Shared helper: `benchmark/lib/i2c_devices.py` (bus engine + ADT7420 + plain ACKing devices), also used by
  t2_i2c_scanner and t2_adt7420_alarm.
- **v1.2 (2026-11-04):** SCL high time is accepted from 2Q to 2Q + 8 clocks (v1: + 4). The spec says wait until SCL is
  seen high through a two-flop synchroniser, then 2Q: 2-3 clocks of synchroniser plus 1-3 of state and registered-output
  latency. A missed stretch wait still fails (it shortens or lengthens the phase by far more than 8).
