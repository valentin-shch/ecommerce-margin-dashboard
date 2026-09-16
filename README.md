# Vella Home profitability dashboard

[Live demo →](https://ecommerce-margin-dashboard.streamlit.app/)

A demo that shows the gap between revenue and real profit. Vella Home is a
made-up home and kitchen brand that sells on its own store, on Amazon, and on
a European marketplace. All the data here is synthetic and built by the code
in this repo.

The dashboard starts at gross revenue and works down to net margin. It
subtracts discounts, cost of goods, shipping, channel fees, and returns. It
then points out the products that look fine on revenue but lose money once
returns are counted, and how much the channel you sell on changes that
margin.

## Pages

    Overview              gross revenue to net margin, and the headline loss
    SKU profitability     revenue vs margin by product, and who's actually losing money
    Returns               what returns cost in euros, and which products they flip unprofitable
    Channel comparison    the same product across channels, at different margins
    Data engineering      how three messy channel exports get cleaned into these numbers

## Layout

    data/generate.py     builds the synthetic data (fixed seed, repeatable)
    data/raw/            generator output, left messy on purpose
    pipeline/clean.py    raw CSV to clean parquet: fix keys, join tables
    pipeline/metrics.py  margin math as plain functions, writes the marts the app reads
    app/                 Streamlit app, one file per page
    tests/              pytest for the metric functions

## Running it

    pip install -r requirements.txt
    python -m data.generate
    python -m pipeline.clean
    python -m pipeline.metrics
    streamlit run app/Overview.py

Settings like the seed, the reporting date, and the VAT rate are read from
environment variables. Defaults are set in code, so it runs without any
config. See `.env.example`.
