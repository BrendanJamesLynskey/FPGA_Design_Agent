# Demo intake: what to send before a demo is considered

Plain text, one page. The owner may send this to someone who asks for a demo of FPGA Force. Nothing is built or run until
the owner has read the answers and decided it is worth doing. A demo is a recording and a set of result files, not a copy of the agent or access to it.

Please answer in plain text, a line or two each. "Don't know" is a fine answer.

1. **Your board and part.** Board name and revision (the catalogue in `docs/board_catalogue.md` lists the boards the agent already has a file for; if yours
   is not there, give the exact FPGA part, package and speed grade, for example `xc7a35tcpg236-1`, and say where its pin list comes from).
2. **Your tool version and licence.** The Vivado version you use (the agent works with 2026.1), and whether your part needs a paid licence. A part outside the free
   licence tier can be documented but not built here.
3. **What you want built.** The function in a paragraph: inputs, outputs, clock rate, throughput or latency target, and any standard it must follow.
   One example input and the output you expect for it is worth more than a page of description.
4. **Interfaces and pins.** Which connectors, LEDs, buttons, UART, memory, Ethernet, video or other interfaces the design uses, with the I/O voltage of each.
   If your design needs a constraints file, send it only if you may share it.
5. **What you may share.** Which files you are allowed to give (sources, IP, constraints, test vectors), their licences, and anything that must not leave your
   hands. Please do not send vendor files whose licence forbids redistribution, or anything under a non-disclosure agreement.
6. **Safety of your board.** Supply voltage and current, jumper settings that matter (for example a bank voltage), and anything on the board that a bitstream could damage.
   The owner will only load a bitstream into volatile configuration memory, never flash or fuses, and only on a board the owner has.
7. **What comes back.** By default: a screen or phone recording of the run, the build and timing reports, the resource and power figures with the conditions they were
   measured in, and what did not work. Tell us if you want something else.
8. **Permission to archive.** May the owner keep the results (recording, reports, your specification) in a private archive of agent runs? Choose one:
   (a) no, delete everything after the run; (b) yes, privately, not published; (c) yes, and a summary may be published without your name.
   If you say yes, may your name be recorded? (yes / no)
9. **Timing.** When you need it, and whether the demo has to be live.
10. **Contact.** How the owner can reach you (a reply to this message is enough).

What the owner will tell you before running anything: whether the request is worth running, which board it would run on, what the agent can and cannot do for your
part (the trust label and known gaps in the catalogue), and what will be kept.
