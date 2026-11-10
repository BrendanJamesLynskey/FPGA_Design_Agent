"""AES-128: the FIPS 197 appendix B request from the model's test list, one round operation a step, from the model's
own round functions; the state after each round is checked against the model's trace."""

REQ = 0     # the model's first request: FIPS 197 appendix B key and plaintext


def trace(m):
    req = bytes.fromhex(m.requests()[REQ])
    key, pt = req[:16], req[16:]
    rk = m.expand_key(key)
    rounds = []
    m.aes128_encrypt(key, pt, rounds)
    steps = []          # (round, operation, state)
    s = [a ^ b for a, b in zip(pt, rk[0])]
    steps.append((0, "input", list(pt)))
    steps.append((0, "AddRoundKey", s))
    for r in range(1, 11):
        s = [m.SBOX[b] for b in s]; steps.append((r, "SubBytes", s))
        s = m._shift_rows(s); steps.append((r, "ShiftRows", s))
        if r != 10:
            s = m._mix_columns(s); steps.append((r, "MixColumns", s))
        s = [a ^ b for a, b in zip(s, rk[r])]; steps.append((r, "AddRoundKey", s))
        assert bytes(s) == rounds[r], "round state must match the model's trace"
    assert bytes(s).hex() == m.reply_for(m.requests()[REQ])
    hexs = [bytes(st).hex() for _, _, st in steps]
    WHAT = {"input": "the plaintext as the 4 x 4 state (bytes go down the columns)",
            "SubBytes": "every byte replaced through the S-box", "ShiftRows": "row r rotated left by r bytes",
            "MixColumns": "each column mixed in GF(2^8)", "AddRoundKey": "round key XORed in"}
    cap = []
    for k, (r, op, st) in enumerate(steps):
        c = f"Round {r}, {op}: {WHAT[op]}" + (f" (round key {rk[r].hex()})" if op == "AddRoundKey" else "") + "."
        if k == len(steps) - 1:
            c += f" Ciphertext {hexs[k]}, the reply the board must send."
        cap.append(c)
    return {
        "stimulus": f"Key {key.hex()} and plaintext {pt.hex()} (FIPS 197 appendix B), one AES-128 operation per step.",
        "unit": "step", "x": list(range(len(steps))),
        "signals": [
            {"name": "round", "kind": "bus", "radix": "dec", "v": [r for r, _, _ in steps]},
            {"name": "operation", "kind": "text", "v": [op for _, op, _ in steps]},
            {"name": "state", "kind": "text", "v": hexs},
        ],
        "captions": cap,
        "hero": {"states": [list(st) for _, _, st in steps], "ops": [op for _, op, _ in steps]},
    }
