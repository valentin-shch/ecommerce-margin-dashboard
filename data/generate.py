"""Synthetic data for Vella Home, a made-up home-and-kitchen brand.

24 months of orders, products and returns written to data/raw/ as CSV, left
deliberately messy. One seeded RNG, so a seed always gives the same files.

Run with:  python -m data.generate
"""

from __future__ import annotations

import calendar
import re
from datetime import date, timedelta

import numpy as np
import pandas as pd

from pipeline.config import AS_OF_DATE, RAW_DIR, SEED, VAT_RATE

N_PRODUCTS = 120
TARGET_ORDERS = 22_450  # tuned so total order lines land near 35k

CHANNELS = ["own_store", "amazon", "marketplace"]
CHANNEL_W = [0.32, 0.48, 0.20]  # Amazon carries the most volume

COUNTRIES = ["DE", "FR", "IT", "ES", "NL", "BE", "AT", "PL", "SE", "IE"]
COUNTRY_W = {
    "own_store":   [0.40, 0.10, 0.06, 0.05, 0.11, 0.07, 0.12, 0.02, 0.04, 0.03],
    "amazon":      [0.26, 0.19, 0.16, 0.15, 0.08, 0.05, 0.04, 0.03, 0.02, 0.02],
    "marketplace": [0.18, 0.30, 0.15, 0.16, 0.06, 0.09, 0.02, 0.02, 0.01, 0.01],
}

CATEGORIES = ["Cookware", "Bakeware", "Storage", "Drinkware",
              "Textiles", "Utensils", "Small Appliances", "Tableware"]
CATEGORY_W = [0.16, 0.10, 0.14, 0.13, 0.12, 0.11, 0.09, 0.15]

COST_RANGE = {
    "Cookware": (12, 38), "Bakeware": (4, 14), "Storage": (5, 18),
    "Drinkware": (3, 12), "Textiles": (3, 13), "Utensils": (2, 9),
    "Small Appliances": (14, 46), "Tableware": (8, 26),
}
WEIGHT_RANGE = {
    "Cookware": (0.9, 3.2), "Bakeware": (0.3, 1.1), "Storage": (0.4, 1.7),
    "Drinkware": (0.25, 1.4), "Textiles": (0.2, 0.8), "Utensils": (0.1, 0.55),
    "Small Appliances": (0.8, 2.8), "Tableware": (0.6, 2.6),
}

MATERIALS = ["Acacia", "Stoneware", "Cast Iron", "Bamboo", "Stainless Steel",
             "Ceramic", "Enamel", "Borosilicate", "Linen", "Copper", "Marble",
             "Terracotta", "Melamine", "Oak", "Slate"]
NOUNS = {
    "Cookware": ["Frying Pan", "Saucepan", "Stock Pot", "Saute Pan", "Grill Pan"],
    "Bakeware": ["Loaf Tin", "Muffin Tray", "Baking Sheet", "Cake Tin", "Tart Mould"],
    "Storage": ["Storage Jar", "Bread Bin", "Canister Set", "Pantry Box", "Nesting Bowls"],
    "Drinkware": ["Tumbler Set", "Wine Glasses", "Mug Set", "Carafe", "Water Bottle"],
    "Textiles": ["Tea Towel Set", "Oven Glove", "Apron", "Table Runner", "Placemat Set"],
    "Utensils": ["Turner", "Ladle", "Spatula Set", "Balloon Whisk", "Serving Spoon"],
    "Small Appliances": ["Hand Blender", "Milk Frother", "Electric Kettle",
                         "Food Chopper", "Coffee Grinder"],
    "Tableware": ["Dinner Plate Set", "Serving Board", "Salad Bowl",
                  "Pasta Bowl Set", "Platter"],
}

SUPPLIERS = ["Northwind Supply Co", "Aureli SRL", "Meridian Homeware",
             "Kestrel Trading Ltd", "Baltic & Byrne", "Lumen Goods"]

