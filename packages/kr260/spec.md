# KR260 package: the PL Ethernet and SFP+ paths of the trigger designs

The user's words (owner, brief 162 and 174, 2026-11-22): the designs b58a_trigger (two RGMII ports) and b96_kr260_10g (one SFP+ lane)
run on the Kria KR260 Robotics Starter Kit (K26 SOM, `xck26-sfvc784-2LV-c`). The board is built and cannot change: the series
resistors, the PHYs and the oscillators are what AMD's carrier card has. Everything the flow needs to know about the board comes
from AMD's published files in `board/` (schematic PDF, BOM, Allegro board file); where the files and our `boards/kr260/board.yaml`
disagree, the files win and the disagreement is reported.
