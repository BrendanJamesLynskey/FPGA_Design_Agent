# AES-128 encryption over the USB-UART

I want the Nexys A7-100T to encrypt one block of data with the AES-128 cipher when my PC sends it a key and a block over the USB serial port, and to send the encrypted block back.

- The cipher is AES with a 128-bit key, exactly as published in FIPS 197 (encryption only, one 16-byte block at a time, no chaining). Bytes are in the order the standard writes them: byte 0 first.
- The serial link: 115200 baud, 8 data bits, no parity, 1 stop bit, on the board's USB-serial port.
- The request is 32 bytes: the 16 key bytes, byte 0 first, and then the 16 plaintext bytes, byte 0 first. As soon as the 32nd byte has arrived the board encrypts and then sends back exactly 16 bytes, the ciphertext, byte 0 first.
  Nothing is remembered from one request to the next: every request carries its own key. (This is a bench demonstration; I know a key sent over a serial cable is not secret.)
  While it is working, further input bytes can be ignored. The PC always waits for the reply before the next request.
- The active-low reset button (CPU_RESETN) returns the board to waiting for the first byte of a request. Show on LED0 that the board is busy (from the 32nd byte until the reply is sent).
- The subject of this design is the USB-UART itself, so it does not embed the test shell; I will test it with a serial driver at the real protocol and a faster baud rate.

Test hooks: top module `c16_nexys_aes_uart_top`, ports named as in the board's master XDC, and a `CLKS_PER_BIT` parameter as a top-level parameter (868 on the board; the bench shrinks it). There are no other time constants.
