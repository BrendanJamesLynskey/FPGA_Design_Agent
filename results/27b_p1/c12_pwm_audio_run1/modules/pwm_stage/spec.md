Uses a free-running 10-bit counter in the 100 MHz clock domain. Duty resets to 512 and is
captured from 512 + floor(sample_in / 128) at counter rollover for use in the following
PWM period. The output is pulled low when counter >= duty and otherwise released to
high impedance; it is never driven high.
