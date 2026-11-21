"""The Python twin of the ML stage (model/twin.py) against the brief 87 references it is built from, and the stream builder's properties."""
from __future__ import annotations

import numpy as np

from designs.b58a_trigger.model import benchfeed as bf
from designs.b87_ml_trading.model import arms as A
from designs.b87_ml_trading.model import lobsim as L
from designs.b96_kr260_10g.model import pcs
from designs.b96_kr260_10g.rm_gp_ml.model import stream
from designs.b96_kr260_10g.rm_gp_ml.model.twin import Twin, load_gbt


def test_good_stream_equals_the_87_feature_state_and_the_integer_model() -> None:
    """With every frame good the twin is the 87 chain: FeatureState fed with the book before each message and the previous message's trade sign, then the integer trees."""
    msgs = stream.orderflow_msgs(300, 4242) + stream.stress_msgs(100, 5)
    tw = Twin(inst=stream.INST, thr=stream.THR)
    book, fs, pend, feats = [0, 0, 0, 0], L.FeatureState(0, 0, 0, 0), 0, []
    got = []
    for m in msgs:
        got.append(tw.frame(m, True))
        feats.append(fs.update(*book, pend))
        pend = (1 if m.side == bf.ASK else -1) if m.type == bf.TRADE else 0
        i = 2 if m.side == bf.ASK else 0
        if m.type in (bf.ADD, bf.MODIFY):
            book[i], book[i + 1] = m.price, m.size
        elif m.type == bf.CANCEL:
            book[i], book[i + 1] = 0, 0
        elif m.type == bf.TRADE and book[i] == m.price and book[i + 1] != 0:
            book[i + 1] = max(0, book[i + 1] - m.size)
            if book[i + 1] == 0:
                book[i] = 0
    cls = A.gbt_predict_int(load_gbt(), np.array(feats, dtype=np.int64))
    assert [o.feat for o in got] == [Twin.pack(f) for f in feats]
    assert [o.cls for o in got] == cls.tolist()


def test_a_bad_frame_changes_nothing() -> None:
    msgs = stream.orderflow_msgs(120, 9)
    a, b = Twin(inst=stream.INST, thr=stream.THR), Twin(inst=stream.INST, thr=stream.THR)
    out_a, out_b = [], []
    for i, m in enumerate(msgs):
        out_a.append(a.frame(m, True))
        if i % 5 == 2:
            b.frame(bf.Msg(bf.TRADE, bf.ASK, stream.INST, 1, 99), False)       # a bad frame in between
        out_b.append(b.frame(m, True))
    assert [(o.feat, o.cls) for o in out_a] == [(o.feat, o.cls) for o in out_b]


def test_other_instruments_do_not_move_the_state_or_get_vetoed() -> None:
    tw = Twin(inst=3, thr=10002, veto_mode=True)
    o = tw.frame(bf.Msg(bf.ADD, bf.ASK, 9, 10001, 1), True)
    assert o.hit and not o.trk and not o.veto and o.order and tw.book == [0, 0, 0, 0]


def test_veto_needs_up() -> None:
    tw = Twin(inst=3, thr=10002, veto_mode=True)
    tw.frame(bf.Msg(bf.ADD, bf.BID, 3, 10000, 200), True)
    o = tw.frame(bf.Msg(bf.ADD, bf.ASK, 3, 10001, 1), True)
    assert o.cls == 2 and o.order and not o.veto
    tw2 = Twin(inst=3, thr=10002, veto_mode=True)
    tw2.frame(bf.Msg(bf.ADD, bf.BID, 3, 10000, 1), True)
    tw2.frame(bf.Msg(bf.ADD, bf.ASK, 3, 10001, 200), True)             # a heavy ask over a light bid: the model says down
    o2 = tw2.frame(bf.Msg(bf.ADD, bf.ASK, 3, 10001, 200), True)
    assert o2.cls == 0 and o2.veto and not o2.order


def test_stream_words_decode_to_the_frames_sent() -> None:
    """The injected words, passed through the Python receive PCS and parser, give back every frame with the intended FCS verdict."""
    words, e = stream.make_stream(seed=3, n_events=30, n_stress=10)
    rx = pcs.RxPcs()
    for w in words:
        rx.step(w)
    frames = [f for f in pcs.parse_xgmii([(d, c) for d, c, _ in rx.out]) if "data" in f]
    assert len(frames) == e["summary"]["frames"]
    assert sum(1 for f in frames if not f["fcs_ok"]) == e["summary"]["kinds"].get("bad_fcs", 0)
