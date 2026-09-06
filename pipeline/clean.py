"""Raw CSV -> clean parquet: resolve SKUs, fix VAT and discount errors, attach
returns to their order line without duplicating revenue.

Joins and hygiene only, no margin math (that's metrics.py). Data-quality
issues are flagged on the row, never dropped or imputed.

Run with:  python -m pipeline.clean
"""

from __future__ import annotations

from datetime import timedelta

import numpy as np
import pandas as pd

from pipeline.config import AS_OF_DATE, CLEAN_DIR, RAW_DIR, RETURN_WINDOW_DAYS, VAT_RATE

WEIGHT_BANDS = [(0.5, "0-0.5"), (1.0, "0.5-1"), (2.0, "1-2"), (5.0, "2-5")]


def weight_band(w: float) -> str | None:
    if pd.isna(w):
        return None
    for limit, label in WEIGHT_BANDS:
        if w <= limit:
            return label
    return "5+"


def _normalise(s: pd.Series) -> pd.Series:
    return s.astype(str).str.strip().str.lower().str.replace(r"\s+", " ", regex=True)


def load_raw() -> dict[str, pd.DataFrame]:
    return {
        "orders": pd.read_csv(RAW_DIR / "orders.csv", parse_dates=["order_date"]),
        "products": pd.read_csv(RAW_DIR / "products.csv", parse_dates=["launch_date"]),
        "returns": pd.read_csv(RAW_DIR / "returns.csv", parse_dates=["return_date"]),
        "shipping": pd.read_csv(RAW_DIR / "shipping.csv"),
        "channel_fees": pd.read_csv(RAW_DIR / "channel_fees.csv"),
        "sku_mapping": pd.read_csv(RAW_DIR / "sku_mapping.csv"),
    }


def resolve_sku(df: pd.DataFrame, mapping: pd.DataFrame, sku_col: str) -> pd.DataFrame:
    """Attach the canonical SKU. No match -> canonical_sku null, unmapped=True."""
    lookup = (mapping.assign(_key=_normalise(mapping["channel_sku"]))
              [["channel", "_key", "sku"]]
              .drop_duplicates(["channel", "_key"])
              .rename(columns={"sku": "canonical_sku"}))
    out = df.assign(_key=_normalise(df[sku_col])).merge(lookup, on=["channel", "_key"], how="left")
    out["unmapped"] = out["canonical_sku"].isna()
    return out.drop(columns="_key")


def clean_returns(raw: dict[str, pd.DataFrame]) -> pd.DataFrame:
    """One row per return event, with channel and canonical SKU attached.
    Feeds the Returns page; the line-grain summary lives on order_lines."""
    order_channel = raw["orders"][["order_id", "channel"]].drop_duplicates()
    returns = raw["returns"].merge(order_channel, on="order_id", how="left")
    returns = resolve_sku(returns, raw["sku_mapping"], sku_col="sku")
    return returns.merge(
        raw["products"][["sku", "category"]].rename(columns={"sku": "canonical_sku"}),
        on="canonical_sku", how="left")


def clean_order_lines(raw: dict[str, pd.DataFrame], returns: pd.DataFrame) -> pd.DataFrame:
    orders = resolve_sku(raw["orders"], raw["sku_mapping"], sku_col="sku")

    # order_id + native code is unique per line, so joining returns on it can't
    # fan out the table.
    orders["line_key"] = orders["order_id"] + "||" + _normalise(orders["sku"])
    returns = returns.assign(line_key=returns["order_id"] + "||" + _normalise(returns["sku"]))
    returns = returns.assign(
        resellable_units=np.where(returns["condition_on_return"] == "resellable",
                                  returns["quantity"], 0))
    returns_by_line = returns.groupby("line_key", as_index=False).agg(
        returned_qty=("quantity", "sum"),
        resellable_qty=("resellable_units", "sum"),
        return_events=("return_id", "count"),
        last_return_date=("return_date", "max"),
    )

    n_before = len(orders)
    orders = orders.merge(returns_by_line, on="line_key", how="left")
    assert len(orders) == n_before, "returns join changed row count, grain violation"
    orders[["returned_qty", "resellable_qty", "return_events"]] = (
        orders[["returned_qty", "resellable_qty", "return_events"]].fillna(0).astype(int))

    orders["return_qty_error"] = orders["returned_qty"] > orders["quantity"]
    orders["returned_qty"] = orders[["returned_qty", "quantity"]].min(axis=1)
    orders["resellable_qty"] = orders[["resellable_qty", "returned_qty"]].min(axis=1)

    # Own-store prices come in VAT-inclusive; strip to net so channels match.
    is_own_store = orders["channel"] == "own_store"
    orders.loc[is_own_store, "unit_price"] = (orders.loc[is_own_store, "unit_price"] / (1 + VAT_RATE)).round(2)
    orders.loc[is_own_store, "discount"] = (orders.loc[is_own_store, "discount"] / (1 + VAT_RATE)).round(2)

    orders["discount_error"] = orders["discount"] > orders["unit_price"]
    orders["discount"] = orders[["discount", "unit_price"]].min(axis=1)

    orders = orders.merge(
        raw["products"][["sku", "name", "category", "cost_price", "weight_kg"]]
        .rename(columns={"sku": "canonical_sku"}),
        on="canonical_sku", how="left")
    orders["cost_missing_reason"] = np.select(
        [orders["unmapped"], orders["cost_price"].isna()],
        ["unmapped_sku", "no_cost_recorded"], default=None)

    orders["weight_band"] = orders["weight_kg"].apply(weight_band)
    orders = orders.merge(raw["shipping"], on=["weight_band", "country", "shipping_method"], how="left")
    orders = orders.rename(columns={"cost": "shipping_cost"})

    orders = orders.merge(raw["channel_fees"][["channel", "referral_pct", "fulfilment_fee"]],
                          on="channel", how="left")

    cutoff = pd.Timestamp(AS_OF_DATE) - timedelta(days=RETURN_WINDOW_DAYS)
    orders["returns_provisional"] = orders["order_date"] > cutoff

    return orders.drop(columns=["line_key"])


