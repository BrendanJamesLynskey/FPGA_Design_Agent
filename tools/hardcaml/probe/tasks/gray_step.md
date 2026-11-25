Module name: `gray_step`

A 10-bit Gray-code stepper (the core of dev task t1_gray_stepper, without the button debouncer or the shell).

Ports (all names exact; one clock `clk`; reset `rst_n` is active low and synchronous):
- inputs: `clk`, `rst_n`, `step` (1 bit), `dir` (1 bit)
- output: `gray` (10 bits)

Behaviour: an internal 10-bit binary count is 0 after reset. In every clock where `step` is 1, the count moves by one: up when `dir` is 0, down when `dir` is 1, wrapping round at both ends (1023 + 1 gives 0; 0 - 1 gives 1023). `gray` is the Gray code of the count (count XOR count shifted right by one), and it shows the count as updated by the clock edge just taken (it is a function of the register, not of the inputs of the current clock).