# SKUs that carry the story, keyed by popularity rank (0 = best seller). The
# loss makers look fine on price vs cost; fees, shipping and returns sink them.
FORCED = {
    0: dict(category="Utensils", name="Bamboo Kitchen Utensil Set",
            cost_price=2.60, weight_kg=0.34, markup=1.62, ret_mult=1.0),
    1: dict(category="Small Appliances", name="Stainless Steel Stand Mixer",
            cost_price=49.00, weight_kg=4.20, markup=1.50, ret_mult=2.3),
    2: dict(category="Cookware", name="Cast Iron Casserole 5L",
            cost_price=23.50, weight_kg=3.70, markup=1.85, ret_mult=2.0),
    3: dict(category="Storage", name="Glass Storage Jar Set of 6",
            cost_price=6.40, weight_kg=1.35, markup=1.60, ret_mult=1.0),
    5: dict(category="Tableware", name="Ceramic Dinner Set 12-Piece",
            cost_price=29.00, weight_kg=5.30, markup=2.00, ret_mult=2.1),
}
LOSS_MAKER_RANKS = [1, 2, 5]

SEASON = {1: 0.78, 2: 0.82, 3: 0.95, 4: 0.98, 5: 1.00, 6: 1.00,
          7: 1.06, 8: 0.96, 9: 1.02, 10: 1.28, 11: 1.90, 12: 1.68}
DISCOUNT_P = {1: 0.40, 7: 0.35, 11: 0.55, 12: 0.45}  # else 0.30

CH_PRICE_ADJ = {"own_store": 1.00, "amazon": 1.02, "marketplace": 0.985}

RETURN_BASE = {"own_store": 0.045, "amazon": 0.115, "marketplace": 0.065}
CATEGORY_RETURN_MULT = {
    "Cookware": 0.80, "Bakeware": 0.85, "Storage": 0.80, "Drinkware": 1.10,
    "Textiles": 1.25, "Utensils": 0.70, "Small Appliances": 1.50, "Tableware": 1.20,
}
REASONS = ["changed mind", "no longer needed", "not as described",
           "arrived damaged", "quality issue", "wrong item"]
REASON_P = [0.34, 0.15, 0.18, 0.12, 0.12, 0.09]
CONDITIONS = ["resellable", "opened", "damaged"]
CONDITION_P = {
    "changed mind":    [0.70, 0.25, 0.05],
    "no longer needed": [0.75, 0.20, 0.05],
    "not as described": [0.45, 0.40, 0.15],
    "arrived damaged": [0.05, 0.15, 0.80],
    "quality issue":   [0.10, 0.35, 0.55],
    "wrong item":      [0.60, 0.30, 0.10],
}

SHIP_BASE = {"0-0.5": 3.20, "0.5-1": 4.40, "1-2": 6.10, "2-5": 9.20, "5+": 13.50}
SHIP_COUNTRY_FACTOR = {
    "DE": 1.00, "NL": 1.00, "BE": 1.03, "FR": 1.08, "AT": 1.06,
    "IT": 1.15, "ES": 1.14, "PL": 1.20, "SE": 1.28, "IE": 1.30,
}
EXPRESS_MULT = 1.85


def month_starts() -> list[date]:
    """First-of-month dates for the 24 full months before the AS_OF_DATE month."""
    y, m = AS_OF_DATE.year, AS_OF_DATE.month
    out = []
    for _ in range(24):
        m -= 1
        if m == 0:
            y, m = y - 1, 12
        out.append(date(y, m, 1))
    return list(reversed(out))


