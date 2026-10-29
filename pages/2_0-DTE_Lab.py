"""0-DTE Lab: price and stress Reg T vs. portfolio-margin requirements for
same-day-expiring index, ETF and single-stock options."""
import json
import sys
from dataclasses import asdict
from datetime import date, datetime, time, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import pandas as pd
import plotly.graph_objects as go
import streamlit as st
import streamlit.components.v1 as components

from zdte.clock import OPEN, clock_at, minutes_to_close
from zdte.engine import ModelConfig, requirement_path, snapshot
from zdte.positions import dummy_account
from zdte.products import PRODUCTS

try:
    st.set_page_config(page_title="0-DTE Lab", page_icon="⏱️", layout="wide")
except Exception:
    pass

ZDTE = ROOT / "zdte"
D0 = date(2000, 1, 1)
LIGHT = {"regt": "#2E6FBA", "pm": "#C2582B", "ink": "#262730", "muted": "#6B7180", "line": "#E4E6EB"}
DARK = {"regt": "#5D9DE3", "pm": "#E2804F", "ink": "#F2F3F5", "muted": "#A0A6B2", "line": "#2B2F3A"}
FONT = '"Source Sans 3", "Source Sans Pro", sans-serif'
MODEL_LINE = ("Pricing model: Black-Scholes-Merton with a continuous dividend yield and skew by moneyness. "
              "American-style ETF and stock options are floored at intrinsic value. Time to expiry is counted "
              "in minutes to the 4:00 PM ET close.")


def theme_type():
    try:
        return st.context.theme.type or "light"
    except Exception:
        return "light"


THEME = theme_type()
COL = DARK if THEME == "dark" else LIGHT


def money(x):
    return f"−${abs(x):,.0f}" if x < -0.5 else f"${x:,.0f}"


def num(x, d=0):
    return f"{x:,.{d}f}".replace("-", "−")


def stretch(fn, *args, **kwargs):
    """Full-width element on both newer (width="stretch") and older Streamlit versions."""
    try:
        return fn(*args, width="stretch", **kwargs)
    except Exception:
        return fn(*args, use_container_width=True, **kwargs)


def chart_header(title, caption):
    st.markdown(f"**{title}**")
    st.caption(caption)


def style_fig(fig, legend=True, height=320):
    fig.update_layout(
        height=height, margin=dict(l=8, r=8, t=30 if legend else 8, b=8),
        font=dict(family=FONT, size=12, color=COL["muted"]),
        paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
        showlegend=legend,
        legend=dict(orientation="h", x=0, xanchor="left", y=1.02, yanchor="bottom",
                    font=dict(color=COL["ink"]), bgcolor="rgba(0,0,0,0)"),
        hoverlabel=dict(font=dict(family=FONT, size=13)),
    )
    fig.update_xaxes(gridcolor=COL["line"], linecolor=COL["line"], zeroline=False)
    fig.update_yaxes(gridcolor=COL["line"], zerolinecolor=COL["muted"], tickformat="$~s", hoverformat="$,.0f", rangemode="tozero")
    stretch(st.plotly_chart, fig, config={"displayModeBar": False})


def show_table(df, fmt):
    stretch(st.dataframe, df.style.format(fmt, na_rep=""), hide_index=True)


def clock_dt(mins_left):
    return datetime.combine(D0, clock_at(mins_left))


# ---------------------------------------------------------------- sidebar
with st.sidebar:
    st.header("Clock and model")
    as_of = st.slider("Current time (ET)", min_value=OPEN, max_value=time(15, 59),
                      value=time(11, 0), step=timedelta(minutes=1), format="h:mm A",
                      help="Where the trading day stands now. The account view and the simulator's starting "
                           "point are valued at this time.")
    conv_label = st.radio("Time convention", ["Trading time (weighted)", "Calendar time"],
                          help="Trading time measures what's left of today's 390-minute session, weighted so the "
                               "open and close carry more variance. Calendar time counts raw minutes over a "
                               "365-day year. Use the convention your IVs were built in.")
    u_shape = st.slider("Open/close volatility weight", 0.0, 4.0, 1.5, 0.1,
                        disabled=conv_label.startswith("Calendar"),
                        help="0 spreads variance evenly across the day. Higher values put more of it near the "
                             "open and close, so midday theta is slower and late-day theta faster.")
    r = st.number_input("Risk-free rate (%)", value=4.0, step=0.25) / 100.0
    skew_mult = st.slider("Skew strength", 0.0, 2.0, 1.0, 0.1,
                          help="Scales each product's put skew. 0 prices every strike at the ATM vol.")
    overlay = st.slider("PM house vol overlay (± vol pts)", 0, 20, 0,
                        help="Not part of the FINRA rule. When on, each PM price point is also valued with vol "
                             "shifted up and down by this amount, and the worse result is used.")
    st.caption("Dummy positions and market data. Margin parameters are FINRA 4210 customer minimums "
               "with no house add-ons; edit them in zdte/products.py.")

