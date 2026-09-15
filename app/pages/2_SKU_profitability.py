"""SKU profitability: revenue vs margin, and which products actually lose money."""

import plotly.graph_objects as go
import streamlit as st

from loaders import load_mart
from pipeline.metrics import HEALTHY_MARGIN_PCT
from ui import PLOTLY_CONFIG, configure_page, fmt_eur, fmt_eur_compact

configure_page("SKU profitability", "Which products actually make money?")

st.caption(
    "Each point is one product, totalled over all 24 months including the "
    "still-provisional ones (the Overview's per-year figures use only settled "
    "months, so don't expect this page's totals to divide evenly into those). "
    "Revenue across (log scale, since a few products sell far more than most), "
    "contribution margin up. Products with no recorded cost aren't shown - "
    "see Data quality."
)

sku = load_mart("sku_profitability")
revenue_threshold = sku["net_revenue"].mean()

QUADRANT_STYLE = {
    "Volume drivers": dict(color="#2a78d6", symbol="circle"),
    "Hidden losers": dict(color="#e34948", symbol="x"),
    "Quiet winners": dict(color="#1baf7a", symbol="triangle-up"),
    "Dead weight": dict(color="#4a3aa7", symbol="square"),
}
def describe(row) -> str:
    """The quadrant is revenue vs the 10% healthy-margin bar, not vs zero -
    a couple of "Hidden losers" are thin but not actually negative, so the
    blurb has to check the real sign rather than assume the quadrant name."""
    negative = row["contribution_margin"] < 0
    quadrant = row["quadrant"]
    if quadrant == "Volume drivers":
        return "High revenue, healthy margin - the backbone of the business."
    if quadrant == "Hidden losers":
        return ("High revenue, and it's actually losing money - fix the economics or drop it."
                if negative else
                "High revenue, but margin is far thinner than a top seller's should be.")
    if quadrant == "Quiet winners":
        return "Lower revenue, healthy margin - a candidate to push harder."
    return ("Lower revenue, and it's losing money - a real candidate to cut."
            if negative else
            "Lower revenue, thin margin - not a priority either way.")

fig = go.Figure()
for quadrant, style in QUADRANT_STYLE.items():
    d = sku[sku["quadrant"] == quadrant]
    fig.add_trace(go.Scatter(
        x=d["net_revenue"], y=d["contribution_margin_pct"] * 100,
        mode="markers", name=quadrant,
        marker=dict(color=style["color"], symbol=style["symbol"], size=11,
                   line=dict(width=1, color="#fcfcfb")),
        customdata=d[["canonical_sku"]],
        hovertext=[f"{n}: {fmt_eur(r)} revenue, {p:.0%} margin"
                  for n, r, p in zip(d["name"], d["net_revenue"], d["contribution_margin_pct"])],
        hoverinfo="text",
    ))

# The dotted lines ARE the quadrant boundaries - position tells you the
# quadrant even with color switched off, same as every bar on the Overview
# chart already carries its own label independent of colour.
fig.add_vline(x=revenue_threshold, line=dict(color="#c3c2b7", dash="dot", width=1))
fig.add_hline(y=HEALTHY_MARGIN_PCT * 100, line=dict(color="#c3c2b7", dash="dot", width=1))
for quadrant, (x, y, xanchor) in {
    "Volume drivers": (0.97, 0.95, "right"), "Hidden losers": (0.97, 0.05, "right"),
    "Quiet winners": (0.03, 0.95, "left"), "Dead weight": (0.03, 0.05, "left"),
}.items():
    fig.add_annotation(x=x, y=y, xref="paper", yref="paper", xanchor=xanchor,
                       text=quadrant, showarrow=False,
                       font=dict(size=13, color=QUADRANT_STYLE[quadrant]["color"]),
                       bgcolor="rgba(252,252,251,0.88)", borderpad=3)

fig.update_xaxes(type="log", title=None,
                 tickvals=[1000, 3000, 10000, 30000, 100000],
                 ticktext=["€1K", "€3K", "€10K", "€30K", "€100K"])
fig.update_yaxes(ticksuffix="%", title=None)
fig.update_layout(
    height=460,
    margin=dict(l=10, r=10, t=10, b=10),
    font=dict(size=15),
    legend=dict(orientation="h", yanchor="bottom", y=1.02, x=0),
)

event = st.plotly_chart(fig, use_container_width=True, config=PLOTLY_CONFIG,
                        theme="streamlit", on_select="rerun", selection_mode="points",
                        key="sku_scatter")

points = (event or {}).get("selection", {}).get("points", [])
if points and points[0].get("customdata"):
    selected_sku = points[0]["customdata"][0]
else:
    selected_sku = load_mart("headline").iloc[0]["canonical_sku"]  # a sensible default

st.markdown("##### Selected product")
row = sku[sku["canonical_sku"] == selected_sku].iloc[0]
with st.container(border=True):
    st.markdown(f"**{row['name']}** - {row['category']}")
    c1, c2 = st.columns(2)
    c1.metric("Revenue (24 months)", fmt_eur_compact(row["net_revenue"]))
    c2.metric("Contribution margin (24 months)",
             f"{fmt_eur_compact(row['contribution_margin'])} ({row['contribution_margin_pct']:.1%})")
    st.caption(f"{row['units']:,} units sold. {describe(row)}")
if not points:
    st.caption("Tap or click any point on the chart to see that product here instead.")

losers = sku[sku["quadrant"] == "Hidden losers"].sort_values("contribution_margin")
still_positive = int((losers["contribution_margin"] >= 0).sum())
positive_note = (f" {still_positive} of these are still (barely) profitable - just far "
                 "thinner than a top seller's margin should be." if still_positive else "")

st.markdown("##### Below the healthy bar")
st.caption(
    "The Hidden losers quadrant from the chart above, worst margin first."
    f"{positive_note}"
)
if len(losers):
    table = losers[["name", "net_revenue", "contribution_margin_pct"]].copy()
    table["net_revenue"] = table["net_revenue"].apply(fmt_eur_compact)
    table["contribution_margin_pct"] = table["contribution_margin_pct"].apply(lambda p: f"{p:.0%}")
    table.columns = ["Product", "Revenue", "Margin"]
    st.dataframe(table, hide_index=True, use_container_width=True)
else:
    st.caption("None this period.")

l1, l2 = st.columns(2)
l1.page_link("Overview.py", label="← Overview")
l2.page_link("pages/4_Channel_comparison.py", label="Channel comparison →")
