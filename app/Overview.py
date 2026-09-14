"""Overview: gross revenue down to net margin, and the headline loss."""

import plotly.graph_objects as go
import streamlit as st

from loaders import load_clean, load_mart
from ui import CHANNEL_LABELS, PLOTLY_CONFIG, configure_page, fmt_eur, fmt_eur_compact

CHART_LABELS = {
    "Outbound shipping": "Shipping",
    "Referral fees": "Referral",
    "Fulfilment fees": "Fulfilment",
    "Platform fees": "Platform",
}

configure_page("Overview", "Where does revenue actually go before it becomes profit?")

st.caption(
    "Vella Home is a fictional home-and-kitchen brand selling on its own store, "
    "on Amazon, and on a European marketplace. This dashboard follows every euro "
    "from sale to profit, by product and by channel. Every number on this site "
    "is synthetic, generated for this demo."
)

headline = load_mart("headline").iloc[0]
channel_cc = load_mart("channel_comparison")
wf = load_mart("margin_waterfall")

net_margin = wf.loc[wf["step"] == "Net margin", "amount"].iloc[0]
gross_revenue = wf.loc[wf["step"] == "Gross revenue", "amount"].iloc[0]

# Which channel the loss is concentrated in, if it's concentrated at all.
by_channel = channel_cc[channel_cc["canonical_sku"] == headline["canonical_sku"]]
losing = by_channel[by_channel["contribution_margin"] < 0]
where = ""
if len(losing) and losing["contribution_margin"].sum() != 0:
    worst = losing.loc[losing["contribution_margin"].idxmin()]
    worst_share = worst["contribution_margin"] / losing["contribution_margin"].sum()
    if worst_share > 0.6:
        where = f", mostly on {CHANNEL_LABELS[worst['channel']]}"

# Same halving a reader would do by hand from the two numbers already on this
# page (annual loss, and net margin below) - matching that keeps the % checkable.
annual_net_margin = net_margin / 2
profit_share = headline["annual_loss_eur"] / annual_net_margin

st.markdown("##### Headline finding")
with st.container(border=True):
    st.markdown(
        f"**{headline['name']}** is Vella Home's #{headline['revenue_rank']} seller "
        f"by revenue. It loses about {fmt_eur_compact(headline['annual_loss_eur'])} "
        f"a year{where} - about {profit_share:.0%} of Vella Home's annual profit."
    )
    c1, c2 = st.columns(2)
    c1.metric("Lost every year", fmt_eur_compact(headline["annual_loss_eur"]))
    c2.metric("Annual revenue", fmt_eur_compact(headline["annual_revenue_eur"]))
    l1, l2 = st.columns(2)
    l1.page_link("pages/4_Channel_comparison.py", label="Channel comparison →")
    l2.page_link("pages/3_Returns.py", label="Returns →")

st.caption("September 2024 to August 2026 (24 months). Revenue is ex-VAT.")

k1, k2 = st.columns(2)
k1.metric("Net margin (before overheads)",
         f"{fmt_eur_compact(net_margin)} ({net_margin / gross_revenue:.1%})")
k2.metric("Gross revenue", fmt_eur_compact(gross_revenue))
st.caption(
    "\"Before overheads\" means after channel fees and shipping, not general "
    "costs like rent or payroll - those aren't part of this dataset."
)

st.markdown("##### From gross revenue to net margin")

measures = ["absolute"] + ["relative"] * (len(wf) - 2) + ["total"]
display_labels = [CHART_LABELS.get(s, s) for s in wf["step"]]

fig = go.Figure(go.Waterfall(
    orientation="h",
    measure=measures,
    y=display_labels,
    x=wf["amount"],
    hovertext=[f"{step}: {fmt_eur(v)}" for step, v in zip(wf["step"], wf["amount"])],
    hoverinfo="text",
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
for label, amount in zip(display_labels, wf["amount"]):
    fig.add_annotation(x=1.0, xref="paper", xanchor="left", xshift=10,
                       y=label, yref="y", showarrow=False,
                       text=fmt_eur_compact(amount), font=dict(size=17, color="#52514e"))
fig.update_yaxes(autorange="reversed", tickfont=dict(size=17))
fig.update_xaxes(showticklabels=False, range=[0, gross_revenue * 1.03])
fig.update_layout(
    height=100 + 44 * len(wf),  # adapts to the step count, never fixed
    margin=dict(l=10, r=100, t=10, b=10),
    font=dict(size=18),
    bargap=0.15,
)
st.plotly_chart(fig, use_container_width=True, config=PLOTLY_CONFIG, theme="streamlit")

order_lines = load_clean("order_lines")
unmapped_pct = (order_lines["cost_missing_reason"] == "unmapped_sku").mean()
no_cost_pct = (order_lines["cost_missing_reason"] == "no_cost_recorded").mean()
recoverable_stock = load_mart("returns_by_sku")["recoverable_stock"].sum()
true_gross_revenue = (order_lines["quantity"] * order_lines["unit_price"]).sum()
excluded_revenue_share = 1 - gross_revenue / true_gross_revenue

st.caption(
    f"Every figure above, including gross revenue, excludes "
    f"{unmapped_pct + no_cost_pct:.1%} of order lines with no usable cost - "
    f"{excluded_revenue_share:.1%} of revenue, since those lines skew slightly "
    f"larger (true gross revenue across all lines is {fmt_eur_compact(true_gross_revenue)}): "
    f"{unmapped_pct:.1%} couldn't be matched to a product, {no_cost_pct:.1%} are "
    "matched SKUs with no cost on file. Refunds and product cost aren't double "
    "counted: refunds return the sale price, cost stays charged because stock "
    f"that comes back resellable ({fmt_eur_compact(recoverable_stock)} of it) isn't "
    "credited back yet. Returns are attributed to the month of the original order, "
    "not the month they arrive, so the last two months are still provisional."
)
l3, l4 = st.columns(2)
l3.page_link("pages/5_Data_quality.py", label="Data quality →")
l4.page_link("pages/3_Returns.py", label="Returns →")
