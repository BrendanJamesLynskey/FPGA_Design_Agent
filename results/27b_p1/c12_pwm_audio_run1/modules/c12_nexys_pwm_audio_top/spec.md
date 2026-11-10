Integrates audio_state and pwm_stage with the always-present shell. The shell owns the USB-UART
pins and register window. The design uses CLK100MHZ and CPU_RESETN, and exposes AUD_PWM,
AUD_SD, and the 16-bit LED output. Reset asserts asynchronously and releases synchronously
into the clock domain. AUD_PWM is open-drain style, AUD_SD is held high, and LED is held off.
The shell protocol is shell/PROTOCOL.md version 1.0.
