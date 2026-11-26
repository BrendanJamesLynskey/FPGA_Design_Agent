# P2 hidden full spec (oracle only): answers the user would give about the ROM, RAM and memory test
Written for brief 227 as the user's answers; it adds facts the request leaves open and carries no test values.
- Reset: MEM_ADDR 0, MEM_CTRL 0 (AUTOINC off), MARCH_CTRL 0, MARCH_PASSES 1, MARCH_STATUS 0, MARCH_ERRS 0, MARCH_FIRST_ERR 0xFFFFFFFF. The RAM contents are not reset by the bus reset; they hold 0xC0DE0000 + i from configuration.
- MEM_ADDR is 10 bits; the upper bits of a write are ignored and read as 0. With AUTOINC, MEM_ADDR wraps from 1023 to 0.
- ROM_DATA read returns the word at MEM_ADDR in the same two-clock read latency as any register; writes to ROM_DATA are ignored. A read of ROM_DATA with AUTOINC increments MEM_ADDR after the data is captured; a read without AUTOINC does not change MEM_ADDR.
- A RAM_DATA write with AUTOINC stores at the old MEM_ADDR and then increments; a RAM_DATA read does the same for reads.
- MARCH_PASSES of 0 is treated as 1; the register keeps the value written (the pass count used is max(1, value)). Values above 65,535 cannot be written (16 bits).
- START while BUSY is ignored. START clears MARCH_ERRS, MARCH_FIRST_ERR (to 0xFFFFFFFF), passes completed and DONE. BUSY is high for the whole test, DONE rises when the last pass has finished and BUSY falls in the same clock.
- A host access to RAM_DATA while the march test is BUSY is ignored (writes) or returns 0 (reads); the test owns the RAM then. MEM_ADDR can still be written.
- INJECT_FAULT makes the test see one wrong word per pass at address 5; that error counts in MARCH_ERRS and, on the first pass, sets MARCH_FIRST_ERR to 5. The fault is injected only in the checker's compare, never in the stored data, so the RAM ends all zero as March C- leaves it.
- March C- is: up(w0); up(r0,w1); up(r1,w0); down(r0,w1); down(r1,w0); down(r0), with the all-zero background and then the all-one background as the data.  One pass is both backgrounds.
- The memory clock is the register bus clock. Block RAM read latency is 1 clock; the bus read data is registered so that h_rdata is valid 2 clocks after h_re.
