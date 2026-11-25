# CRC-32 checker

I want a block for the Nexys A7-100T that takes 32-bit data words over the UART test shell, computes the standard
Ethernet CRC-32 (IEEE 802.3, polynomial 0xEDB88320, reflected) of the stream so far one word per clock, and lets me
read the running CRC back and clear it. The 16 LEDs show the low 16 bits of the CRC. Reset with the CPU reset
button. The design ID reads "CRC3".
