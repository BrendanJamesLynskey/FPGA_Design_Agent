The always-present shell owns USB-UART at 115200 baud and the 0x80-0xFF register
window. Implement the defaulted newline-terminated 8-N-1 ASCII commands PATTERN n,
FRAME?, and ID?, returning requested values as ASCII lines.
