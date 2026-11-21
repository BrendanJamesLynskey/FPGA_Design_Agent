"""Brief 117: the story pages (home, worked example, inspect) are built from the committed records."""
import json
import sys
from pathlib import Path

SITE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SITE))
import build  # noqa: E402
import worked  # noqa: E402


def test_kr260_data_is_current():
    assert json.loads((SITE / "data" / "kr260.json").read_text()) == json.loads(json.dumps(worked.build()))


def test_every_cell_has_a_record_and_a_state():
    d = worked.build()
    kinds = {k["id"] for k in d["kinds"]}
    for r in d["requirements"]:
        assert r["cells"], r["id"]
        for k, c in r["cells"].items():
            assert k in kinds and c["state"] in ("pass", "measured")
            assert (worked.ROOT / c["file"]).exists()
            assert "{" not in c["text"], c["text"]


def test_pages_tell_the_story_and_link_the_matrix_from_one_place():
    d = build.load_data(None)
    pages, bad = build.build(SITE / "public", d)
    assert not bad
    for fn in ("index.html", "worked-example.html", "inspect.html"):
        assert fn in pages
    home = pages["index.html"]
    assert "You specify and judge" in home and "Hardware verification is its own layer" in home
    assert 'id="evm"' in home and "EVIDENCE 2: hardware" in home
    for fn in ("index.html", "worked-example.html", "inspect.html"):
        assert f'href="{worked.TRACE_HREF}"' in pages[fn]
    assert "Brief 118" in pages["inspect.html"] and "python -m flow inspect" in pages["inspect.html"]


def test_a_changed_record_fails_the_export(tmp_path, monkeypatch):
    y = (SITE / "worked" / "worked.yaml").read_text().replace("partitions proved: 219", "partitions proved: 218")
    monkeypatch.setattr(worked.Path, "read_text", lambda self, *a, **k: y if self.name == "worked.yaml" else Path.read_bytes(self).decode())
    try:
        worked.build()
    except AssertionError as e:
        assert "eqy_parts" in str(e)
    else:
        raise AssertionError("a quote that is not in the record must fail")
