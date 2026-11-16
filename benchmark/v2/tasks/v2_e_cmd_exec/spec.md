# Command executor and register file

I want the part of a small command protocol that carries commands out, built for the Nexys A7-100T. Another block has
already checked each packet; this block is given the command's type and parameters and acts on a small bank of registers. I stage the parameters through the test shell on the USB-UART (115200 baud) and then say "go".

The bank has eight 32-bit registers, numbered 0 to 7:

| No. | Name | Access | Holds |
|---|---|---|---|
| 0 | ID | read only | the constant 0x55445031 |
| 1, 2, 3 | SCRATCH0, 1, 2 | read and write | whatever was written; 0 after reset |
| 4 | CMDS | read only | how many commands have been carried out successfully |
| 5 | ERRS | read only | how many commands failed, plus how many packets were refused upstream |
| 6 | PERIOD | read only | the telemetry period: 100 after reset |
| 7 | UPTIME | read only | the number of ticks since reset |

The command types are: 1 read, 2 write, 3 status, 4 telemetry start, 5 telemetry stop. Parameters: a 16-bit first parameter
(the register number for read and write, the period for telemetry start) and a 32-bit second parameter (the value to write).

- Read: puts the register's value where I can read it back. A read of CMDS or ERRS shows the count as it was before this
  command was counted.
- Write: stores the value in a read and write register. A write to a read-only register is refused.
- Status: succeeds and does nothing else. Telemetry stop: switches telemetry off. Telemetry start: if the first parameter is
  not zero, the period becomes that number raised to 4 if it is lower; zero keeps the period as it is. It then switches
  telemetry on.
- A register number of 8 or more is refused (read or write). A type that is not one of the five is refused.

Every command leaves a result code: 0 OK, 1 unknown type, 3 unknown register, 5 write to a read-only register. A command that
succeeds adds one to CMDS; one that fails adds one to ERRS and changes nothing else. A refused command's result code is
readable; the value I read back is zero unless the command was a successful read.

I can also tell the block about time and about trouble upstream: writing a number n (0 to 255) to the tick register adds n to
UPTIME, and writing anything to the refused register adds one to ERRS. I can read whether telemetry is on. The eight registers
can also be read straight out of the block, without a command.

LED[7:0] shows ERRS (low byte) and LED[15:8] shows CMDS (low byte). CPU_RESETN resets everything. The design ID is "CXR1".

Bench notes: the top module is `v2_e_cmd_exec_top`, its ports are named as in the board's master XDC, and the shell parameters `CLKS_PER_BIT`, `TIMEOUT_CYCLES` and `BUILD_STAMP` are provided.