cfg = ModelConfig(r=r, convention="calendar" if conv_label.startswith("Calendar") else "trading",
                  u_shape=u_shape, skew_mult=skew_mult, vol_overlay=overlay / 100.0)
mins_now = minutes_to_close(as_of)
account = dummy_account(ModelConfig(r=r, convention=cfg.convention, u_shape=u_shape, skew_mult=skew_mult))
symbols = list(dict.fromkeys(account["underlying"]))

# ---------------------------------------------------------------- header
st.title("0-DTE Lab")
st.markdown(f"Same-day expirations, valued at **{as_of.strftime('%-I:%M %p')} ET** with "
            f"**{int(mins_now // 60)}h {int(mins_now % 60):02d}m** to the close.")
st.caption(MODEL_LINE)

tab_acct, tab_sim, tab_notes = st.tabs(["Account", "Simulate a security", "How the lab works"])

# ---------------------------------------------------------------- account
with tab_acct:
    rows = []
    for sym in symbols:
        prod, legs = PRODUCTS[sym], account[account.underlying == sym]
        s = snapshot(prod, legs, prod.spot, prod.iv, mins_now, cfg)
        t = s["totals"]
        rows.append({"Underlying": prod.label, "Spot": prod.spot, "ATM IV": prod.iv * 100,
                     "Contracts": t["contracts"], "Delta $": t["dollar_delta"],
                     "Gamma (Δ sh / 1%)": t["gamma_shares_1pct"], "Theta next hr": t["theta_next_hr"],
                     "Vega / pt": t["vega_per_pt"], "Reg T": s["regt"], "PM": s["pm"]["requirement"],
                     "PM vs Reg T": s["pm"]["requirement"] - s["regt"]})
    summary = pd.DataFrame(rows)
    tot_regt, tot_pm = summary["Reg T"].sum(), summary["PM"].sum()

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Reg T requirement", money(tot_regt))
    c2.metric("Portfolio margin requirement", money(tot_pm))
    c3.metric("PM vs Reg T", money(tot_pm - tot_regt),
              f"{(tot_pm / tot_regt - 1) * 100:+.0f}%".replace("-", "−") if tot_regt else None, delta_color="inverse")
    c4.metric("Theta, next hour", money(summary["Theta next hr"].sum()))

    show_table(summary, {"Spot": "{:,.2f}", "ATM IV": "{:.1f}%", "Contracts": "{:,.0f}",
                         "Delta $": money, "Gamma (Δ sh / 1%)": num, "Theta next hr": money,
                         "Vega / pt": money, "Reg T": money, "PM": money, "PM vs Reg T": money})

    left, right = st.columns(2, gap="large")
    with left:
        chart_header("Requirement by underlying", "Reg T and portfolio margin at the current time, price and vol.")
        fig = go.Figure()
        fig.add_bar(name="Reg T", x=summary["Underlying"], y=summary["Reg T"], marker_color=COL["regt"])
        fig.add_bar(name="Portfolio margin", x=summary["Underlying"], y=summary["PM"], marker_color=COL["pm"])
        fig.update_layout(barmode="group", bargap=0.3, hovermode="x unified")
        style_fig(fig)
    with right:
        chart_header("Account requirement through the close",
                     "Every 10 minutes from now to 4:00 PM, with price and vol unchanged.")
        paths = [requirement_path(PRODUCTS[s_], account[account.underlying == s_], PRODUCTS[s_].spot,
                                  PRODUCTS[s_].iv, mins_now, cfg, step=10.0)
                 .set_index("minutes_left")[["Reg T", "Portfolio margin"]] for s_ in symbols]
        total_path = sum(paths)
        xs = [clock_dt(m) for m in total_path.index]
        fig = go.Figure()
        fig.add_scatter(name="Reg T", x=xs, y=total_path["Reg T"], line=dict(color=COL["regt"], width=2))
        fig.add_scatter(name="Portfolio margin", x=xs, y=total_path["Portfolio margin"],
                        line=dict(color=COL["pm"], width=2))
        fig.update_layout(hovermode="x unified")
        fig.update_xaxes(tickformat="%-I:%M %p", hoverformat="%-I:%M %p")
        style_fig(fig)

    with st.expander("Positions"):
        show_table(account[["underlying", "strategy", "option", "qty", "avg_price"]].rename(columns={
            "underlying": "Underlying", "strategy": "Strategy", "option": "Option", "qty": "Qty",
            "avg_price": "Avg price"}), {"Avg price": "{:,.2f}"})