def build_products(rng) -> pd.DataFrame:
    # Heavy-tailed popularity: a few SKUs do most of the volume. Clip the tail
    # so none of them runs away completely.
    pop = rng.pareto(1.8, N_PRODUCTS) + 1.0
    pop = np.minimum(pop, 5.0 * np.median(pop))
    rank_to_idx = np.argsort(-pop)

    used_names: set[str] = set()
    rows = []
    for idx in range(N_PRODUCTS):
        category = rng.choice(CATEGORIES, p=CATEGORY_W)
        name = _unique_name(rng, category, used_names)
        cost = round(float(rng.uniform(*COST_RANGE[category])), 2)
        weight = round(float(rng.uniform(*WEIGHT_RANGE[category])), 2)
        markup = float(rng.uniform(2.3, 3.7))
        rows.append(dict(idx=idx, sku=f"VH-{1000 + idx}", name=name,
                         category=category, cost_price=cost, weight_kg=weight,
                         supplier=rng.choice(SUPPLIERS),
                         launch_date=_launch_date(rng), markup=markup,
                         ret_mult=1.0))

    for rank in range(N_PRODUCTS):
        idx = int(rank_to_idx[rank])
        spec = FORCED.get(rank)
        if spec is None:
            continue
        row = rows[idx]
        row.update(name=spec["name"], category=spec["category"],
                   cost_price=spec["cost_price"], weight_kg=spec["weight_kg"],
                   markup=spec["markup"], ret_mult=spec["ret_mult"])

    # Thin margin on the second and fourth best sellers that aren't forced losers.
    for rank in (4, 6):
        rows[int(rank_to_idx[rank])]["markup"] = float(rng.uniform(1.55, 1.72))

    # A scattering of extra return-prone SKUs beyond the forced ones.
    for idx in rng.choice(rank_to_idx[10:], size=8, replace=False):
        rows[int(idx)]["ret_mult"] = float(rng.uniform(1.3, 1.6))

    df = pd.DataFrame(rows)

    # Price is set while every SKU still has a cost, then ~3% have their cost
    # blanked to mimic a gap in the product system. The business still sells
    # them, so order prices stay realistic; only the reported cost, and hence
    # their margin, goes missing.
    df["net_price"] = (df["cost_price"] * df["markup"]).round(2)
    missing = rng.choice(rank_to_idx[35:], size=4, replace=False)
    df.loc[df["idx"].isin(missing), "cost_price"] = np.nan
    df["popularity"] = pop
    df["is_loss_maker"] = df["idx"].isin(rank_to_idx[LOSS_MAKER_RANKS])
    df["asin"] = [_asin(rng) for _ in range(N_PRODUCTS)]
    df["mp_variants"] = [_marketplace_variants(rng, n) for n in df["name"]]
    return df


def _unique_name(rng, category: str, used: set[str]) -> str:
    for _ in range(50):
        name = f"{rng.choice(MATERIALS)} {rng.choice(NOUNS[category])}"
        if name not in used:
            used.add(name)
            return name
    name = f"{name} #{len(used)}"
    used.add(name)
    return name


def _launch_date(rng) -> date:
    if rng.random() < 0.70:
        start, span = date(2019, 1, 1), (date(2024, 8, 15) - date(2019, 1, 1)).days
    else:
        start, span = date(2024, 9, 1), (date(2026, 5, 15) - date(2024, 9, 1)).days
    return start + timedelta(days=int(rng.integers(0, span)))


def _asin(rng) -> str:
    alphabet = np.array(list("ABCDEFGHJKLMNPQRSTUVWXYZ0123456789"))
    return "B0" + "".join(rng.choice(alphabet, size=8))


def _marketplace_variants(rng, name: str) -> list[str]:
    base = re.sub(r"[^a-z0-9]+", " ", name.lower()).strip()
    styles = [
        base.replace(" ", "-"),
        "vh " + base,
        base.replace(" ", "_"),
        _drop_a_char(rng, base),
        "".join(w[:4] for w in base.split()),
    ]
    variants = [styles[int(rng.integers(0, len(styles)))]]
    if rng.random() < 0.15:
        variants.append(styles[int(rng.integers(0, len(styles)))])
    return list(dict.fromkeys(variants))


