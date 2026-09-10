"""Margin maths for the dashboard.

Pure functions over the cleaned order lines, plus a build step that writes
page-ready tables to data/clean/marts/.

The model, per order line (everything already net of VAT):

    net revenue = quantity * (unit_price - discount)
    net margin  = net revenue - COGS - shipping - channel fees
                  - refunds - return shipping

Channel fees: referral is a % of net revenue, fulfilment is per unit, the
monthly platform fee is split across lines pro-rata by net revenue within a
channel. A return reverses the sale (refund + return postage).

Run with:  python -m pipeline.metrics
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from pipeline.config import CLEAN_DIR

MARTS_DIR = CLEAN_DIR / "marts"

# SKU matrix cutoffs: "high revenue" is above the mean (right-skewed, so this
# is roughly the top third), "healthy" is margin above this. Blunt on purpose.
HEALTHY_MARGIN_PCT = 0.10

WATERFALL_STEPS = [
    ("Gross revenue", "gross_revenue", 1),
    ("Discounts", "discount_amount", -1),
    ("COGS", "cogs", -1),
    ("Outbound shipping", "outbound_shipping", -1),
    ("Referral fees", "referral_fee", -1),
    ("Fulfilment fees", "fulfilment", -1),
    ("Platform fees", "platform_fee", -1),
    ("Refunds", "refund", -1),
    ("Return shipping", "return_shipping", -1),
]


def enrich(order_lines: pd.DataFrame, channel_fees: pd.DataFrame) -> pd.DataFrame:
    """Add per-line margin components. Lines with unknown cost are dropped:
    the revenue is real but the margin isn't computable."""
    df = order_lines[order_lines["cost_price"].notna()].copy()
    q = df["quantity"]

    df["gross_revenue"] = q * df["unit_price"]
    df["discount_amount"] = q * df["discount"]
    df["net_revenue"] = df["gross_revenue"] - df["discount_amount"]
    df["cogs"] = q * df["cost_price"]
    df["outbound_shipping"] = df["shipping_cost"]
    df["referral_fee"] = df["net_revenue"] * df["referral_pct"]
    df["fulfilment"] = q * df["fulfilment_fee"]
    df["platform_fee"] = _platform_fee(df, channel_fees)
    df["refund"] = df["returned_qty"] * (df["unit_price"] - df["discount"])
    df["return_shipping"] = np.where(df["returned_qty"] > 0, df["shipping_cost"], 0.0)

    df["net_margin"] = (df["net_revenue"] - df["cogs"] - df["outbound_shipping"]
                        - df["referral_fee"] - df["fulfilment"] - df["platform_fee"]
                        - df["refund"] - df["return_shipping"])

    # Stock that came back resellable. Not credited to margin yet.
    df["recoverable_stock"] = df["resellable_qty"] * df["cost_price"]
    return df


def _platform_fee(df: pd.DataFrame, channel_fees: pd.DataFrame) -> pd.Series:
    n_months = df["order_date"].dt.to_period("M").nunique()
    fixed_total = channel_fees.set_index("channel")["monthly_fixed"] * n_months
    channel_revenue = df.groupby("channel")["net_revenue"].transform("sum")
    return df["net_revenue"] / channel_revenue * df["channel"].map(fixed_total)


def margin_waterfall(enriched: pd.DataFrame) -> pd.DataFrame:
    rows = [(label, sign * enriched[col].sum()) for label, col, sign in WATERFALL_STEPS]
    rows.append(("Net margin", enriched["net_margin"].sum()))
    return pd.DataFrame(rows, columns=["step", "amount"]).round(2)


def sku_profitability(enriched: pd.DataFrame) -> pd.DataFrame:
    g = (enriched.groupby("canonical_sku")
         .agg(name=("name", "first"), category=("category", "first"),
              units=("quantity", "sum"),
              net_revenue=("net_revenue", "sum"),
              net_margin=("net_margin", "sum"))
         .reset_index())
    g["net_margin_pct"] = g["net_margin"] / g["net_revenue"]

    high_revenue = g["net_revenue"] >= g["net_revenue"].mean()
    healthy = g["net_margin_pct"] >= HEALTHY_MARGIN_PCT
    g["quadrant"] = np.select(
        [high_revenue & healthy, high_revenue & ~healthy, ~high_revenue & healthy],
        ["Volume drivers", "Hidden losers", "Quiet winners"],
        default="Dead weight")
    return g.sort_values("net_revenue", ascending=False).reset_index(drop=True).round(2)


def channel_comparison(enriched: pd.DataFrame) -> pd.DataFrame:
    g = (enriched.groupby(["canonical_sku", "channel"])
         .agg(name=("name", "first"),
              units=("quantity", "sum"),
              net_revenue=("net_revenue", "sum"),
              net_margin=("net_margin", "sum"))
         .reset_index())
    g["net_margin_pct"] = g["net_margin"] / g["net_revenue"]
    sold_on_several = g.groupby("canonical_sku")["channel"].transform("nunique") > 1
    return (g[sold_on_several]
            .sort_values(["name", "channel"]).reset_index(drop=True).round(2))


