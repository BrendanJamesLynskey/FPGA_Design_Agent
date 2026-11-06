# Compressed-database search behind the test shell

I want a block for the Nexys A7-100T's FPGA that finds the database entries closest to a query when the database is stored in a compressed form, and I want to exercise it entirely from the test shell.

- Each database entry is stored as eight small codes of 4 bits each (so a 32-bit word per entry, code j in bits 4j to 4j+3). There are up to 1000 entries, numbered 0 upwards in the order they arrive.
- For each query I give the block a table of distances: 8 groups of 16 numbers, each a whole number below 2^20 (the table entry for group g and code c is the distance contribution of code c in group g).
  I write the table in over the shell: I set a table position (group and code) and then write the values one after another, each write storing the value and moving on to the next position (the next code, and after code 15 the next group).
- The distance of a database entry to the query is the sum over its eight codes of the table entry that code picks in its group. Smaller is closer.
- A "start" command, before the entries of a new query, forgets the previous result and restarts the entry numbering at 0. Then I park up to 16 entries over the shell and give a "burst" command with a count, which presents them on
  consecutive clocks, one per clock; several bursts follow each other, and the burst that carries the final entry is marked "last". The table is fully written before the first entry of a query and does not change during it.
- When the last entry has been taken into account the block raises a "done" flag (it stays up until the next start) and I read the eight closest entries closest first: for each place a "filled" flag,
  the distance (up to 23 bits) and the entry number. If two entries have the same distance the one with the smaller number comes first. The result must be right at the moment done is high.
- CPU_RESETN clears done and forgets the result. I will run several queries and check every place of the result exactly. LED0 shows done and LED1 shows that a burst is running.
  The shell runs at 115200 baud on the USB-UART. The design ID is "PQSR".

Test hooks: top module `c15_pq_search_top`, ports named as in the board's master XDC, and the test shell's
`CLKS_PER_BIT`, `TIMEOUT_CYCLES` and `BUILD_STAMP` parameters as top-level parameters. There are no other time
constants.
