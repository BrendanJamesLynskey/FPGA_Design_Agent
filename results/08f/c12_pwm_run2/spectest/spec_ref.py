"""Reference model of the PWM audio output stage, written from the request only."""

GAIN_RESET = 2068        # "It resets to 2068"
GAIN_MAX = 8192          # "any value above 8192 is replaced by 8192"
PERIOD = 1024            # 10-bit free-running counter
ID_PWMA = 0x50574D41     # "PWMA", MSB first (PROTOCOL.md DESIGN_ID)


def to_signed16(v):
    v &= 0xFFFF
    return v - 0x10000 if v & 0x8000 else v


def clamp_gain(w):
    return min(w & 0xFFFF, GAIN_MAX)


def sample_out(sample, gain):
    """floor(sample * gain / 2^15), signed sample, unsigned Q15 gain (floor, not truncation to zero)."""
    return (to_signed16(sample) * gain) >> 15


def duty(sample, gain):
    """512 + floor(sample_out / 128)."""
    return 512 + (sample_out(sample, gain) >> 7)


def low_clocks(sample, gain):
    """Pin is pulled low while counter >= duty: 1024 - duty clocks per period."""
    return PERIOD - duty(sample, gain)
