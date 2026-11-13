# AGENT b30_hil_audio_pinfault (fda-handover/1)
source: designs/b30_hil_audio_pinfault/handover.yaml; human view: README.md; refresh: python -m flow.handover fresh designs/b30_hil_audio_pinfault

## identity
kind=demonstration produced_by=human+agent part=xc7a100tcsg324-1 board=Nexys A7-100T top=b30_hil_audio_top tool=Vivado 2026.1

## summary
The seeded-fault twin of b30_hil_audio. It builds from the same RTL, but its constraint file puts the audio output AUD_PWM on the pin of LED 0, so the tone never reaches the audio jack. It passes simulation and every check made inside the FPGA, and only the measurement at the jack fails, which is the point of the demonstration. The hardware-in-the-loop run of this design therefore reports a failure by intent.
not: a working design; the audio output is deliberately miswired and the design is not meant to pass the check at the jack; a general fault library; it seeds one fault, a wrong pin, to show the class of defect that simulation and in-FPGA self-checks cannot see

## state
stage=built vivado=2026.1 kb_pin=1fc7ed8 build_id=d2f00de4
gates: build_2026_1=not-run hil_fault_caught=pass

## interface
clk CLK100MHZ 100MHz
rst CPU_RESETN active-low: the board's reset button, synchronised by the test shell's reset synchroniser; reset behaviour is as in b30_hil_audio
if UART register window test shell, 8N1 UART at 115200 baud: the same register map as b30_hil_audio (header of designs/b30_hil_audio/rtl/b30_hil_audio_top.sv) doc=shell/PROTOCOL.md
if Audio output (miswired) AUD_PWM on pin H17, the pin b30_hil_audio uses for LED 0; AUD_SD stays on its audio-amplifier pin: the PWM tone is generated as in b30_hil_audio but leaves on the wrong pin, so the audio stage gets no tone; LED[0] is moved to pin J13 so the two ports do not share a pin doc=boards/nexys_a7_100t/inventory.yaml
param CLKS_PER_BIT=868 legal=set by the shell's UART; the board value is 868
param FD_GATE_CLKS=50,000,000 legal=1 or more; the board value is 50,000,000

## files
designs/b30_hil_audio/rtl/b30_hil_audio_top.sv 308b6cba65: the top, shared with b30_hil_audio (this design has no RTL of its own)
designs/b30_hil_audio_pinfault/design.xdc ae07766b50: the constraint file with the seeded fault (AUD_PWM on H17, LED[0] on J13); its first line says so
designs/b30_hil_audio_pinfault/build.yaml 3268f3bc4a: how flow/run_vivado.sh builds the design; sources are those of b30_hil_audio with this constraint file
designs/b30_hil_audio_pinfault/hil.yaml 1fee6a6ba8: the same eight checks as b30_hil_audio; the tone_at_the_jack check must fail here
designs/b30_hil_audio_pinfault/lint/xadc_stub.sv 9379bc0d79: lint-only stand-in for the XADC primitive

## commands
simulate the shared RTL (the simulation cannot see the constraint file) (~2min): python3 -m pytest -q designs/b30_hil_audio/tests/test_hil_audio_rtl.py
[heavy] build and run the gates (~4min): flow/run_vivado.sh designs/b30_hil_audio_pinfault base
program the SRAM and run the hardware-in-the-loop checks (expected overall result fail, from the audio check) (~1min): python3 flow/hil.py designs/b30_hil_audio_pinfault

## records (path sha256-prefix; claims below cite R<n>)
R1 designs/b30_hil_audio/tests/test_hil_audio_rtl.py 074480dd34
R2 results/b30/builds.json 9d6f7e51be
R3 results/b30/hil_runs/b30_hil_audio_pinfault.hil.json 6434637459

## evidence
E1 simulation pass R1 ci: the shared RTL passes its simulation against the golden models; the seeded fault is in the constraint file, which simulation does not read
E2 build not-run R2: not rebuilt on Vivado 2026.1; the build on the earlier release passed its gates (the record is that release's; its numbers are not quoted)
E3 board pass x1 R3: one hardware-in-the-loop run; the seeded fault is caught, since the audio check fails on level, distortion and SINAD while the other seven checks pass; the run's overall result is fail by design | cond: wall power; power gate passed before programming; die temperature and rails read by the XADC and by JTAG sysmon agreed within tolerance; audio captured by a USB interface at gain about 50 percent, uncalibrated; ambient not recorded

## measured
M1 board -=-90.5 dBFS R3#checks.tone_at_the_jack.measured.level_dbfs_rms: tone level at the audio jack, relative to full scale of the capture interface | USB audio capture of the right channel; gain about 50 percent, not calibrated; pass threshold at least -75 dBFS, so this fails
M2 board -=72.36 % R3#checks.tone_at_the_jack.measured.thd_percent: total harmonic distortion measured at the audio jack | same capture as M1; with no tone this is distortion of the noise; pass threshold at most 5 percent, so this fails
M3 board -=-2.89 dB R3#checks.tone_at_the_jack.measured.sinad_db: signal to noise and distortion ratio at the audio jack | same capture as M1; pass threshold at least 15 dB, so this fails
M4 board -=1000 Hz R3#checks.tone_frequency_in_fpga.measured: tone frequency measured inside the FPGA | 0.5 s gate on the sample sign bit; passes although the tone never reaches the jack, which is why the in-FPGA check cannot see this fault

## gaps
[resources] Not measured on Vivado 2026.1; only the earlier release built this design, and brief 49 withdrew those numbers. The RTL is the same as b30_hil_audio, whose 2026.1 numbers are in that design's handover, but the placed design was not measured.
[timing] Not measured on Vivado 2026.1 (see resources). The pin constraint differs from b30_hil_audio, so its slack is not assumed equal.
[power] Not measured on Vivado 2026.1 (see resources).
[latency] Not measured; no record times a window read or the tone path.
[throughput] Not applicable; the design is an instrument carrier with a deliberate fault.
[E2] The earlier-release build passed its gates, but the design was not rebuilt on 2026.1.
[build_2026_1] The 2026.1 build gate was never run for this design; re-run flow/run_vivado.sh designs/b30_hil_audio_pinfault base.
[E3] The board run used a bitstream built on the earlier Vivado release and was one run, so there is no spread. The run's overall result is fail by intent; the evidence shows the fault is caught, not that the design works.
[audio calibration] The audio level is relative to the capture interface's full scale at an uncalibrated gain; the noise floor of the interface alone was not recorded, and the pass thresholds were not tuned on a no-tone capture.
[fault coverage] One fault in one class (a wrong pin) was seeded. No record shows what the audio stage does with the signal on the LED pin beyond the capture at the jack, and no other pin or constraint fault was tried.
[behaviour] Everything the design does on the register window is as in b30_hil_audio, including its gaps; the LED[0] indicator is on a different pin from that design's, and nothing reads it.

## next_actions
1. Rebuild on Vivado 2026.1 and re-run flow/hil.py on that bitstream.
2. Capture the audio interface with no tone, so the check's thresholds can be shown to separate a working design from a silent one with margin.
3. Seed further faults of the same class (a swapped or floating pin) if the repair loop is to be tested on them.

## open_questions
- Should the hardware-in-the-loop stage feed this failure back to the agent's repair loop, and what constraint change should it suggest?

## history
2026-11-11 30 pr=-: created as the seeded-fault twin of b30_hil_audio; one board run caught the fault at the audio jack
2026-11-13 68 pr=-: handover written to the documentation standard
