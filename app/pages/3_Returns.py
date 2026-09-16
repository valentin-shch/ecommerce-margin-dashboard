"""Returns: what they cost in euros, and which products they flip unprofitable."""

import plotly.graph_objects as go
import streamlit as st

from loaders import load_clean, load_mart
from ui import PLOTLY_CONFIG, configure_page, fmt_eur_compact

configure_page("Returns", "What do returns actually cost, and where?")

order_lines = load_clean("order_lines")
no_cost_share = order_lines["cost_price"].isna().mean()

st.caption(
    "Totals over the full 24 months, including the still-provisional last two "
    "(returns are charged back to the month of the original sale, not the month "
    f"they arrive - see Overview for why). Excludes the {no_cost_share:.1%} of order "
    "lines with no usable cost, same as Overview and SKU profitability - see Data engineering."
)

by_channel = load_mart("returns_by_channel")
by_sku = load_mart("returns_by_sku")

total_cost = by_channel["returns_cost"].sum()
total_rate = by_channel["units_returned"].sum() / by_channel["units_sold"].sum()

k1, k2 = st.columns(2)
k1.metric("Cost of returns", fmt_eur_compact(total_cost))
k2.metric("Return rate", f"{total_rate:.1%}")

flips = by_sku[by_sku["returns_flip_negative"]].sort_values("contribution_margin")
n = len(flips)

st.markdown("##### Where returns flip margin negative")
if n:
    worst = flips.iloc[0]
    subject = "1 product's" if n == 1 else f"{n} products'"
    # Independently rounding "before" and "cost" to the nearest €1K, then also
    # independently rounding their (precise) difference, doesn't guarantee the
    # three add up - same lesson as the Overview waterfall. Deriving the loss
    # from the two rounded figures already on screen keeps it hand-checkable.
    before_k = round(worst["margin_before_returns"] / 1000)
    cost_k = round(worst["returns_cost"] / 1000)
    loss_display = fmt_eur_compact((before_k - cost_k) * 1000)
    with st.container(border=True):
        st.markdown(
            f"Returns flip {subject} margin negative this period. The biggest: "
            f"**{worst['name']}** was profitable "
            f"({fmt_eur_compact(worst['margin_before_returns'])}) before returns; a "
            f"{worst['return_rate']:.0%} return rate costs {fmt_eur_compact(worst['returns_cost'])}, "
            f"more than wiping it out and flipping it to a {loss_display} loss (24 months)."
        )
        # Even 3 columns ran off the right edge at 390px with the last one
        # invisible and no scroll cue - every row here is already margin-negative
        # by definition, so the euro cost (with rate folded in) tells the story
        # on its own without needing a separate margin column too.
        table = flips[["name"]].copy()
        table["returns_cost"] = [f"{fmt_eur_compact(c)} ({r:.0%} rate)"
                                 for c, r in zip(flips["returns_cost"], flips["return_rate"])]
        table.columns = ["Product", "Returns cost"]
        st.dataframe(table, hide_index=True, use_container_width=True)
else:
    st.caption("No product's margin flips negative because of returns this period.")

st.markdown("##### Return cost by")
dim = st.radio("Break down by", ["Category", "Channel", "Reason", "SKU"],
               horizontal=True, label_visibility="collapsed")

CHANNEL_AXIS_LABELS = {"own_store": "Own store", "amazon": "Amazon", "marketplace": "Marketplace"}
SKU_CHART_LIMIT = 8  # 116 SKUs won't fit a bar chart - top N by cost, same idea as the category cut

if dim == "SKU":
    d = by_sku.nlargest(SKU_CHART_LIMIT, "returns_cost").sort_values("returns_cost")
    labels = d["name"]
    sublabels = [f"{r:.0%} return rate" for r in d["return_rate"]]
    st.caption(f"Top {SKU_CHART_LIMIT} products by returns cost, not filtered to "
              "negative margin like the table above.")
elif dim == "Category":
    d = load_mart("returns_by_category").sort_values("returns_cost")
    labels = d["category"]
    sublabels = [f"{r:.0%} return rate" for r in d["return_rate"]]

    # A category's rate can be one bad SKU dragging the average up rather than
    # a category-wide pattern - flag it when that's what's actually happening.
    worst_cat = d.loc[d["return_rate"].idxmax()]
    cat_skus = by_sku[by_sku["category"] == worst_cat["category"]]
    top_sku = cat_skus.loc[cat_skus["units_returned"].idxmax()]
    concentration = top_sku["units_returned"] / cat_skus["units_returned"].sum()
    rest = cat_skus.drop(top_sku.name)
    rate_without_top = rest["units_returned"].sum() / rest["units_sold"].sum()
    if concentration > 0.4 and worst_cat["return_rate"] > total_rate * 1.5:
        st.caption(
            f"{worst_cat['category']}'s {worst_cat['return_rate']:.0%} rate is mostly one "
            f"product: **{top_sku['name']}** alone is {concentration:.0%} of the category's "
            f"returned units. Without it, {worst_cat['category']} runs {rate_without_top:.1%} - "
            f"close to the {total_rate:.1%} overall rate."
        )
elif dim == "Channel":
    d = load_mart("returns_by_channel").sort_values("returns_cost")
    labels = d["channel"].map(CHANNEL_AXIS_LABELS)
    sublabels = [f"{r:.0%} return rate" for r in d["return_rate"]]
else:
    d = load_mart("returns_by_reason").sort_values("returns_cost")
    share = d["units"] / d["units"].sum()
    labels = d["reason"].str.capitalize()
    sublabels = [f"{s:.0%} of returns" for s in share]

fig = go.Figure(go.Bar(
    orientation="h", y=labels, x=d["returns_cost"],
    marker=dict(color="#e34948"),
    hovertext=[f"{lab}: {fmt_eur_compact(c)}, {sub}"
              for lab, c, sub in zip(labels, d["returns_cost"], sublabels)],
    hoverinfo="text",
))
# Plotly's native y-axis tick labels clipped the odd long product name by a
# character - a left-hand paper-anchored annotation column can't be clipped
# by axis margin math, same fix as the right-hand value column below.
for label, cost, sub in zip(labels, d["returns_cost"], sublabels):
    fig.add_annotation(x=0.0, xref="paper", xanchor="right", xshift=-10,
                       y=label, yref="y", showarrow=False, align="right",
                       text=str(label), font=dict(size=15, color="#52514e"))
    fig.add_annotation(x=1.0, xref="paper", xanchor="left", xshift=10,
                       y=label, yref="y", showarrow=False, align="left",
                       text=f"{fmt_eur_compact(cost)}<br><span style='font-size:12px'>{sub}</span>",
                       font=dict(size=15, color="#52514e"))
fig.update_xaxes(showticklabels=False, range=[0, d["returns_cost"].max() * 1.05])
fig.update_yaxes(showticklabels=False)
left_margin = min(220, 24 + 7 * max(len(str(l)) for l in labels))
fig.update_layout(
    height=max(220, 90 + 55 * len(d)),
    margin=dict(l=left_margin, r=130, t=10, b=10),
    font=dict(size=15),
    bargap=0.3,
)
st.plotly_chart(fig, use_container_width=True, config=PLOTLY_CONFIG, theme="streamlit")
st.caption(
    "The % beside each bar is a return rate, except for Reason and the callout "
    "above, which show a share of returns instead - same-looking number, different question."
)

l1, l2 = st.columns(2)
l1.page_link("pages/2_SKU_profitability.py", label="← SKU profitability")
l2.page_link("pages/4_Channel_comparison.py", label="Channel comparison →")
