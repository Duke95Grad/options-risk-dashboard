"""Options Risk Dashboard - Streamlit wrapper.

The dashboard itself is a self-contained HTML/JavaScript page (dashboard_template.html).
This app loads the data files, optionally swaps in an uploaded positions CSV,
embeds everything into the page and displays it.
"""
import csv
import io
import json
from pathlib import Path

import streamlit as st
import streamlit.components.v1 as components

HERE = Path(__file__).parent
DATA = HERE / "data"
TEMPLATE = HERE / "dashboard_template.html"
REQUIRED_COLUMNS = ["account", "symbol", "quantity", "cost_basis"]

st.set_page_config(page_title="Options Risk Dashboard", layout="wide", initial_sidebar_state="collapsed")


def read_positions(text: str) -> list[dict]:
    """Parse a positions CSV: account, symbol (ticker or OCC option symbol), quantity, cost_basis."""
    reader = csv.DictReader(io.StringIO(text))
    cols = [c.strip().lower() for c in (reader.fieldnames or [])]
    missing = [c for c in REQUIRED_COLUMNS if c not in cols]
    if missing:
        raise ValueError(f"Missing column(s): {', '.join(missing)}. Expected: {', '.join(REQUIRED_COLUMNS)}")
    rows = []
    for raw in reader:
        row = {k.strip().lower(): (v or "") for k, v in raw.items() if k}
        if not row.get("symbol", "").strip():
            continue
        float(row["quantity"])  # raises if not a number
        float(row["cost_basis"] or 0)
        rows.append({k: row[k] for k in REQUIRED_COLUMNS})
    if not rows:
        raise ValueError("The file has no position rows.")
    return rows


@st.cache_data
def load_market_data() -> dict:
    return {
        "underlyings": json.loads((DATA / "underlyings.json").read_text()),
        "option_quotes": json.loads((DATA / "option_quotes.json").read_text()),
        "vol_surface": json.loads((DATA / "vol_surface.json").read_text()),
        "yield_curve": json.loads((DATA / "yield_curve.json").read_text()),
    }


# ---- sidebar: optional positions upload ----
with st.sidebar:
    st.header("Positions")
    st.caption("Upload a CSV with columns account, symbol, quantity, cost_basis. "
               "Option symbols use OCC format, e.g. `AAPL  261120C00275000`.")
    upload = st.file_uploader("Positions CSV", type=["csv"])
    st.download_button("Download sample positions CSV", (DATA / "positions.csv").read_bytes(),
                       file_name="positions_sample.csv", mime="text/csv")

positions, source_label = None, "Sample data"
if upload is not None:
    try:
        positions = read_positions(upload.getvalue().decode("utf-8-sig"))
        source_label = f"Positions: {upload.name} · market data: sample"
        st.sidebar.success(f"Loaded {len(positions)} positions from {upload.name}.")
    except Exception as exc:  # show the problem and fall back to the sample book
        st.sidebar.error(f"Could not read that file: {exc}")
if positions is None:
    positions = read_positions((DATA / "positions.csv").read_text())

data = {"positions": positions, **load_market_data()}
inject = ("window.__ORD_DATA__ = " + json.dumps(data, separators=(",", ":")) + ";"
          + "window.__ORD_SOURCE__ = " + json.dumps(source_label) + ";")
html = TEMPLATE.read_text(encoding="utf-8").replace("/*__ORD_DATA__*/", inject.replace("</", "<\\/"), 1)

if hasattr(st, "iframe"):  # Streamlit 1.5x+: sizes itself to the dashboard
    st.iframe(html, height="content")
else:  # older Streamlit
    components.html(html, height=2200, scrolling=True)
