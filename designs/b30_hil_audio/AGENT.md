# AGENT b30_hil_audio (fda-handover/1)
source: designs/b30_hil_audio/handover.yaml; human view: README.md; refresh: python -m flow.handover fresh designs/b30_hil_audio

## identity
kind=demonstration produced_by=human+agent part=xc7a100tcsg324-1 board=Nexys A7-100T top=b30_hil_audio_top tool=Vivado 2026.1

## summary
One design on the Nexys A7 that carries four library instruments (a tone generator, a frequency and duty counter, a logic analyser and a frame CRC) and an XADC readout behind the test shell, so that every sensing path of the brief 30 hardware-in-the-loop stage has something to read. The tone leaves the board as PWM audio, and `hil.yaml` lists eight checks that compare the board with Python golden models, including a measurement of the tone at the audio jack.
not: a product design; its job is to give the hardware-in-the-loop checks a known answer on every path; a test of the instruments' own correctness; the library blocks are tested in ip_lib and hil/tests; the video, analogue-input, M2K, Pluto, RTL-SDR and Red Pitaya paths, which no run covered

## state
stage=board-verified vivado=2026.1 kb_pin=1fc7ed8 build_id=efa287bc
gates: build_2026_1=pass hil_board=pass

## interface
clk CLK100MHZ 100MHz
rst CPU_RESETN active-low: the board's reset button, synchronised by the test shell's reset synchroniser (assert asynchronous, release synchronous); reset turns the tone on, clears the pixel-fault switch and sets the DDS step back to its 1 kHz value
if UART register window test shell, 8N1 UART at 115200 baud: 32-bit registers at shell addresses 0x80 plus the offset in the header of rtl/b30_hil_audio_top.sv (CTRL 0x00, STEP 0x01, WAVE 0x02, SAMPLE 0x03, frequency counter 0x10 to 0x13, logic analyser 0x20 to 0x28, XADC 0x40 to 0x43, frame CRC 0x50 to 0x55); read data is valid the clock after the read strobe; offsets with no register read 0 doc=shell/PROTOCOL.md
if Audio output AUD_PWM (PWM, 10-bit duty, offset binary) and AUD_SD (held high), LVCMOS33: the line is driven low for the low part of each PWM period and released for the high part, because the board's audio stage pulls it up; the board's low-pass filter and 3.5 mm jack follow doc=boards/nexys_a7_100t/inventory.yaml
if LEDs LED[0] is the tone-on bit and LED[1] is a slow heartbeat, LVCMOS33: indicators only; no check reads them
param CLKS_PER_BIT=868 legal=set by the shell's UART; the board value is 868
param FD_GATE_CLKS=50,000,000 legal=1 or more; the board value is 50,000,000
param STEP (reset value)=89,463,225 legal=a 32-bit DDS phase step, writable at offset 0x01

## files
designs/b30_hil_audio/rtl/b30_hil_audio_top.sv 308b6cba65: the top, with the register map in its header (tone, instruments, XADC, frame generator and the read mux)
designs/b30_hil_audio/design.xdc e9b9ecb91a: pins (AUD_PWM on A11), the 100 MHz clock and the false paths on the asynchronous inputs and slow outputs
designs/b30_hil_audio/build.yaml fe43c5592c: how flow/run_vivado.sh builds the design, with the library sources it pulls in
designs/b30_hil_audio/hil.yaml 91f21090d8: the eight hardware-in-the-loop checks, their stimulus, expected results and tolerances
designs/b30_hil_audio/tests/hil_audio_cocotb.py 194d16964a: cocotb test of every instrument's registers against the Python golden models
designs/b30_hil_audio/tests/test_hil_audio_rtl.py 074480dd34: pytest entry that runs the cocotb test with Icarus Verilog (8-clock UART bit, a 40,000-clock gate)

## commands
simulate every instrument against the golden models (~2min): python3 -m pytest -q designs/b30_hil_audio/tests/test_hil_audio_rtl.py
[heavy] build and run the gates (~4min): flow/run_vivado.sh designs/b30_hil_audio base
program the SRAM and run the hardware-in-the-loop checks (~1min): python3 flow/hil.py designs/b30_hil_audio

## records (path sha256-prefix; claims below cite R<n>)
R1 designs/b30_hil_audio/tests/test_hil_audio_rtl.py 074480dd34
R2 results/vivado_2026_1_remeasure/b30_hil_audio.json d96edd32f1
R3 results/b30/hil_runs/b30_hil_audio.hil.json f9a662c1e2

## evidence
E1 simulation pass R1 ci: every instrument's registers read through the shell in simulation and compared with the Python golden models
E2 build pass R2: whole-board build on Vivado 2026.1; every gate passes (built, not programmed)
E3 board pass x1 R3: one hardware-in-the-loop run; all eight checks pass (design ID, frame CRC known answer, seeded pixel fault seen, tone frequency in the FPGA, logic analyser against the DDS model, pre-trigger, XADC against JTAG sysmon, tone at the audio jack) | cond: wall power; power gate passed before programming; die temperature and rails read by the XADC and by JTAG sysmon agreed within tolerance (M11, M12); audio captured by a USB interface at gain about 50 percent, uncalibrated; ambient not recorded

