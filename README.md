# Options Risk Dashboard

Risk dashboard for one customer account holding equity, ETF and index options plus stock:
Reg T / FINRA strategy pairing, security-level greeks, VIX-method 30-day IV and expected moves,
option chains with model theos (Bjerksund-Stensland 2002, Black-Scholes-Merton, CRR binomial),
a price and IV shock module (normalized-strike remap), beta-weighted scenario P&L grids,
and what-if trades.

All prices, quotes, the volatility surface, the Treasury curve and the betas in `data/` are **sample data**.

## Files

| File | What it is |
|---|---|
| `app.py` | The Streamlit app. Loads the data, embeds it in the dashboard page and shows it. |
| `dashboard_template.html` | The dashboard itself (HTML/JavaScript, fully self-contained). |
| `requirements.txt` | Python packages Streamlit Community Cloud installs. |
| `data/positions.csv` | Sample positions: `account, symbol, quantity, cost_basis`. Options use OCC symbols. |
| `data/*.json` | Sample underlyings (spot, dividend yield, beta), option quotes, vol surface, Treasury curve. |

## Using your own positions

Open the sidebar (the `>>` arrow at the top left of the app) and upload a CSV with the columns
`account, symbol, quantity, cost_basis`. Option symbols use OCC format, for example `AAPL  261120C00275000`
(root padded to 6 characters, YYMMDD, C/P, strike x 1000 in 8 digits). Only underlyings and contracts
present in the market data files can be priced. Uploaded files are used for that browser session only.

## Run it on your own computer (optional)

```
pip install -r requirements.txt
streamlit run app.py
```
