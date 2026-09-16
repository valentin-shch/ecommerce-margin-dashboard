"""Data engineering: what it took to turn three messy channel exports into numbers you can trust."""

import plotly.graph_objects as go
import streamlit as st

from loaders import load_clean
from ui import PLOTLY_CONFIG, configure_page, fmt_eur_compact

configure_page("Data engineering",
               "What it took to turn three channels' messy exports into one number you can trust")

st.caption(
    "Three raw CSVs go in; a seeded generator, a cleaning pass and a metrics pass "
    "turn them into everything on this site. Nothing here is a black box - this "
    "page shows the joins, the judgment calls, and what's still excluded and why."
)

sku_mapping = load_clean("sku_mapping")
products = load_clean("products")

st.markdown("##### Three channels, three SKU formats, one product")
st.markdown(
    "Own store uses Vella Home's own codes. Amazon assigns opaque ASINs. The "
    "marketplace is free-text the seller typed by hand - typos, abbreviations, "
    "underscores, whatever fit. All three have to resolve to the same canonical "
    "SKU before a product's margin can be compared across channels at all."
)

examples = (sku_mapping.merge(products[["sku", "name"]], on="sku", how="left")
           .set_index("channel_sku").loc[
               ["VH-1000", "B0AH374DW8", "cermic pasta bowl set", "stonfryipan"]].reset_index())
CHANNEL_TAG = {"own_store": "Own store", "amazon": "Amazon", "marketplace": "Marketplace"}
# Even a 3-column table truncated mid-word at 390px with no scroll cue - this
# content is just too verbose for fixed columns. Flowing text wraps instead of
# cutting off, same idea as the stacked-card alternative the brief allows.
with st.container(border=True):
    for _, row in examples.iterrows():
        st.markdown(f"**{CHANNEL_TAG[row['channel']]}** &nbsp; `{row['channel_sku']}` "
                    f"&rarr; **{row['sku']}** {row['name']}")
st.caption(
    f"{len(sku_mapping):,} channel SKU codes map to {sku_mapping['sku'].nunique()} "
    "canonical products this way - normalised, matched case- and whitespace-insensitively, "
    "and left unmatched rather than guessed at when nothing fits (see below)."
)

order_lines = load_clean("order_lines")
n = len(order_lines)
unmapped_n = int((order_lines["cost_missing_reason"] == "unmapped_sku").sum())
no_cost_n = int((order_lines["cost_missing_reason"] == "no_cost_recorded").sum())
usable_n = n - unmapped_n - no_cost_n

gross = order_lines["quantity"] * order_lines["unit_price"]
total_revenue = gross.sum()
unmapped_revenue = gross[order_lines["cost_missing_reason"] == "unmapped_sku"].sum()
no_cost_revenue = gross[order_lines["cost_missing_reason"] == "no_cost_recorded"].sum()

st.markdown("##### What's left after matching")
st.metric("Order lines complete enough to use", f"{usable_n / n:.1%}",
         help="Every figure on this site is built only from these lines.")

BAR_COLORS = {"Usable": "#2a78d6", "Can't be matched to a product": "#e34948",
             "Matched, no cost on file": "#d68a1f"}
segments = [("Usable", usable_n), ("Can't be matched to a product", unmapped_n),
           ("Matched, no cost on file", no_cost_n)]

fig = go.Figure()
for seg_name, count in segments:
    # In-bar text on a 93/4.5/2.4 split meant the two small segments had no
    # room to hold their own label - Plotly shrinks and rotates it into
    # illegibility. A legend (like the SKU quadrant scatter) stays readable
    # no matter how thin the segment is.
    fig.add_trace(go.Bar(
        orientation="h", y=["Order lines"], x=[count],
        marker=dict(color=BAR_COLORS[seg_name]),
        name=seg_name,  # counts are already in the explanation text below - the
                        # legend's job here is just identity, not repeating numbers
        hovertext=f"{seg_name}: {count:,} lines ({count / n:.1%})", hoverinfo="text",
    ))
fig.update_layout(
    barmode="stack",
    height=170,
    margin=dict(l=10, r=10, t=10, b=10),
    font=dict(size=14),
    bargap=0.5,
    legend=dict(orientation="h", yanchor="bottom", y=1.02, x=0),
)
fig.update_xaxes(showticklabels=False, range=[0, n])
fig.update_yaxes(showticklabels=False)
st.plotly_chart(fig, use_container_width=True, config=PLOTLY_CONFIG, theme="streamlit")

