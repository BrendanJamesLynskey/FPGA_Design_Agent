# t2_i2c_scanner: reviewer notes

- **Twin:** none (no textbook or Digilent demo scans the bus).
- **Trap:** none.
- **Left out of spec.md on purpose:** register offsets, MAP word/bit layout, LOWEST's "none" code (0xFF), the
  probe waveform in quarters, that results update during the scan, what a start while busy does (ignored), LED
  width/encoding.
- **Review:** the bench puts devices at reserved addresses 0x03 and 0x7A and checks they are never probed, checks the
  exact probe order and log (START, address+W, STOP per address), and that the ADT7420 never receives a data byte.
- Hardware oracle: the ADT7420 at 0x4B must be found (selfcheck); other on-board I2C devices are not expected on
  this bus (the RM lists only the ADT7420 on TMP_SCL/TMP_SDA).
- Shared helper: `benchmark/lib/i2c_devices.py`.