def _drop_a_char(rng, s: str) -> str:
    letters = [i for i, c in enumerate(s) if c.isalpha()]
    if len(letters) < 6:
        return s
    i = int(rng.choice(letters[2:-2]))
    return s[:i] + s[i + 1:]


def _native_sku(rng, product: pd.Series, channel: str) -> str:
    if channel == "own_store":
        return product["sku"]
    if channel == "amazon":
        return product["asin"]
    variants = product["mp_variants"]
    text = variants[1] if len(variants) > 1 and rng.random() < 0.25 else variants[0]
    lead = " " * int(rng.integers(0, 2))
    trail = " " * int(rng.integers(1, 3))
    return f"{lead}{text}{trail}"


def build_channel_fees() -> pd.DataFrame:
    # fulfilment_fee is per unit. own_store's 2.9% is really card processing.
    return pd.DataFrame([
        dict(channel="own_store", referral_pct=0.029, fulfilment_fee=1.25, monthly_fixed=220.0),
        dict(channel="amazon", referral_pct=0.150, fulfilment_fee=3.90, monthly_fixed=39.0),
        dict(channel="marketplace", referral_pct=0.110, fulfilment_fee=2.70, monthly_fixed=19.0),
    ])


def build_shipping() -> pd.DataFrame:
    rows = []
    for band, base in SHIP_BASE.items():
        for country, factor in SHIP_COUNTRY_FACTOR.items():
            for method, mult in (("standard", 1.0), ("express", EXPRESS_MULT)):
                rows.append(dict(weight_band=band, country=country,
                                 shipping_method=method,
                                 cost=round(base * factor * mult, 2)))
    return pd.DataFrame(rows)


def build_orders_and_returns(rng, products: pd.DataFrame):
    months = month_starts()
    weights = np.array([SEASON[d.month] for d in months]) * np.linspace(0.90, 1.18, 24)
    orders_per_month = np.round(TARGET_ORDERS * weights / weights.sum()).astype(int)

    launch = products["launch_date"].to_numpy(dtype="datetime64[D]")
    pop = products["popularity"].to_numpy()
    loss_idx = products.index[products["is_loss_maker"]].to_numpy()
    net_price = products["net_price"].to_numpy()
    ret_mult = products["ret_mult"].to_numpy()
    category = products["category"].to_numpy()

    customers = np.array([f"VH-C{100000 + i}" for i in range(9000)])

    order_rows, return_rows = [], []
    oid = rid = 0
    for mi, first in enumerate(months):
        dim = calendar.monthrange(first.year, first.month)[1]
        for _ in range(int(orders_per_month[mi])):
            oid += 1
            order_id = f"ORD-{oid:06d}"
            channel = str(rng.choice(CHANNELS, p=CHANNEL_W))
            order_date = date(first.year, first.month, _day_of_month(rng, first.month, dim))
            country = str(rng.choice(COUNTRIES, p=COUNTRY_W[channel]))
            express_p = 0.30 if first.month in (11, 12) else 0.20
            method = "express" if rng.random() < express_p else "standard"
            customer = customers[min(8999, int(rng.beta(0.7, 2.5) * 9000))]

            eligible = pop * (launch <= np.datetime64(order_date))
            if channel == "amazon":
                eligible = eligible.copy()
                eligible[loss_idx] *= 2.5
            eligible = eligible / eligible.sum()

            n_lines = int(rng.choice([1, 2, 3, 4], p=[0.62, 0.24, 0.10, 0.04]))
            n_lines = min(n_lines, int((eligible > 0).sum()))
            picks = rng.choice(N_PRODUCTS, size=n_lines, replace=False, p=eligible)

            for pi in picks:
                product = products.iloc[int(pi)]
                qty = int(rng.choice([1, 2, 3, 4], p=[0.74, 0.18, 0.06, 0.02]))
                net = net_price[pi] * float(np.clip(rng.normal(1.0, 0.03), 0.90, 1.12))
                net *= CH_PRICE_ADJ[channel]
                price = net * (1 + VAT_RATE) if channel == "own_store" else net

                discount = 0.0
                if rng.random() < DISCOUNT_P.get(first.month, 0.30):
                    pct = rng.uniform(0.05, 0.45 if first.month == 11 else 0.30)
                    discount = price * pct
                if rng.random() < 0.003:
                    discount = price * rng.uniform(1.05, 1.90)  # genuine data error

                native = _native_sku(rng, product, channel)
                order_rows.append((order_id, order_date.isoformat(), channel, native,
                                   qty, round(price, 2), round(discount, 2),
                                   customer, country, method))

                rate = min(0.60, RETURN_BASE[channel]
                           * CATEGORY_RETURN_MULT[category[pi]] * ret_mult[pi])
                if rng.random() < rate:
                    rq = _return_qty(rng, qty)
                    lag = int(np.clip(round(rng.gamma(2.2, 9.0)), 1, 60))
                    return_date = order_date + timedelta(days=lag)
                    if return_date <= AS_OF_DATE:  # later returns aren't observed yet
                        rid += 1
                        reason = str(rng.choice(REASONS, p=REASON_P))
                        condition = str(rng.choice(CONDITIONS, p=CONDITION_P[reason]))
                        return_rows.append((f"RET-{rid:06d}", order_id, native, rq,
                                            return_date.isoformat(), reason, condition))

    orders = pd.DataFrame(order_rows, columns=[
        "order_id", "order_date", "channel", "sku", "quantity", "unit_price",
        "discount", "customer_id", "country", "shipping_method"])
    returns = pd.DataFrame(return_rows, columns=[
        "return_id", "order_id", "sku", "quantity", "return_date", "reason",
        "condition_on_return"])
    return orders, returns


