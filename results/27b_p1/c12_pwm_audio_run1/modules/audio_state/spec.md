Holds a signed 16-bit sample and unsigned Q15 gain register. Reset clears the sample and sets
gain to 2068. Shell writes to gain are capped at 8192. sample_out is the signed 16-bit
floor(sample * gain / 32768) result and is available combinationally.
The shell register map uses SAMPLE at offset 0x00 (RW, reset 0), GAIN at offset 0x01
(WO, reset 0), and SOUT at offset 0x02 (RO, reset 0). Each is 32 bits; bits [15:0] hold
the sample, written gain, or sample_out, respectively, and bits [31:16] read as zero.
SAMPLE and SOUT use two's-complement values. GAIN writes set the gain, capped at 8192;
the GAIN register cannot be read back and reads as zero. Unmapped offsets read zero;
writes to unmapped offsets and RO registers are ignored.
