# Requirements needed before this design can proceed

Requirements readiness stopped: no answer was available for the open questions. Nothing was built.

Answer each question in `requirements_answers.yaml` (`Q1: <your answer>`, or `Q1: {answer: ..., who: ...}`), then run again; or answer through the interview.

| Id | Topic | Question | Where it came from |
|---|---|---|---|
| Q1 | Names, files and the build target | The core has no vendor primitive, so BUILD (0x004) must enter it through a port. What is that port called and how wide is it (for example a 32-bit input carrying the USR_ACCESS word)? Does the core also drive the led[1:0] outputs, or does the top? | reviewer (RDY-REV-01) |
| Q2 | requirement | What is MEM_ADDR after the ROM_DATA read, i.e. the value used for the following RAM_DATA read? (Scenario: AUTOINC set, MEM_ADDR = 1023, one ROM_DATA read is performed, then a RAM_DATA read is performed immediately after.) Two careful readers of the requirements disagree about this; what is the intended behaviour? | readers (RDY-READ-01) |
| Q3 | requirement | What value is returned by the RAM_DATA read? (Scenario: Host writes RAM word 7 = 0x12345678, then rst is pulsed for 3 clocks, then MEM_ADDR is set to 7 and RAM_DATA read with BUSY=0.) Two careful readers of the requirements disagree about this; what is the intended behaviour? | readers (RDY-READ-01) |
| Q4 | requirement | What value is read back? (Scenario: Host writes 0xFFFFFC05 to MEM_ADDR, then reads MEM_ADDR back.) Two careful readers of the requirements disagree about this; what is the intended behaviour? | readers (RDY-READ-01) |
| Q5 | requirement | What value does h_rdata present for that read, in the first allowed read response? (Scenario: SCRATCH holds 0x11111111. Host asserts h_we writing 0x22222222 to 0x008 on clock N and h_re reading 0x008 on clock N+1 (the clock just after the write).) Two careful readers of the requirements disagree about this; what is the intended behaviour? | readers (RDY-READ-01) |
| Q6 | requirement | Which RAM word receives the write and what is MEM_ADDR afterward (give MEM_ADDR)? (Scenario: AUTOINC set, MEM_ADDR=1023, host writes RAM_DATA=0xDEADBEEF, BUSY=0.) Two careful readers of the requirements disagree about this; what is the intended behaviour? | readers (RDY-READ-01) |
| Q7 | requirement | What is the value of MARCH_STATUS bits 31:16 (passes completed) after reset? (Scenario: A 200-pass march run is mid-test (BUSY=1, passes completed 57) when rst is asserted for 3 clocks and released. After release the host reads MARCH_STATUS and MARCH_ERRS.) The requirements do not say; what should happen? | readers (RDY-READ-02) |
| Q8 | requirement | Does MEM_ADDR advance by 1 as a result of the ignored write while BUSY is 1? (Scenario: BUSY=1 during a march run; host writes RAM_DATA=0xAAAA5555 at MEM_ADDR 3 with AUTOINC set, then reads RAM_DATA.) The requirements do not say; what should happen? | readers (RDY-READ-02) |
