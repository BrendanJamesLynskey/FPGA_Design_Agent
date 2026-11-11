"""Brief 40: every packet-processing ip.yaml agrees with its RTL (parameters and defaults), its sweep points lie in the
declared space, its guards lie outside it, and the generated READMEs are current. No simulator needed."""
from flow.net import ipdoc


def test_ip_yaml_matches_rtl_and_readmes_current():
    errs = []
    for b in ipdoc.NET:
        errs += ipdoc.check(b)
        p = ipdoc.IP / b / "README.md"
        if not p.exists() or p.read_text() != ipdoc.readme(b):
            errs.append(f"stale README: {p} (run python3 flow/net/ipdoc.py)")
    assert not errs, "\n".join(errs)
