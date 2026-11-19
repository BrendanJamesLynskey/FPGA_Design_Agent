# 8-bit enable counter

An 8-bit up counter for the Nexys A7-100T. It counts on every rising edge of the 100 MHz clock while switch SW0 is high and holds its value while SW0 is low. The centre button BTNC resets it to zero synchronously. The count is shown in binary on LED[7:0]. It wraps from 255 to 0. Nothing else.
