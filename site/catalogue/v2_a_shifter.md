# Shifter and rotator (v2_a_shifter)

Domain A, drill tier, Nexys A7-100T. Survey row: A03 (shift registers, barrel shifter, rotate). Draft for the problem catalogue; the task files are in
`benchmark/v2/tasks/v2_a_shifter/`.

## The problem, and where it is used

A 32-bit shifter driven from the test shell: shift left, shift right logical, shift right keeping the sign, and rotate left, by an amount of 0 to 63. The difficulty is what happens for amounts of 32 and over, and what an arithmetic right shift does to a negative number.

Where it appears: Every processor ALU, floating-point alignment and normalisation, CRC and hash datapaths, and bit-field extraction in packet parsers. A barrel shifter is the usual log-depth multiplexer structure behind it.

## Hero diagram

A 32-bit word drawn as a ribbon of cells with the sign bit marked. A knob picks the operation and a slider the amount; the ribbon slides, with the vacated cells filled in zero, copies of the sign, or the bits that fell off the other end, according to the mode. A five-stage barrel diagram (shift by 1, 2, 4, 8, 16) sits underneath with the active stages highlighted.

## Animation plan (driven by `hidden/model.py`)

Call shift(a, amt, mode) from the model for each setting and animate the move from the operand to the result: bits slide across the barrel stages, fill bits are coloured by origin (zero, sign, wrapped). Sweeping the amount from 0 to 63 shows the behaviour change at 32.

## Interface

Shell registers: A (32-bit operand), CTRL (amount in bits 5:0, operation in bits 9:8) and RES (read-only 32-bit result). LED[15:0] shows the low half of the result.

## Acceptance criteria in plain words

All four operations give the model's result for every amount from 0 to 63. The arithmetic shift keeps the sign for negative operands. The LEDs show the low 16 bits of the result. Register map and reset values as listed.
