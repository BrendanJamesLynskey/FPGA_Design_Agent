"""Brief 40: every packet-processing ip.yaml agrees with its RTL (parameters and defaults), its sweep points lie in the
declared space, its guards lie outside it, and the generated READMEs are current. No simulator needed."""
from flow.net import ipdoc


def test_ip_yaml_matches_rtl_and_readmes_current():
    errs = []
    for b in ipdoc.NET + ipdoc.NET63 + ipdoc.HIL:
        errs += ipdoc.check(b)
        p = ipdoc.IP / b / "README.md"
        if not p.exists() or p.read_text() != ipdoc.readme(b):
            errs.append(f"stale README: {p} (run python3 flow/net/ipdoc.py)")
    assert not errs, "\n".join(errs)


def test_every_register_interface_has_a_registers_section():
    """Brief 64A2 (owner, 2026-11-13: every register block has a datasheet): an entry with an AXI4-Lite slave interface
    and no register_map fails --check; a reason for having none is accepted; the README section is generated."""
    y = {"interfaces": [{"name": "s_axil", "type": "axi4-lite", "dir": "slave"}]}
    assert any("no Registers section" in e for e in ipdoc.register_problems("x", y))
    assert ipdoc.register_problems("x", dict(y, register_map={"none": "forwards every access"})) == []
    assert ipdoc.register_problems("x", dict(y, register_map={"none": " "})) != []
    assert ipdoc.register_problems("x", {"interfaces": [{"type": "axis", "dir": "slave"}]}) == []
    for b in ipdoc.NET + ipdoc.NET63 + ipdoc.HIL + ipdoc.DSP + ipdoc.CPU + ipdoc.INFRA:
        assert ipdoc.register_problems(b, __import__("yaml").safe_load((ipdoc.IP / b / "ip.yaml").read_text())) == [], b
    t = (ipdoc.IP / "axil_table_ctrl" / "README.md").read_text()
    reg = t.split("## Registers\n\n", 1)[1]
    first = reg.split("\n\n", 1)[0]
    assert first.startswith("It differs from the house register conventions (docs/hwsw.md) in 2 ways: byte strobes")
    assert "Unmapped addresses answer OKAY and read 0." in first
    for topic in ("**Unmapped addresses.**", "**Reserved bits.**", "**Reads have no side effects.**",
                  "**Partial writes.** Byte strobes (WSTRB) are ignored", "**Reset.** `rst`, synchronous, active high",
                  "**Interrupt.** None", "**Clock domain and timing.** Every field is in the `clk` domain"):
        assert topic in reg, topic
    assert "DECERR" in (ipdoc.IP / "axil_xbar" / "README.md").read_text().split("## Registers", 1)[1]
