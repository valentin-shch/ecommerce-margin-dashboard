"""Overview: gross revenue down to net margin, and the headline loss."""

import plotly.graph_objects as go
import streamlit as st

from loaders import load_mart
from ui import PLOTLY_CONFIG, configure_page, fmt_eur, fmt_eur_compact

configure_page("Overview", "Where does revenue actually go before it becomes profit?")

st.caption(
    "Vella Home is a fictional home-and-kitchen brand selling on its own store, "
    "on Amazon, and on a European marketplace. Every number on this site is "
    "synthetic, generated for this demo."
)

headline = load_mart("headline").iloc[0]

st.markdown("##### Headline finding")
with st.container(border=True):
    st.markdown(
        f"**{headline['name']}** is Vella Home's #{headline['revenue_rank']} "
        "seller by revenue, and it loses money on every sale."
    )
    c1, c2 = st.columns(2)
    c1.metric("Lost every year", fmt_eur_compact(headline["annual_loss_eur"]))
    c2.metric("Annual revenue", fmt_eur_compact(headline["annual_revenue_eur"]))
    st.caption(
        "Amazon's fees and a high return rate erase the margin. "
        "See Channel comparison and Returns."
    )

wf = load_mart("margin_waterfall")
net_margin = wf.loc[wf["step"] == "Net margin", "amount"].iloc[0]
gross_revenue = wf.loc[wf["step"] == "Gross revenue", "amount"].iloc[0]

k1, k2, k3 = st.columns(3)
k1.metric("Net margin", fmt_eur_compact(net_margin))
k2.metric("Net margin %", f"{net_margin / gross_revenue:.1%}")
k3.metric("Gross revenue", fmt_eur_compact(gross_revenue))

st.markdown("##### From gross revenue to net margin")

measures = ["absolute"] + ["relative"] * (len(wf) - 2) + ["total"]

fig = go.Figure(go.Waterfall(
    orientation="h",
    measure=measures,
    y=wf["step"],
    x=wf["amount"],
    hovertext=[fmt_eur(v) for v in wf["amount"]],
    hoverinfo="text+y",
    connector=dict(line=dict(color="#c3c2b7", width=1)),
    increasing=dict(marker=dict(color="#2a78d6")),
    decreasing=dict(marker=dict(color="#e34948")),
    totals=dict(marker=dict(color="#2a78d6")),
    showlegend=False,  # every bar already has its own name; red/blue only
                       # reinforces cost-vs-total, it isn't the only cue
))
# A label placed at each bar's own edge collides with the axis text once a
# bar's cumulative position sits low in the range. A fixed right-hand column
# can't collide with anything, so every value lands there instead.
for step, amount in zip(wf["step"], wf["amount"]):
    fig.add_annotation(x=1.0, xref="paper", xanchor="left", xshift=10,
                       y=step, yref="y", showarrow=False,
                       text=fmt_eur_compact(amount), font=dict(size=13, color="#52514e"))
fig.update_yaxes(autorange="reversed")
fig.update_xaxes(tickprefix="EUR ", separatethousands=True, range=[0, gross_revenue * 1.03])
fig.update_layout(
    height=130 + 55 * len(wf),  # adapts to the step count, never fixed
    margin=dict(l=10, r=90, t=30, b=10),
    font=dict(size=14),
)
st.plotly_chart(fig, use_container_width=True, config=PLOTLY_CONFIG, theme="streamlit")

st.caption(
    "Excludes the ~7% of order lines with no recorded product cost (see Data "
    "quality). The last two months are still settling as returns arrive, so "
    "this figure will move slightly (see Returns)."
)
