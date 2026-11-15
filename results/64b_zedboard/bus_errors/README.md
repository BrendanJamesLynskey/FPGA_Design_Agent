# Bus-error behaviour, ZedBoard bump (Zynq-7000, Cortex-A9 core 0, bare metal)

One access type per run: file `e_<target><write><attr>.log`; target 0 hole in `zb_hole_okay`, 1 `zb_hole_slverr`, 2 `zb_hole_split`,
3 an address between two block windows (DECERR from `axil_xbar`), 4 above the last window; write 0 = read, 1 = write; attr 0 =
strongly ordered (SO), 1 = device (DEV), 2 = normal non-cacheable (NC) mapping of the PL window. 200 accesses per run, async aborts
unmasked, `ldr`/`str` followed by `dsb`, `isb`. The DDR console log is the record (the UART showed the same text when readable).
Vivado 2026.1 build `zb_hwsw`; ps7_init DDR3 settings from the ZedBoard guide; operating conditions in each log (Tj 35-40 C,
rails nominal, no alarm).

All 30 runs (5 targets x read/write x 3 mappings) were made on 2026-11-15 after a power cycle, a single full load (hello program) and light
reloads only; none wedged the PS. The SO runs e_000, e_010, e_100, e_110, e_200, e_210 and e_300 were made in the earlier session (2026-11-14, before the PS wedged); the rest on 2026-11-15. Records:
`summary.json` (`bus_errors`) is read from these logs by `designs/b64b_zedboard/make_summary.py`.

## Reads and writes with the strongly ordered mapping (precise)

| access | result of 200 attempts |
|---|---|
| read hole, `okay` | no abort, value 0 |
| write hole, `okay` | no abort |
| read hole, `slverr` | 200 precise data aborts, DFSR 0x1008 (external abort, precise, read), DFAR = the address, load result not written |
| write hole, `slverr` | 200 precise aborts at the write's barrier, DFSR 0x1808 (WnR=1), DFAR = the address |
| read hole, `split` | 200 precise aborts, DFSR 0x1008 |
| write hole, `split` | no abort (write ignored) |
| read outside every block (DECERR) | 200 precise aborts, DFSR 0x008 (ExT = 0: DECERR is distinguishable from SLVERR by DFSR bit 12), DFAR = the address |
| write outside every block (DECERR), between two windows and above the last | 200 precise aborts at the write's barrier, DFSR 0x808 (WnR=1, ExT=0), DFAR = the address |

## Device and normal non-cacheable mappings (imprecise reads, writes lost)

| access | result of 200 attempts |
|---|---|
| read hole `slverr` or `split`, DEV or NC | 200 aborts, each an **imprecise** external abort: DFSR 0x1406 (FS 0b10110, ExT=1), taken at the `isb` after the load (return address 8 bytes after it), DFAR unreliable (in six of the eight runs it is a stale value, in the two above-window runs it happens to equal the address), the load returned 0 |
| read outside every block (DECERR), DEV or NC | 200 imprecise aborts, DFSR 0x406 (ExT=0), same timing, stale DFAR |
| read hole `okay`, DEV or NC | no abort, value 0 |
| **write** to any hole or outside address (`okay`, `slverr`, `split`, DECERR), DEV or NC | **no abort at all** in 200 attempts, although `dsb` and a delay of about 1-2 us follow every store; the error-capture block did record the writes (STICKY set, IS_WRITE set) for the holes |

So on this part an error response to a posted write (Device or Normal non-cacheable memory) is lost, and the only trace is the
slave's own capture register; the strongly ordered mapping is the only one in which a write error reaches the core, and then precisely.
A read error with a non-SO mapping arrives as an imprecise abort one or two instructions late and without the address, so the address can
only come from the capture register or from a precise (SO) re-read.

## Capture block

The error-capture registers (offsets 0xFF8 address, 0xFFC status) read back address 0x100 and a count of 200 with the read/write bit as
expected in every hole run with the SO and DEV mappings, including `okay` (where no abort is taken). With the NC mapping the count field
reads 255 (it saturates at 255) in the hole runs, that is, **more** than 200 accesses reached the slave for 200 CPU accesses. The cause is not
known (Normal-memory behaviour of the A9 or the interconnect is the suspect: speculative or repeated accesses); not investigated further.

Not measured: Linux (user space through UIO mmap or `devmem`, kernel driver), and any run beyond 200 attempts per access type.