def returns_summary(enriched: pd.DataFrame, by) -> pd.DataFrame:
    g = (enriched.groupby(by)
         .agg(units_sold=("quantity", "sum"),
              units_returned=("returned_qty", "sum"),
              refund=("refund", "sum"),
              return_shipping=("return_shipping", "sum"),
              net_margin=("net_margin", "sum"),
              recoverable_stock=("recoverable_stock", "sum"))
         .reset_index())
    g["return_rate"] = g["units_returned"] / g["units_sold"]
    g["returns_cost"] = g["refund"] + g["return_shipping"]
    g["margin_before_returns"] = g["net_margin"] + g["returns_cost"]
    g["returns_flip_negative"] = (g["margin_before_returns"] > 0) & (g["net_margin"] < 0)
    return g.sort_values("returns_cost", ascending=False).reset_index(drop=True).round(2)


def returns_by_reason(enriched: pd.DataFrame, returns: pd.DataFrame) -> pd.DataFrame:
    lines = enriched[["order_id", "canonical_sku", "unit_price", "discount", "shipping_cost"]]
    events = returns.merge(lines, on=["order_id", "canonical_sku"], how="inner")
    events["refund"] = events["quantity"] * (events["unit_price"] - events["discount"])
    events["return_shipping"] = events["shipping_cost"]  # ~one parcel per event

    g = (events.groupby("reason")
         .agg(events=("return_id", "count"),
              units=("quantity", "sum"),
              refund=("refund", "sum"),
              return_shipping=("return_shipping", "sum"))
         .reset_index())
    g["returns_cost"] = g["refund"] + g["return_shipping"]
    return g.sort_values("returns_cost", ascending=False).reset_index(drop=True).round(2)


def headline_finding(enriched: pd.DataFrame) -> pd.DataFrame:
    """The loss-making bestseller: worst total margin among top-10 revenue
    SKUs, using only months whose return window has closed."""
    settled = enriched[~enriched["returns_provisional"]]
    years = _years_covered(settled)

    by_sku = (settled.groupby("canonical_sku")
              .agg(name=("name", "first"), category=("category", "first"),
                   units=("quantity", "sum"),
                   net_revenue=("net_revenue", "sum"),
                   net_margin=("net_margin", "sum"))
              .reset_index())
    by_sku["revenue_rank"] = by_sku["net_revenue"].rank(ascending=False).astype(int)

    candidates = by_sku[(by_sku["net_margin"] < 0) & (by_sku["revenue_rank"] <= 10)]
    worst = candidates.sort_values("net_margin").iloc[0]

    return pd.DataFrame([{
        "canonical_sku": worst["canonical_sku"],
        "name": worst["name"],
        "category": worst["category"],
        "revenue_rank": int(worst["revenue_rank"]),
        "annual_revenue_eur": round(worst["net_revenue"] / years),
        "annual_loss_eur": round(-worst["net_margin"] / years),
    }])


def _years_covered(df: pd.DataFrame) -> float:
    span = df["order_date"].max() - df["order_date"].min()
    return max(span.days, 1) / 365.25


def build_marts() -> dict[str, pd.DataFrame]:
    order_lines = pd.read_parquet(CLEAN_DIR / "order_lines.parquet")
    returns = pd.read_parquet(CLEAN_DIR / "returns.parquet")
    channel_fees = pd.read_parquet(CLEAN_DIR / "channel_fees.parquet")
    enriched = enrich(order_lines, channel_fees)

    marts = {
        "margin_waterfall": margin_waterfall(enriched),
        "sku_profitability": sku_profitability(enriched),
        "channel_comparison": channel_comparison(enriched),
        "returns_by_sku": returns_summary(enriched, ["canonical_sku", "name", "category"]),
        "returns_by_category": returns_summary(enriched, "category"),
        "returns_by_channel": returns_summary(enriched, "channel"),
        "returns_by_reason": returns_by_reason(enriched, returns),
        "headline": headline_finding(enriched),
    }
    MARTS_DIR.mkdir(parents=True, exist_ok=True)
    for name, df in marts.items():
        df.to_parquet(MARTS_DIR / f"{name}.parquet", index=False)
    return marts


def main() -> None:
    marts = build_marts()

    print(f"\nwritten to {MARTS_DIR}\n")
    print("=== margin waterfall ===")
    print(marts["margin_waterfall"].to_string(index=False))

    h = marts["headline"].iloc[0]
    print(f"\n=== headline finding ===")
    print(f"{h['name']} (rank {h['revenue_rank']} by revenue) loses about "
          f"EUR {h['annual_loss_eur']:,.0f} a year on EUR {h['annual_revenue_eur']:,.0f} of sales")

    print("\n=== SKUs where returns flip margin negative ===")
    flip = marts["returns_by_sku"]
    flip = flip[flip["returns_flip_negative"]][["name", "return_rate", "returns_cost", "net_margin"]]
    print(flip.to_string(index=False) if len(flip) else "(none)")


if __name__ == "__main__":
    main()
