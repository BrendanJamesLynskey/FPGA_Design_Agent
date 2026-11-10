This single RTL block is the audio output stage. Its shell register window has
SAMPLE at 0x00, GAIN at 0x01, and SOUT at 0x02. SAMPLE holds the signed 16-bit
sample written in bits [15:0]; reads return zero in bits [31:16]. GAIN is
write-only: writing bits [15:0] sets the gain, capped at 8192, and reads return
zero. SOUT returns sample_out in bits [15:0] and zero in bits [31:16].
The gain register resets to 2068. SAMPLE_OUT is the combinational signed result
floor(sample * gain / 32768).
The PWM counter is free-running, 10 bits wide, and resets to zero on CPU_RESETN.
The duty value is 512 + floor(sample_out / 128), latched at counter wrap for the
following period. AUD_PWM is pulled low at or above the duty value and otherwise
left high-impedance. AUD_SD is held high and LED is held off.
The top-level integration also exposes the shell-owned USB-UART pins and forwards
CLKS_PER_BIT, TIMEOUT_CYCLES, and BUILD_STAMP to the test shell.
