# v2_e_resp_builder: unstated details

Details left to the interview; the oracle answers from the formal spec.

- The CRC covers all bytes before it, header included; low byte first.
- The length byte is the payload length, not the frame length.
- Capacity is 24 and extra bytes are dropped with a sticky flag, cleared by the build.
- TYPE keeps 7 bits, IDX 7 bits.
- The reply stays readable after the next payload bytes are gathered.
- PBYTE and BUILD read as zero; unmapped read zero.
