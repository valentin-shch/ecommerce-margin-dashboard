# Vella Home profitability dashboard

**[Live demo →](https://ecommerce-margin-dashboard.streamlit.app/)**

A demo that shows the gap between revenue and real profit. Vella Home is a
made-up home and kitchen brand that sells on its own store, on Amazon, and on
a European marketplace. All the data here is synthetic and built by the code
in this repo.

The dashboard starts at gross revenue and works down to net margin. It
subtracts discounts, cost of goods, shipping, channel fees, and returns, then
points out the products that look fine on revenue but lose money once
returns are counted, and how much the channel you sell on changes that
margin.

## What's in it

- **Overview**: gross revenue to net margin as a waterfall, with the specific
  loss-making bestseller named and its annual cost quantified.
- **SKU profitability**: revenue vs margin by product, quadrant-labelled in
  plain language, tap or click any point for a detail panel.
- **Returns**: what returns cost in euros, not just a rate, by category,
  channel, reason and product, and which products they flip unprofitable.
- **Channel comparison**: the same product's margin across channels, since
  channel mix alone can turn a profitable product into a loss.
- **Data engineering**: how three channels' messy exports resolve to one
  canonical SKU, what's still excluded and why, and the pipeline behind it.

Every page is responsive down to a phone screen and carries a one-line
plain-language subtitle stating the question it answers.

## The data

Nothing here is real. `data/generate.py` builds 24 months of synthetic
orders, products and returns, deliberately messy the way real multi-channel
exports are: each channel uses its own SKU format (clean codes on the own
store, opaque ASINs on Amazon, hand-typed free text with typos on the
marketplace), some SKUs have no cost on file, returns arrive up to 60 days
after the order, own-store prices are VAT-inclusive and marketplace prices
aren't, and a few order lines have a discount larger than the unit price. A
handful of SKUs are designed to lose money after returns and fees, without
that being obvious from the raw data. `pipeline/clean.py` resolves and flags
all of it; the Data engineering page shows the receipts.

## Stack

Python, pandas, Plotly, Streamlit. No database: CSV to parquet to disk, read
straight from files. No external services, no API keys.

## Structure

    data/generate.py     builds the synthetic data (fixed seed, repeatable)
    data/raw/            generator output, left messy on purpose
    pipeline/clean.py    raw CSV to clean parquet: fix keys, join tables
    pipeline/metrics.py  margin math as plain functions, writes the marts the app reads
    app/                 Streamlit app, one file per page
    tests/               pytest for the metric functions

## Running it locally

    pip install -r requirements.txt
    python -m data.generate
    python -m pipeline.clean
    python -m pipeline.metrics
    streamlit run app/Overview.py

The seed and reporting date are fixed constants, not tied to today's date, so
the data is identical on every run unless you override them. Settings like
the seed, the reporting date, and the VAT rate are read from environment
variables, with defaults baked into the code so it runs without any config.
See `.env.example`.

## Deploying

Streamlit Community Cloud runs the repo as committed: `pip install -r
requirements.txt`, then `streamlit run app/Overview.py`. There's no separate
pipeline step at deploy time, so `data/clean/` (the pipeline's output, not
just `data/raw/`) is committed too, or every page fails to load. Regenerate
and rerun the pipeline first if the data needs to change, using the same
three commands as above.

No secrets or API keys to configure. A GitHub Actions workflow
(`.github/workflows/keepalive.yml`) pings the live URL every 6 hours so the
free tier doesn't go to sleep.
