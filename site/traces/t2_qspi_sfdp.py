"""Flash ID and SFDP read: the model's two transactions, one byte on the wire per step (the flash contents are the stimulus)."""

def trace(m):
    import importlib.util
    from pathlib import Path
    p = Path(m.__file__).with_name("flash_model.py")      # the bench's flash: the same ID and SFDP table the tests use
    spec = importlib.util.spec_from_file_location("_flash_t2_qspi_sfdp", p)
    fm = importlib.util.module_from_spec(spec); spec.loader.exec_module(fm)
    IDENT, SFDP = fm.IDENT, fm.SFDP_TABLE
    md = m.Model()
    txs = md.start(IDENT, SFDP)
    rows = []   # (phase, mosi, miso, csn, caption_text)
    done_after = {}
    rows.append(("idle", None, None, 1, "Chip select is high: the flash is not selected. The start command has just been written."))
    for ti, (ops, n) in enumerate(txs):
        rows.append(("select", None, None, 0, f"Chip select goes low for transaction {ti + 1}."))
        for j in range(n):
            if j < len(ops):
                what = "command" if j == 0 else "address"
                rows.append((what, ops[j], None, 0, f"The master sends {what} byte {ops[j]:#04x}."))
            elif ti == 1 and j == len(ops):
                rows.append(("dummy", None, None, 0, "Eight dummy clocks: the flash needs them to prepare its data; nothing useful is sent or read."))
            else:
                if ti == 0:
                    b = IDENT[j - len(ops)]
                    rows.append(("ID byte", None, b, 0, f"The flash returns ID byte {j - len(ops)}: {b:#04x}."))
                else:
                    k = j - len(ops) - 1
                    b = SFDP[k]
                    rows.append(("SFDP byte", None, b, 0, f"The flash returns SFDP byte {k}: {b:#04x}."))
        rows.append(("deselect", None, None, 1, "Chip select goes high, ending the transaction." + (f" The ID register now reads {md.read(m.ID):06X}." if ti == 0 else
                    f" Status: done, signature {'matches' if md.read(m.STATUS) & m.SIG_OK else 'does not match'} (SFDP word 0 reads {md.read(m.SFDP0):08X}).")))
        done_after[len(rows) - 1] = ti
    x, ph, mo, mi, cs, idr, s0, sig, cap = [], [], [], [], [], [], [], [], []
    seen_id = seen_sig = False
    for i, (p, a, b, c, t) in enumerate(rows):
        ti = done_after.get(i)
        if ti == 0:
            seen_id = True
        if ti == 1:
            seen_sig = True
        x.append(i); ph.append(p); mo.append(a or 0); mi.append(b or 0); cs.append(c)
        idr.append(md.read(m.ID) if seen_id else 0)
        s0.append(md.read(m.SFDP0) if seen_sig else 0)
        sig.append(int(bool(md.read(m.STATUS) & m.SIG_OK)) if seen_sig else 0)
        cap.append(f"Step {i}: {t}")
    return {
        "stimulus": f"A start command is given; the flash is the bench's own flash model, answering ID {IDENT[:3].hex(' ')} and an SFDP table whose first four bytes spell the signature. "
                    "Two transactions follow, each shown byte by byte; MOSI is shown as 0 when the master sends nothing useful.",
        "unit": "step", "x": x,
        "signals": [
            {"name": "phase", "kind": "text", "v": ph},
            {"name": "QSPI_CSN", "kind": "bit", "v": cs},
            {"name": "MOSI byte", "kind": "bus", "radix": "hex", "width": 8, "v": mo},
            {"name": "MISO byte", "kind": "bus", "radix": "hex", "width": 8, "v": mi},
            {"name": "ID", "kind": "bus", "radix": "hex", "width": 24, "v": idr},
            {"name": "SFDP0", "kind": "bus", "radix": "hex", "width": 32, "v": s0},
            {"name": "SIG_OK", "kind": "bit", "v": sig},
        ],
        "captions": cap,
    }
