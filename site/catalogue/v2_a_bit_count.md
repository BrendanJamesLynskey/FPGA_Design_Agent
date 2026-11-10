# Bit counter (v2_a_bit_count)

Domain A, drill tier, Nexys A7-100T. Survey row: A24 (leading-zero count, popcount, bit reverse). Draft for the problem catalogue; the task files are in
`benchmark/v2/tasks/v2_a_bit_count/`.

## The problem, and where it is used

Take a 32-bit word and report how many bits are 1, how many zeros come before the first 1 counting down from bit 31, and the word with its bit order reversed. The corner is the zero word: it has no 1 at all.

Where it appears: Floating-point normalisation, priority and arbitration logic, hash and error-correcting codes (parity and weight), FFT address generation (bit reversal), and the count-leading-zeros and population-count instructions of most processors.

## Hero diagram

A 32-cell ribbon of bits. A popcount tree (adders in a pyramid) sits above it summing the ones; a scan arrow runs in from bit 31 and stops at the first 1 to show the leading zeros; a mirror line down the middle swaps cell i with cell 31-i for the reversal.

## Animation plan (driven by `hidden/model.py`)

Call pop, lzc and rev from the model for each word. Animate the pyramid adding pairs of bits level by level, the scan arrow walking down from bit 31, and the mirror swap. Single-bit words 1 << n, then the all-ones and all-zero words, play in turn.

## Interface

Shell registers: WORD (32-bit write), POP, LZC and REV (read-only). LED[5:0] shows the count of 1 bits.

## Acceptance criteria in plain words

POP counts 0 to 32 (six bits) including the all-ones word. LZC counts down from bit 31 and is 32 for a zero word. REV reverses the bits. The LEDs show POP. Register map and reset values as listed.
