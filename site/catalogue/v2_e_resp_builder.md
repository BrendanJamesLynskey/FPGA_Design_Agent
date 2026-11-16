# Reply frame builder (v2_e_resp_builder)

Domain E (networking), tier T2 (L1 probe of the endpoint ladder), Nexys A7-100T. Part of the UDP command and telemetry endpoint ladder project (brief 82). Draft for the problem catalogue; the task files are in
`benchmark/v2/tasks/v2_e_resp_builder/`.

## The problem, and where it is used

The reply side of a command protocol: lay out the reply fields and payload as bytes, append the CRC-32, and let the host read the finished packet back byte by byte.

Every request and reply protocol has a framing step like this; the common mistakes are a check that covers the wrong bytes, a length byte that counts the frame instead of the payload, and the behaviour when the payload buffer is full.

## Hero diagram

Field boxes (type, status, sequence number, payload) slide into a byte strip; the check value is computed over the strip as it fills and appended at the end; the read-back index walks along the strip.

## Animation plan (driven by `hidden/model.py`)

Use the Model in hidden/model.py to set the fields, add payload bytes (including past the capacity) and build, then show the reply bytes, length, overflow flag and the check value.

## Interface

Shell registers: type, status, sequence number, payload byte, build, index, byte read-back, length, payload count and status word. LED[7:0] shows the reply length and LED[15:8] its status byte.

## Acceptance criteria in plain words

The reply is the type with its top bit set, the status, the sequence number high byte first, the payload length, the payload and the CRC-32 low byte first over everything before it; a byte written to a full payload buffer is dropped and sets the overflow flag; a build clears the payload and the flag; the finished reply stays readable until the next build and reads zero beyond its end.
