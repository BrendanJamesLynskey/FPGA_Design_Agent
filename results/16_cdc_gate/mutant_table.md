| fixture | what | report_cdc alone flags | structure flags | injected sim flags (seeds 1-3) | new gate flags |
|---|---|---|---|---|---|
| C1 | toggle, 2-flop ASYNC_REG vector | no | no | no | no |
| C2 | toggle, 3-flop ASYNC_REG vector | no | no | no | no |
| C3 | xpm_cdc_single | no | no | no | no |
| C4 | pulse to toggle, scalar ASYNC_REG flops | no | no | no | no |
| C5 | xpm_cdc_pulse | no | no | no | no |
| C6 | hand-built Gray bus + max-delay/bus-skew | no | no | no | no |
| C7 | xpm_cdc_gray | no | no | no | no |
| C8 | hand-built 4-phase handshake | no | no | no | no |
| C9 | xpm_cdc_handshake | no | no | no | no |
| C10 | hand-built Gray async FIFO | no | no | no | no |
| C11 | xpm_fifo_async | no | no | no | no |
| C12 | reset bridge (async assert, sync release) | no | no | no | no |
| M1 | two flops, no ASYNC_REG | no | yes (U2) | no | yes |
| M1B | no synchroniser (one flop) | yes | yes (U2) | no | yes |
| M2 | one bit into two flops, compared | yes | yes (U2) | no | yes |
| M3 | binary counter bit by bit | no | yes (U5) | yes | yes |
| M4 | two toggles XORed before the synchroniser | yes | yes (U3) | no | yes |
| M5 | pulse into a level synchroniser | no | no | yes | yes |
| M6A | Gray bus with no max-delay/bus-skew exception | no | yes (U5) | no | yes |
| M7 | two flags synchronised separately, then compared | no | yes (U6) | yes | yes |
| M8 | source reset clears a destination register | yes | yes (U1) | no | yes |
| M10 | raw reset released asynchronously into clk_b flops | yes | yes (U1) | no | yes |

Not ported: M6b and M6c (the same RTL as M6a with route-through LUT padding: hardware skew, nothing to see in RTL or at synthesis beyond M6a's missing exception), M9 and M11 and C13 (one-sided reset of a FIFO or handshake: they need the rig's asynchronous-reset release injection, which the cycle-level model does not have).