st.caption(
    f"By revenue rather than lines: {1 - (unmapped_revenue + no_cost_revenue) / total_revenue:.1%} "
    f"usable, since the excluded lines skew slightly larger than average."
)

with st.container(border=True):
    st.markdown(
        f"**Can't be matched to a product** ({unmapped_n:,} lines, "
        f"{fmt_eur_compact(unmapped_revenue)} of revenue) - after normalising for case and "
        "whitespace, roughly one in twenty-two channel codes still doesn't map to a "
        "Vella Home product. The sale happened, but there's no product to attach "
        "its cost to, so it's left out rather than guessed at."
    )
    st.markdown(
        f"**Matched, no cost on file** ({no_cost_n:,} lines, "
        f"{fmt_eur_compact(no_cost_revenue)} of revenue) - the product is known, but "
        "roughly 1 in 40 has no recorded cost price, usually a new or discontinued "
        "SKU with a gap in the product record. Same treatment: excluded, not estimated."
    )

st.markdown("##### Order volume, and what's still provisional")
order_lines["ym"] = order_lines["order_date"].dt.to_period("M")
counts = order_lines.groupby("ym").size()
provisional = order_lines.groupby("ym")["returns_provisional"].any()
months = counts.index.to_timestamp()
first_provisional = months[provisional.values][0] if provisional.any() else None

fig2 = go.Figure(go.Scatter(
    x=months, y=counts, mode="lines+markers",
    line=dict(color="#2a78d6", width=2), marker=dict(size=5, color="#2a78d6"),
    hovertext=[f"{m:%b %Y}: {c:,} order lines" for m, c in zip(months, counts)],
    hoverinfo="text",
))
if first_provisional is not None:
    fig2.add_vrect(x0=first_provisional, x1=months[-1] + (months[-1] - months[-2]),
                   fillcolor="#d68a1f", opacity=0.15, line_width=0)
    fig2.add_annotation(x=first_provisional, y=counts.max(), xanchor="left", yanchor="top",
                        showarrow=False, text="still settling", font=dict(size=13, color="#a8690f"))
fig2.update_xaxes(dtick="M3", tickformat="%b %y", tickfont=dict(size=13))
fig2.update_yaxes(tickfont=dict(size=13), rangemode="tozero")
fig2.update_layout(
    height=300,
    margin=dict(l=10, r=10, t=10, b=10),
    font=dict(size=14),
)
st.plotly_chart(fig2, use_container_width=True, config=PLOTLY_CONFIG, theme="streamlit")
st.caption(
    "Order lines placed each month - the Q4 peak is Vella Home's actual seasonal "
    "pattern, not a data issue. The shaded months are still inside the 60-day return "
    "window, so their margin isn't final yet (see Returns)."
)

st.markdown("##### Known data errors, caught rather than hidden")
discount_errors = int(order_lines["discount_error"].sum())
qty_errors = int(order_lines["return_qty_error"].sum())
vat_adjusted = int((order_lines["channel"] == "own_store").sum())
c1, c2, c3 = st.columns(3)
c1.metric("Discount exceeded price", f"{discount_errors:,}", help="Clipped to the unit price, not left negative.")
c2.metric("Returned qty exceeded ordered", f"{qty_errors:,}",
         help="A line with more units returned than were ever ordered - a data error. "
              "Not the same as a partial return (e.g. 1 of 3 units back), which is normal "
              "and handled on every page.")
c3.metric("Own-store lines, VAT removed", f"{vat_adjusted:,} lines",
         help="Own-store prices are VAT-inclusive; marketplace prices aren't. Both are compared ex-VAT.")

st.markdown("##### How it's built")
c4, c5 = st.columns(2)
c4.metric("Pipeline stages", "3", help="generate -> clean -> metrics. Each stage writes its own output; the app only ever reads the last one.")
c5.metric("Automated tests", "13", help="Covering the margin formulas in pipeline/metrics.py - every deliberate edge case (partial returns, missing cost, weight-scaled fees) has one.")

l1, l2 = st.columns(2)
l1.page_link("pages/4_Channel_comparison.py", label="← Channel comparison")
l2.page_link("Overview.py", label="Overview →")
