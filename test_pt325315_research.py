from strategies import pt325315_research as r
from strategies import independent_flash_filters as iff


def event(**overrides):
    row = {
        "timestamp": "2026-09-25T16:30:00+00:00",
        "flash_drop_pct": 1.5,
        "pre_return_pct": 1.6,
        "pre_r2": .85,
        "pre30_return_std_pct": .30,
        "target_price": 10.8,
    }
    row.update(overrides)
    return row


def test_family_is_large_unique_and_independent_registry_ids():
    assert len(r.IDS) >= 60
    assert len(r.IDS) == len(r.SPECS)
    assert r.IDS <= iff.IDS
    assert "PT325315" not in r.IDS


def test_combo_carries_own_exit_state():
    row = r.refresh("PT315XMF", event(), 10.0)
    assert row["strategy_id"] == "PT315XMF"
    assert row["source_strategy_id"] == "PT325315"
    assert row["exit_model"] == "k_checkpoint"
    assert row["mode"] == "conditional_mfe"
    assert row["seconds"] == 900
    assert row["min_mfe_pct"] == .25
    assert row["stop_price"] == 9.8


def test_parent_config_not_mutated():
    before = dict(r.parent.CONFIG)
    _ = r.config("PT315RB30")
    assert r.parent.CONFIG == before
    assert r.config("PT315RB30")["rebound_confirmation_pct"] == .003


def test_entry_axes_are_independent():
    assert r.accepts("PT315PR150", event(pre_return_pct=1.6), 10)
    assert not r.accepts("PT315PR150", event(pre_return_pct=1.4), 10)
    assert r.accepts("PT315VU40", event(), 10)  # 1.5/.30 = 5 units
    assert not r.accepts("PT315VU40", event(pre30_return_std_pct=.5), 10)


def test_entry_price_filter_happens_after_rebound():
    low = r.refresh("PT315PLOW", event(target_price=6.0), 4.5)
    high = r.refresh("PT315PLOW", event(target_price=21.0), 20.0)
    assert r.validate("PT315PLOW", low, .2)[0]
    assert not r.validate("PT315PLOW", high, .2)[0]
