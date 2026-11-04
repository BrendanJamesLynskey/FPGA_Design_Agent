# t2_qspi_sfdp: reviewer notes

- **Twin:** none (our own b2_qspi_jedec self-check reads only the ID). Trap: none.
- **Left out of spec.md on purpose:** register map and byte order of the SFDP words (little-endian, signature reads
  0x50444653), the 3 address bytes and the number of dummy cycles (8), the start-up SCK cycles with CS high
  (STARTUPE2 drops the first 3 USRCCLKO edges), CS setup/hold/gap times, behaviour while busy.
- **Review:** the flash model (hidden/flash_model.py) fails the test on any opcode other than 9Fh and 5Ah (the
  forbidden list of designs/b2_qspi_jedec/tests/test_qspi_rtl.py is a subset). The wrapper is `tb_cclk_bench` with
  `logic cclk;` for the STARTUPE2 stub.
- **Hardware caveat:** the inventory lists SFDP as an S25FL127S feature; the owner's board answered RDID with model
  bytes "00" (an S25FL128S). Whether that part answers 5Ah with a JESD216 header is not established, so selfcheck
  requires the ID and repeatability, and only records SIG_OK. A planner should confirm on the board before relying
  on REQ-05 beyond the ID.
- **v1.2 (2026-11-04):** the tests compare the opcode and address bytes (RDID 9Fh; RSFDP 5Ah 00 00 00) and the byte
  count (4 and 21) only. DQ0 during the dummy and read bytes is a don't-care: spec.md never fixed it, the flash ignores it
  there, and a single shift register that echoes MISO onto MOSI is a correct design. Chosen over adding "DQ0 = 0" to the
  spec because nothing about the flash needs it. The dummy clocks are still checked, through the byte count.
