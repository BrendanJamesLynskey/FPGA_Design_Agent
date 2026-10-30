# Nexys A7-100T board files

| File | What | Source and licence |
|---|---|---|
| `Nexys-A7-100T-Master.xdc` | Digilent's master constraints file, unmodified | [Digilent/digilent-xdc](https://github.com/Digilent/digilent-xdc) at commit `c8644a9fe31cc803789643124545d56b3bef4600`, MIT |
| `LICENSE-digilent-xdc.txt` | Digilent's licence for the file above | same commit |
| `board.yaml` | part, clock, reset, UART pins, I/O standards, JTAG notes, in machine-readable form | this repo (MIT) |

Designs copy only the pins they use from the master XDC into their own `design.xdc`. Note that `SW[8]` and `SW[9]`
are in bank 34, which is powered at 1.8 V, so they are `LVCMOS18`; every other user I/O used here is `LVCMOS33`.
