import numpy as np
import pandas as pd
import pytest

from pipeline import metrics
from pipeline.config import CLEAN_DIR

FEES = pd.DataFrame([
    {"channel": "amazon", "referral_pct": 0.15, "fulfilment_fee": 4.0, "monthly_fixed": 30.0},
    {"channel": "own_store", "referral_pct": 0.03, "fulfilment_fee": 1.0, "monthly_fixed": 100.0},
])


def line(**overrides):
    row = dict(order_id="ORD-1", channel="amazon", canonical_sku="VH-1", name="Thing",
               category="Cat", quantity=1, unit_price=100.0, discount=0.0,
               cost_price=40.0, shipping_cost=5.0, referral_pct=0.15,
               fulfilment_fee=4.0, returned_qty=0, resellable_qty=0,
               returns_provisional=False, order_date=pd.Timestamp("2025-01-15"))
    row.update(overrides)
    return row


def frame(*rows):
    return pd.DataFrame(list(rows))


def test_net_revenue_is_quantity_times_discounted_price():
    e = metrics.enrich(frame(line(quantity=2, unit_price=50.0, discount=5.0)), FEES)
    assert e["gross_revenue"].iloc[0] == 100.0
    assert e["discount_amount"].iloc[0] == 10.0
    assert e["net_revenue"].iloc[0] == 90.0


def test_cogs_counts_every_shipped_unit_even_when_returned():
    e = metrics.enrich(frame(line(quantity=3, cost_price=10.0, returned_qty=1)), FEES)
    assert e["cogs"].iloc[0] == 30.0


def test_lines_with_unknown_cost_are_dropped():
    e = metrics.enrich(frame(line(), line(canonical_sku="VH-2", cost_price=np.nan)), FEES)
    assert list(e["canonical_sku"]) == ["VH-1"]


def test_full_return_cancels_the_revenue():
    e = metrics.enrich(frame(line(quantity=1, returned_qty=1)), FEES)
    assert e["net_revenue"].iloc[0] - e["refund"].iloc[0] == 0.0


def test_return_adds_a_shipping_leg():
    e = metrics.enrich(frame(line(returned_qty=0), line(returned_qty=1)), FEES)
    assert e["return_shipping"].tolist() == [0.0, 5.0]


def test_platform_fee_totals_the_monthly_charge():
    # two amazon lines, one calendar month -> one month of the 30.0 fixed fee
    e = metrics.enrich(frame(line(), line(order_id="ORD-2")), FEES)
    assert e["platform_fee"].sum() == pytest.approx(30.0)


def test_platform_fee_splits_by_revenue_share():
    e = metrics.enrich(
        frame(line(unit_price=90.0), line(order_id="ORD-2", unit_price=30.0)), FEES)
    # shares are 75% / 25% of a single month's 30.0
    assert e["platform_fee"].tolist() == pytest.approx([22.5, 7.5])


def test_waterfall_reconciles_to_net_margin():
    e = metrics.enrich(
        frame(line(), line(order_id="ORD-2", quantity=2, returned_qty=1),
              line(order_id="ORD-3", channel="own_store", referral_pct=0.03,
                   fulfilment_fee=1.0)), FEES)
    wf = metrics.margin_waterfall(e)
    assert wf["step"].iloc[0] == "Gross revenue"
    assert wf["step"].iloc[-1] == "Net margin"
    assert wf["amount"].iloc[:-1].sum() == pytest.approx(wf["amount"].iloc[-1], abs=0.01)


def test_quadrants():
    g = pd.DataFrame([
        dict(canonical_sku="A", name="A", category="C", quantity=1,
             net_revenue=1000.0, net_margin=200.0),   # high rev, healthy
        dict(canonical_sku="B", name="B", category="C", quantity=1,
             net_revenue=1000.0, net_margin=-50.0),   # high rev, unhealthy
        dict(canonical_sku="C", name="C", category="C", quantity=1,
             net_revenue=10.0, net_margin=5.0),       # low rev, healthy
        dict(canonical_sku="D", name="D", category="C", quantity=1,
             net_revenue=10.0, net_margin=-1.0),      # low rev, unhealthy
    ])
    out = metrics.sku_profitability(g).set_index("canonical_sku")["quadrant"].to_dict()
    assert out == {"A": "Volume drivers", "B": "Hidden losers",
                   "C": "Quiet winners", "D": "Dead weight"}


def test_returns_summary_rate_and_flip_flag():
    e = metrics.enrich(
        frame(line(quantity=10, unit_price=30.0, cost_price=10.0, returned_qty=7)), FEES)
    s = metrics.returns_summary(e, "canonical_sku")
    assert s["return_rate"].iloc[0] == pytest.approx(7 / 10)
    # profitable before returns, negative after
    assert bool(s["returns_flip_negative"].iloc[0])


def test_headline_picks_the_biggest_high_revenue_loss():
    dates = pd.date_range("2025-01-01", "2025-12-31", periods=13)
    rows = []
    for i in range(12):  # a spread of healthy SKUs
        rows.append(line(order_id=f"O{i}", canonical_sku=f"VH-{i}", name=f"S{i}",
                         quantity=5, unit_price=40.0, cost_price=12.0,
                         order_date=dates[i]))
    rows.append(line(order_id="BAD", canonical_sku="VH-BAD", name="Loss Leader",
                     quantity=40, unit_price=60.0, cost_price=30.0, returned_qty=18,
                     order_date=dates[12]))
    h = metrics.headline_finding(metrics.enrich(frame(*rows), FEES)).iloc[0]
    assert h["name"] == "Loss Leader"
    assert h["annual_loss_eur"] > 0


@pytest.mark.skipif(not (CLEAN_DIR / "order_lines.parquet").exists(),
                    reason="run the pipeline first")
def test_story_holds_on_real_data():
    ol = pd.read_parquet(CLEAN_DIR / "order_lines.parquet")
    fees = pd.read_parquet(CLEAN_DIR / "channel_fees.parquet")
    sku = metrics.sku_profitability(metrics.enrich(ol, fees))

    top5 = set(sku.head(5)["name"])
    for name in ["Stainless Steel Stand Mixer", "Cast Iron Casserole 5L",
                 "Ceramic Dinner Set 12-Piece"]:
        row = sku[sku["name"] == name].iloc[0]
        assert row["net_margin"] < 0, f"{name} should be loss-making"
        assert name in top5, f"{name} should be a top-5 revenue SKU"
