"""Brief 190, item 18: the reference-stream generator and the birthday-bound helpers (pure Python, no simulator)."""
from __future__ import annotations

import math
from pathlib import Path

from designs.b110_itch_ouch.model import refstream as R

D = Path(__file__).parent.parent


def test_birthday_bound_matches_hand_values_and_monte_carlo() -> None:
    # 100 live items in 4096 slots: n(n-1)/(2m) = 9900/8192 = 1.2085, so 1 - exp(-1.2085) = 0.70
    assert abs(R.p_any_collision_approx(100, 4096) - (1 - math.exp(-9900 / 8192))) < 1e-12
    assert 0.700 < R.p_any_collision(100, 4096) < 0.706
    assert abs(R.uniform_monte_carlo(100, 4096, 3000, seed=7) - R.p_any_collision(100, 4096)) < 0.03
    assert R.p_any_collision(5000, 4096) == 1.0                     # more items than slots: a collision is certain
    assert R.p_any_collision(1, 1000) == 0.0


def test_sizing_for_one_percent_and_power_of_two() -> None:
    m = R.slots_for_collision_probability(100, 0.01)
    assert 490_000 < m < 495_000
    assert R.p_any_collision_approx(100, m) <= 0.0100001
    assert R.pow2_at_least(m) == 1 << 19 and R.pow2_at_least(4096) == 4096 and R.pow2_at_least(1) == 1


def test_per_insert_rate_is_live_over_slots_for_small_loads() -> None:
    assert abs(R.p_new_item_finds_slot_taken(40, 4096) - 40 / 4096) < 5e-5


def test_stream_is_deterministic_ordered_and_pairs_every_delete_with_an_add() -> None:
    cfg = R.StreamCfg(seed=3, n_orders=2000)
    a, b = R.events(cfg), R.events(cfg)
    assert a == b and a != R.events(R.StreamCfg(seed=4, n_orders=2000))
    assert [t for t, _, _ in a] == sorted(t for t, _, _ in a)
    added: set[int] = set()
    for _, kind, rf in a:
        if kind == "add":
            assert rf not in added
            added.add(rf)
        else:
            assert rf in added                                       # a delete never comes before its add
    assert sum(k == "add" for _, k, _ in a) == 2000
    day_long = 2000 - sum(k == "del" for _, k, _ in a)
    assert 0 < day_long < 80                                          # about 1 % never deleted


def test_references_are_sparse_and_heavy_tailed_not_tidy() -> None:
    ev = R.events(R.StreamCfg(seed=1, n_orders=5000))
    refs = [rf for _, k, rf in ev if k == "add"]
    gaps = [b - a for a, b in zip(refs, refs[1:])]
    assert 20 < sum(gaps) / len(gaps) < 45                            # gap_mean 30 others between ours
    t_add = {rf: t for t, k, rf in ev if k == "add"}
    life = sorted(t - t_add[rf] for t, k, rf in ev if k == "del")
    assert life[len(life) // 2] < 60 and life[-1] > 1000             # a short median and a long tail


def test_direct_map_refusals_fall_with_table_size_and_a_second_slot_helps() -> None:
    ev = R.events(R.StreamCfg(seed=1, n_orders=8000))
    prev = 2.0
    for bits in (8, 10, 12, 14):
        one, two = R.replay_direct(ev, bits), R.replay_two_slot(ev, bits)
        assert one["adds"] == two["adds"] == 8000
        assert two["refused"] <= one["refused"]
        rate = one["refused"] / one["adds"]
        assert rate < prev
        prev = rate
    big = R.replay_two_slot(ev, 14)
    assert big["refused"] / big["adds"] < 0.005                       # 16384 slots, two candidates: far below the one-slot rate


def test_a_table_never_refuses_when_it_is_large_enough_for_the_live_set_and_refs_are_dense() -> None:
    ev = R.events(R.StreamCfg(seed=2, n_orders=300, gap_mean=0.0, day_long=0.0, life_median=5.0, life_sigma=0.5))
    assert R.replay_direct(ev, 12)["refused"] == 0


def test_multiplying_by_an_odd_constant_does_not_change_low_bit_collisions() -> None:
    """The first draft's 'scattered' mode did this and measured the same refusals as the plain counter: an odd multiplier is a bijection on the
    low b bits, so a table indexed by those bits sees the same collision pattern."""
    ev = R.events(R.StreamCfg(seed=5, n_orders=3000))
    mult = [(t, k, (rf * 0x9E3779B97F4A7C15) & ((1 << 64) - 1)) for t, k, rf in ev]
    assert R.replay_direct(ev, 9)["refused"] == R.replay_direct(mult, 9)["refused"]


def test_results_file_is_generated_by_the_script_and_names_it() -> None:
    f = D.parents[1] / "results" / "190_refstream" / "results.md"
    t = f.read_text()
    assert "refstream_measure.py" in t and "| 100 | 4096 |" in t and "0.7043" in t
