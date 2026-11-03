# t2_adt7420_alarm: reviewer notes

- **Twin:** the textbook's ADT7420 temperature display (13-bit power-on mode, a fixed read sequence).
- **Trap:** `test_full_16bit_resolution`: the device model (benchmark/lib/i2c_devices.Adt7420) returns the 13-bit
  format (low 3 bits = T_LOW/T_HIGH/T_CRIT flags) unless CONFIG bit 7 is set; the test uses temperatures with odd
  low bits (0x0D87, -0x0123). The trap variant writes CONFIG = 0x10 (comparator mode but 13-bit) and fails.
- **Left out of spec.md on purpose:** the register map, CONFIG value 0x90 (16-bit, comparator, active low), the order
  of the configure writes, the limits' reset values, MAX/MIN seeding by the first reading, NACK handling (STOP,
  sticky flag, reading discarded), the poll waveform (repeated START is required: the model loses its pointer on
  STOP), that a re-configure restarts the statistics, the TMP_INT pull-up.
- **Review:** the bench keeps the temperature fixed while each reading is on the bus and checks every reading's bus
  transaction. Registers are read straight after a reading ends (PERIOD_CYCLES = 8000 in the bench); STATUS.BUSY is
  masked in those reads. The ALARM test drives INT through the model's comparator logic with T_HYST = 5 C.
- Hardware: selfcheck sets T_HIGH below the room temperature to see the real INT fire.