def data_quality_summary(order_lines: pd.DataFrame, raw: dict[str, pd.DataFrame]) -> pd.DataFrame:
    revenue = order_lines["quantity"] * order_lines["unit_price"]
    unmapped_rev = revenue[order_lines["unmapped"]].sum()
    missing_cost_rev = revenue[order_lines["cost_price"].isna()].sum()
    provisional_months = sorted(order_lines.loc[order_lines["returns_provisional"], "order_date"]
                                .dt.strftime("%Y-%m").unique())

    rows = [
        ("order lines", f"{len(order_lines):,}"),
        ("date range", f"{order_lines['order_date'].min():%Y-%m-%d} to "
                       f"{order_lines['order_date'].max():%Y-%m-%d}"),
        ("as-of date", f"{AS_OF_DATE:%Y-%m-%d}"),
        ("unmapped channel SKUs", f"{order_lines['unmapped'].sum():,} lines "
                                  f"({order_lines['unmapped'].mean():.1%}), "
                                  f"EUR {unmapped_rev:,.0f} revenue can't be attributed to a product"),
        ("missing cost price", f"{order_lines['cost_price'].isna().sum():,} lines "
                               f"({order_lines['cost_price'].isna().mean():.1%}), "
                               f"EUR {missing_cost_rev:,.0f} revenue with unknown margin"),
        ("  of which: SKU has no cost on file",
         f"{(order_lines['cost_missing_reason'] == 'no_cost_recorded').sum():,} lines"),
        ("  of which: SKU could not be mapped",
         f"{(order_lines['cost_missing_reason'] == 'unmapped_sku').sum():,} lines"),
        ("discount exceeded price (data error, clipped)", f"{order_lines['discount_error'].sum():,} lines"),
        ("returned qty exceeded ordered qty (data error, clipped)",
         f"{order_lines['return_qty_error'].sum():,} lines"),
        ("VAT-adjusted (own store)", f"{(order_lines['channel'] == 'own_store').sum():,} lines"),
        ("return events", f"{len(raw['returns']):,}"),
        ("units returned", f"{order_lines['returned_qty'].sum():,}"),
        ("provisional months (return window still open)", ", ".join(provisional_months)),
        ("order lines in provisional months",
         f"{order_lines['returns_provisional'].sum():,} lines, margin still moving as returns arrive"),
    ]
    return pd.DataFrame(rows, columns=["metric", "value"])


def run() -> dict[str, pd.DataFrame]:
    raw = load_raw()
    returns = clean_returns(raw)
    order_lines = clean_order_lines(raw, returns)
    products = raw["products"].assign(missing_cost=raw["products"]["cost_price"].isna())
    dq = data_quality_summary(order_lines, raw)

    CLEAN_DIR.mkdir(parents=True, exist_ok=True)
    order_lines.to_parquet(CLEAN_DIR / "order_lines.parquet", index=False)
    returns.to_parquet(CLEAN_DIR / "returns.parquet", index=False)
    products.to_parquet(CLEAN_DIR / "products.parquet", index=False)
    raw["shipping"].to_parquet(CLEAN_DIR / "shipping.parquet", index=False)
    raw["channel_fees"].to_parquet(CLEAN_DIR / "channel_fees.parquet", index=False)
    dq.to_parquet(CLEAN_DIR / "dq_summary.parquet", index=False)

    return {"order_lines": order_lines, "returns": returns, "products": products, "dq_summary": dq}


def main() -> None:
    result = run()
    order_lines = result["order_lines"]

    print(f"\nwritten to {CLEAN_DIR}\n")
    print(f"order_lines: {len(order_lines):,} rows, {len(order_lines.columns)} cols")
    print(order_lines.head(3).to_string(index=False))

    print("\n=== data quality summary ===")
    for metric, value in result["dq_summary"].itertuples(index=False):
        print(f"{metric}: {value}")


if __name__ == "__main__":
    main()
