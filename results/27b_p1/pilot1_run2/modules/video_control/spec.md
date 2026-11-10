The shell owns the USB-UART and register window. Place PATTERN at offset
0x00 and FRAME_COUNT at offset 0x04 relative to window_base 0x00, which
corresponds to addresses in the shell's 0x80-0xFF window. Support the
newline-terminated ASCII ID?, PAT n, and FRAME? commands with line-terminated
responses. PAT command behavior beyond the specified bars follows
assumption A-1.