def _day_of_month(rng, month: int, dim: int) -> int:
    if month == 11 and rng.random() < 0.22:
        return int(rng.integers(24, 30))  # Black Friday week
    if month in (11, 12):
        return int(np.clip(rng.beta(1.7, 2.3) * dim, 0, dim - 1)) + 1
    return int(rng.integers(1, dim + 1))


def _return_qty(rng, qty: int) -> int:
    if qty == 1:
        return 1
    return int(min(qty, rng.choice([1, qty, max(1, qty // 2)], p=[0.6, 0.3, 0.1])))


def build_sku_mapping(rng, products: pd.DataFrame):
    rows = []
    for _, p in products.iterrows():
        rows.append(("own_store", p["sku"], p["sku"]))
        rows.append(("amazon", p["asin"], p["sku"]))
        for v in p["mp_variants"]:
            rows.append(("marketplace", v.strip().lower(), p["sku"]))

    mapping = pd.DataFrame(rows, columns=["channel", "channel_sku", "sku"])
    mapping = mapping.drop_duplicates(subset=["channel", "channel_sku"])

    # Drop ~10% of non-own-store rows so some codes don't map. Keep the top
    # sellers mapped so the gap is a nuisance, not a hole in the headline.
    top_skus = set(products.nlargest(12, "popularity")["sku"])
    droppable = mapping[(mapping["channel"] != "own_store")
                        & (~mapping["sku"].isin(top_skus))]
    n_drop = int(round(0.10 * (mapping["channel"] != "own_store").sum()))
    drop_idx = rng.choice(droppable.index.to_numpy(), size=n_drop, replace=False)
    return mapping.drop(index=drop_idx).reset_index(drop=True)


def _normalise(s: pd.Series) -> pd.Series:
    return s.str.strip().str.lower().str.replace(r"\s+", " ", regex=True)


def write_all(rng) -> dict[str, pd.DataFrame]:
    products = build_products(rng)
    orders, returns = build_orders_and_returns(rng, products)
    mapping = build_sku_mapping(rng, products)

    products_out = products[["sku", "name", "category", "cost_price",
                             "weight_kg", "supplier", "launch_date"]].copy()
    products_out["launch_date"] = products_out["launch_date"].astype(str)

    files = {
        "products.csv": products_out,
        "orders.csv": orders,
        "returns.csv": returns,
        "shipping.csv": build_shipping(),
        "channel_fees.csv": build_channel_fees(),
        "sku_mapping.csv": mapping,
    }
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    for name, df in files.items():
        df.to_csv(RAW_DIR / name, index=False)

    files["_products_full"] = products
    return files


def report(files: dict[str, pd.DataFrame]) -> None:
    orders = files["orders.csv"]
    returns = files["returns.csv"]
    products = files["_products_full"]
    mapping = files["sku_mapping.csv"]

    print(f"\nwritten to {RAW_DIR}\n")
    for name in ["products.csv", "orders.csv", "returns.csv", "shipping.csv",
                 "channel_fees.csv", "sku_mapping.csv"]:
        df = files[name]
        print(f"--- {name}  ({len(df):,} rows, {len(df.columns)} cols)")
        print(df.head().to_string(index=False))
        print()

    print("=== cross-checks ===")
    print(f"order lines .............. {len(orders):,}")
    print(f"distinct orders .......... {orders['order_id'].nunique():,}")
    print(f"distinct customers ....... {orders['customer_id'].nunique():,}")
    print(f"date range .............. {orders['order_date'].min()} .. {orders['order_date'].max()}")
    print(f"as-of date .............. {AS_OF_DATE}")
    print("\nchannel mix (lines):")
    print(orders["channel"].value_counts(normalize=True).round(3).to_string())

    units = orders.assign(units=orders["quantity"]).groupby("channel")["units"].sum()
    ret_units = (returns.merge(orders[["order_id", "sku", "channel"]].drop_duplicates(),
                               on=["order_id", "sku"], how="left")
                 .groupby("channel")["quantity"].sum())
    print("\nreturn rate by channel (returned units / sold units):")
    print((ret_units / units).round(3).to_string())

    lag = (pd.to_datetime(returns["return_date"]).dt.normalize()
           - pd.to_datetime(returns.merge(orders[["order_id"]].assign(
               od=orders["order_date"]).drop_duplicates(), on="order_id")["od"]))
    print(f"\nreturn lag days: min {lag.dt.days.min()}, "
          f"median {int(lag.dt.days.median())}, max {lag.dt.days.max()}")

    om = orders.assign(ym=orders["order_date"].str[:7])
    sold_by_month = om.groupby("ym")["quantity"].sum()
    ret_by_month = (returns.merge(om[["order_id", "ym"]].drop_duplicates(), on="order_id")
                    .groupby("ym")["quantity"].sum())
    rate_by_month = (ret_by_month / sold_by_month).round(3)
    print("\nreturn rate by order month (last 4 sit below trend, returns still arriving):")
    print(rate_by_month.tail(4).to_string())

    native = _normalise(orders["sku"])
    mapped_keys = set(zip(mapping["channel"], _normalise(mapping["channel_sku"])))
    is_mapped = [(c, s) in mapped_keys for c, s in zip(orders["channel"], native)]
    gross = orders["quantity"] * orders["unit_price"]
    print(f"\nSKU mapping coverage: {np.mean(is_mapped):.1%} of lines, "
          f"{gross[is_mapped].sum() / gross.sum():.1%} of gross value")

    bad = (orders["discount"] > orders["unit_price"]).sum()
    print(f"lines with discount > unit_price (injected error): {bad}")

    missing_cost = products["cost_price"].isna().sum()
    print(f"SKUs with missing cost_price: {missing_cost} of {len(products)}")

    print("\n(for reference, not visible in the raw data) designed loss makers:")
    print(products.loc[products["is_loss_maker"], ["sku", "name", "category"]]
          .to_string(index=False))


def main() -> None:
    rng = np.random.default_rng(SEED)
    files = write_all(rng)
    report(files)


if __name__ == "__main__":
    main()