# ---------------------------------------------------------------- simulator
with tab_sim:
    pick, info = st.columns([2, 5], gap="large")
    sym = pick.selectbox("Security", symbols,
                         format_func=lambda s_: f"{PRODUCTS[s_].label}, {PRODUCTS[s_].name}")
    prod = PRODUCTS[sym]
    info.markdown(f"**{prod.exercise} style, multiplier {prod.multiplier}.** {prod.settlement}.  \n"
                  f"Reg T naked rate {prod.regt_pct:.0%} of the underlying (minimum {prod.regt_min_pct:.0%}). "
                  f"PM range: {prod.pm_class.split(': ')[-1]}.")
    st.caption("The sliders below reprice every leg as you drag them. Starting values are the current "
               "time, price and vol from the sidebar.")

    legs = account[account.underlying == sym]
    payload = {
        "product": {**asdict(prod), "american": prod.american},
        "legs": legs[["strategy_id", "strategy", "option", "type", "strike", "qty", "avg_price"]]
        .to_dict("records"),
        "cfg": asdict(cfg),
        "minutes_now": mins_now,
    }
    html = ((ZDTE / "sim_component.html").read_text(encoding="utf-8")
            .replace("__THEME__", THEME)
            .replace("__ENGINE__", (ZDTE / "sim_engine.js").read_text(encoding="utf-8"))
            .replace("__PAYLOAD__", json.dumps(payload)))
    if hasattr(st, "iframe"):          # Streamlit 1.5x+: sizes itself to the content
        st.iframe(html, height="content")
    else:                              # older Streamlit
        n_rows = len(legs) + len({*legs["strategy_id"]})
        components.html(html, height=1560 + 37 * n_rows, scrolling=True)

# ---------------------------------------------------------------- notes
with tab_notes:
    st.markdown("""
**Pricing model.** Black-Scholes-Merton with a continuous dividend yield. Each strike gets its own implied vol from
a simple skew around the ATM vol, measured by moneyness, so the curve moves with the underlying. American options
(ETFs and single stocks) are floored at intrinsic value; early exercise on the expiration day is otherwise ignored.

**Time.** Each option's time to expiry is measured in minutes to the 4:00 PM ET close, then turned into a year
fraction. In trading time, the remaining share of today's variance is divided by 252, and the open and close carry
more of it than midday. In calendar time, raw minutes are divided by the minutes in a 365-day year. The same IV
gives very different prices under the two, so match the convention to how the IV was quoted. At the close, options
are valued at intrinsic value and gamma and vega go to zero.

**Live simulator.** The simulator runs a browser copy of the same engine so it can reprice while you drag.
`tests/test_parity.py` checks that both copies agree to the cent.

**Reg T.** Legs are grouped by the strategy you tag them with. Long options are paid in full. Naked shorts use the
greater of 100% of the option value plus 15% (broad-based index and ETF) or 20% (equity) of the underlying, less any
out-of-the-money amount, or the option value plus 10% of the underlying (calls) or strike (puts). Credit spreads use
the strike width, debit spreads the net value, short straddles and strangles the greater side plus the other side's
value, and short iron condors the greater of the two widths. Reg T moves with price, vol and time because it is
built on option values and the underlying price.

**Portfolio margin.** Each underlying is revalued at five equally spaced moves down and five up across its range
(+6% / −8% for high-cap broad-based indexes and ETFs that track them, ±15% for single stocks), with the clock held
where it is. The requirement is the worst loss, but never less than $0.375 × multiplier per contract. Products are
not netted against each other, so SPX and SPY stand alone.

**What this leaves out.** House requirements, concentration add-ons, cross-product offsets, day-trading buying power,
and after-the-close exercise and assignment risk on physically settled options.
""")
