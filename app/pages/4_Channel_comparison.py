"""Channel comparison: the same product, sold through different channels, at different margins."""

import plotly.graph_objects as go
import streamlit as st

from loaders import load_mart
from ui import PLOTLY_CONFIG, configure_page, fmt_eur_compact

configure_page("Channel comparison", "Does the channel you sell through change the margin?")

st.caption(
    "Only products sold on 2+ channels - a single-channel product has nothing to "
    "compare. Totals over the full 24 months, same basis as SKU profitability."
)

cc = load_mart("channel_comparison")
headline = load_mart("headline").iloc[0]

CHANNEL_AXIS_LABELS = {"own_store": "Own store", "amazon": "Amazon", "marketplace": "Marketplace"}

by_channel = cc.groupby("channel").agg(revenue=("net_revenue", "sum"),
                                       margin=("contribution_margin", "sum"))
by_channel["pct"] = by_channel["margin"] / by_channel["revenue"]
by_channel = by_channel.sort_values("pct")

best = cc.loc[cc.groupby("canonical_sku")["contribution_margin_pct"].idxmax()]
worst = cc.loc[cc.groupby("canonical_sku")["contribution_margin_pct"].idxmin()]
spread = best[["canonical_sku", "name", "channel", "contribution_margin_pct"]].merge(
    worst[["canonical_sku", "channel", "contribution_margin_pct"]],
    on="canonical_sku", suffixes=("_best", "_worst"))
flips = spread[(spread["contribution_margin_pct_best"] > 0) &
              (spread["contribution_margin_pct_worst"] < 0)].copy()
flips["swing"] = flips["contribution_margin_pct_best"] - flips["contribution_margin_pct_worst"]
flips = flips.sort_values("swing", ascending=False)

worst_ch = by_channel.index[0]
best_ch = by_channel.index[-1]
worst_ch_flip_share = (flips["channel_worst"] == worst_ch).mean() if len(flips) else 0

st.markdown("##### Headline finding")
with st.container(border=True):
    st.markdown(
        f"{CHANNEL_AXIS_LABELS[best_ch]} earns Vella Home a "
        f"{by_channel.loc[best_ch, 'pct']:.0%} margin on average; "
        f"{CHANNEL_AXIS_LABELS[worst_ch]} earns {by_channel.loc[worst_ch, 'pct']:.0%}. "
        f"For {len(flips)} products, the gap is wide enough that the channel alone "
        f"decides whether it's profitable: {(flips['channel_worst'] == worst_ch).sum()} "
        f"of them are negative on {CHANNEL_AXIS_LABELS[worst_ch]} but positive on "
        f"{CHANNEL_AXIS_LABELS[best_ch]}."
    )
    cols = st.columns(3)
    for col, ch in zip(cols, by_channel.index):
        col.metric(CHANNEL_AXIS_LABELS[ch], f"{by_channel.loc[ch, 'pct']:.0%}")

st.markdown("##### Margin by channel, product by product")
names = sorted(cc["name"].unique())
default_name = cc.loc[cc["canonical_sku"] == headline["canonical_sku"], "name"].iloc[0]
selected_name = st.selectbox("Product", names, index=names.index(default_name))

row = cc[cc["name"] == selected_name].sort_values("contribution_margin_pct")
labels = row["channel"].map(CHANNEL_AXIS_LABELS)
colors = ["#e34948" if v < 0 else "#2a78d6" for v in row["contribution_margin_pct"]]

fig = go.Figure(go.Bar(
    orientation="h", y=labels, x=row["contribution_margin_pct"] * 100,
    marker=dict(color=colors),
    hovertext=[f"{lab}: {p:.0%} margin ({fmt_eur_compact(m)})"
              for lab, p, m in zip(labels, row["contribution_margin_pct"], row["contribution_margin"])],
    hoverinfo="text",
))
pad = max(15, row["contribution_margin_pct"].abs().max() * 100 * 0.3)
fig.update_xaxes(showticklabels=False,
                 range=[min(-5, row["contribution_margin_pct"].min() * 100 - pad),
                        max(5, row["contribution_margin_pct"].max() * 100 + pad)])
# Anchoring the value label to each bar's own end meant a short negative bar
# put its label right where the channel-name column already sits - they
# overlapped. One fixed column per side, like the Overview waterfall and
# Returns charts, decouples the labels from the bars entirely.
fig.update_yaxes(showticklabels=False)
for label, pct, margin in zip(labels, row["contribution_margin_pct"], row["contribution_margin"]):
    fig.add_annotation(x=0.0, xref="paper", xanchor="right", xshift=-10,
                       y=label, yref="y", showarrow=False, align="right",
                       text=str(label), font=dict(size=15, color="#52514e"))
    fig.add_annotation(x=1.0, xref="paper", xanchor="left", xshift=10,
                       y=label, yref="y", showarrow=False, align="left",
                       text=f"{pct:.0%} ({fmt_eur_compact(margin)})", font=dict(size=15, color="#52514e"))
fig.add_vline(x=0, line=dict(color="#c3c2b7", width=1))
fig.update_layout(
    height=max(160, 60 + 60 * len(row)),
    margin=dict(l=110, r=100, t=10, b=10),
    font=dict(size=15),
    bargap=0.35,
)
st.plotly_chart(fig, use_container_width=True, config=PLOTLY_CONFIG, theme="streamlit")

st.markdown("##### Where channel decides profit or loss")
st.caption(
    f"{len(flips)} products are negative margin on one channel and positive on "
    "another - same product, same cost, different outcome depending where it sells. "
    "Sorted by the size of that swing, biggest first."
)
if len(flips):
    # A "best channel X% -> worst channel Y%" column still overflowed at 390px
    # alongside long product names, same lesson as Returns: 2 columns only
    # works if the second one is short. The channel names are already in the
    # headline sentence and the chart above, so the table just needs the swing.
    table = flips[["name"]].copy()
    table["range"] = [f"{bp:+.0%} -> {wp:+.0%}"
                      for bp, wp in zip(flips["contribution_margin_pct_best"],
                                        flips["contribution_margin_pct_worst"])]
    table.columns = ["Product", "Best -> worst margin"]
    st.dataframe(table, hide_index=True, use_container_width=True)
else:
    st.caption("None this period.")

l1, l2 = st.columns(2)
l1.page_link("pages/3_Returns.py", label="← Returns")
l2.page_link("pages/5_Data_quality.py", label="Data quality →")
