# F0B manual checks (owner, 2026-10-30)

The three checks a person makes that the script cannot (brief 02, item 7). The answers are the owner's, relayed by
the planner; nothing here was measured by a script.

| # | Check | Answer |
|---|---|---|
| a | Photo of the board running T1 | Taken after `f0b_dimming_demo.sh`. It shows the display reading `40` on the left and `0000` on the right, the DONE LED (green) and POWER LED (red) on, the 16 LEDs off, and the micro-USB cable in J6 (PROG/UART). JP3 is visibly on USB. JP1 is on QSPI by the owner's statement (the photo does not show for certain which pair the jumper covers). Committed resized (900 x 1200), metadata stripped: [docs/img/t1_on_nexys_a7.jpg](../../docs/img/t1_on_nexys_a7.jpg) |
| b | Buttons, BRINGUP.md steps 4-6 | Yes, all matched: BTNU x3 gave `0003`; BTND x4 gave `FFFF` with all 16 LEDs dim; BTNC gave `0000` |
| c | LED dimming at three levels set over the UART (`f0b_dimming_demo.sh`: COUNT 0x8421, DUTY 0x08, 0x40, 0xA0, 6 s each, twice) | The script printed `design_id T1DC`, shell `1.0`, `build_stamp dfd4624e` and both rounds. The owner confirms three visibly different brightness levels, one after another. The owner did not explicitly confirm the `08`/`40`/`A0` digits; the photo shows `40` on the left after the script's final write of DUTY 0x40 |

What changed in BRINGUP.md because of these: JP1 is no longer "on JTAG" (it only chooses what loads at power-up, and
JTAG programming to SRAM worked with it on QSPI); J6 and JP3 are marked as checked on the photo.