## measured
M1 resources lut=1233 LUT R2#lut: LUTs, whole board design | routed whole-board build, Vivado 2026.1, xc7a100tcsg324-1, including the test shell
M2 resources ff=1158 FF R2#ff: flip-flops, whole board design | routed whole-board build, Vivado 2026.1, including the test shell
M3 resources bram36=0.5 tile R2#bram36: block RAM tiles (36 kb equivalents) | routed whole-board build, Vivado 2026.1; the DDS wave table uses one 18 kb block RAM
M4 timing wns_ns=2.436 ns R2#wns_ns: worst setup slack | routed, at the 100 MHz board clock
M5 timing whs_ns=0.048 ns R2#whs_ns: worst hold slack | ditto
M6 power power_w=0.128 W R2#power_w: total on-chip power estimate | report_power after routing, vectorless (default toggle rates), the board's thermal environment
M7 board -=93c30c48 R3#checks.frame_crc_known_answer.measured.crc: CRC-32 of the generated 128-pixel frame, read from the board | equals the golden model's CRC; the pass rule is exact equality with no new mismatches
M8 board -=1000 Hz R3#checks.tone_frequency_in_fpga.measured: tone frequency measured inside the FPGA | 0.5 s gate on the sample sign bit, resolution 2 Hz; pass range 1000 Hz plus or minus 4 Hz
M9 board -=-29.27 dBFS R3#checks.tone_at_the_jack.measured.level_dbfs_rms: tone level at the audio jack, relative to full scale of the capture interface | USB audio capture of the right channel; gain about 50 percent, not calibrated; pass threshold at least -75 dBFS
M10 board -=1.32 % R3#checks.tone_at_the_jack.measured.thd_percent: total harmonic distortion of the tone at the audio jack | same capture as M11, through the board's PWM filter and the interface; pass threshold at most 5 percent
M11 board -=25.716 C R3#checks.xadc_vs_jtag.measured.tj_c: die temperature read by the in-design XADC | fabric DRP readout; the JTAG sysmon read 25.6 C in the same run; pass tolerance 2 C and at most 85 C
M12 board -=1.0063 V R3#checks.xadc_vs_jtag.measured.vccint_v: VCCINT read by the in-design XADC | fabric DRP readout against JTAG sysmon, tolerance 0.02 V

## gaps
[latency] Not measured; no record times a window read or the tone path.
[throughput] Not applicable; the design is an instrument carrier, and the logic analyser captures one 256-sample buffer at the 48.008 kHz sample rate per arm.
[E3] The board run used a bitstream built on the earlier Vivado release; the 2026.1 build (E2) was not programmed. It was one run, so there is no spread.
[audio calibration] The audio level is relative to the capture interface's full scale at an uncalibrated gain, not a voltage at the jack; the THD includes the board's filter and the interface, which no run measured alone.
[paths not run] No run used the M2K, Pluto, RTL-SDR, Red Pitaya, HDMI capture, I2S audio or an XADC analogue input; their host drivers are tested only on synthetic data or a fake server (results/b30/README.md).
[agent loop] The hardware-in-the-loop stage (flow/hil.py) is not wired into the agent's repair loop or gates.
[behaviour] Writes to read-only offsets are ignored and offsets with no register read 0. Offsets 0x20 to 0x2F all go to the logic analyser, beyond the nine registers its header lists. After reset the frame CRC expected value (0x54) is 0, so every frame counts as a mismatch until the host writes the model's CRC. CTRL bit 1 flips one pixel bit of every frame until cleared.
[instrument limits] The frequency counter gates 0.5 s, so a tone change takes up to a gate to show; the logic analyser samples at the tone tick, not at 100 MHz.

## next_actions
1. Re-run flow/hil.py on a Vivado 2026.1 bitstream, with the XADC and JTAG sysmon read at the start and end, and repeat it several times for a spread.
2. Calibrate the audio path once (interface alone, then the board) so the level and THD can be quoted in volts and in the board's own contribution.
3. Run the paths that were not connected (M2K, Pluto, RTL-SDR, Red Pitaya, HDMI capture) when the hardware is attached, as results/b30/README.md lists.

## open_questions
- Should the hardware-in-the-loop stage be wired into the agent's gates, and what should it do when the audio interface is absent (skip and report, as now)?

## history
2026-11-11 30 pr=-: written with the HIL instruments and stage; one board run, all eight checks pass; its seeded-fault twin fails the audio check
2026-11-11 49 pr=-: rebuilt on Vivado 2026.1; every gate passes (not programmed)
2026-11-13 68 pr=-: handover written to the documentation standard
