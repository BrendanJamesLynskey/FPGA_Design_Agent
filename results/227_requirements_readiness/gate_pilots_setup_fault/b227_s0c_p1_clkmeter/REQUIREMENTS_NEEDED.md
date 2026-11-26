# Requirements needed before this design can proceed

Requirements readiness stopped: no answer was available for the open questions. Nothing was built.

Answer each question in `requirements_answers.yaml` (`Q1: <your answer>`, or `Q1: {answer: ..., who: ...}`), then run again; or answer through the interview.

| Id | Topic | Question | Where it came from |
|---|---|---|---|
| Q1 | Names, files and the build target | The core has no vendor primitive, so the BUILD word must reach it through a port, but the core port list does not include one. What is that port called and how wide is it (presumably 32 bits)? The bench drives the core, so it must know which port to drive. | reviewer (RDY-REV-01) |
| Q2 | requirement | What is GATE_ACTUAL after this measurement completes? (Scenario: The host writes START in the same clock cycle that it writes GATE_LEN = 5000 while not BUSY (GATE_LEN currently 2000). Both are issued in the same cycle on the bus.) Two careful readers of the requirements disagree about this; what is the intended behaviour? | readers (RDY-READ-01) |
| Q3 | requirement | Is that START accepted, starting a new measurement? (Scenario: A START is issued exactly in the clock cycle in which DONE sets and BUSY clears at the end of the gate.) Two careful readers of the requirements disagree about this; what is the intended behaviour? | readers (RDY-READ-01) |
| Q4 | requirement | In cycle 3, what does h_rdata show: ID, BUILD, or something else? (Scenario: The host issues h_re for address 0x000 in cycle 0 and h_re for 0x004 in cycle 1 (back-to-back reads).) Two careful readers of the requirements disagree about this; what is the intended behaviour? | readers (RDY-READ-01) |
| Q5 | requirement | What value is read back? (Scenario: The host writes 0x12345678 to the ID register at 0x000 and reads it back.) Two careful readers of the requirements disagree about this; what is the intended behaviour? | readers (RDY-READ-01) |
| Q6 | requirement | After reset releases, what is MEAS_DONE? (Scenario: A 1 s gate is half done with BUSY=1, DONE=0, MEAS_DONE=3 when rst asserts for 16 clk_ref cycles.) Two careful readers of the requirements disagree about this; what is the intended behaviour? | readers (RDY-READ-01) |
| Q7 | requirement | What is led[0] on the next cycles after the write takes effect, and when LED_EN returns to 1, does the toggle counter restart from zero? (Scenario: LED_EN is 1 and LED 0 is currently 1; the host then writes LED_EN = 0.) The requirements do not say; what should happen? | readers (RDY-READ-02) |
