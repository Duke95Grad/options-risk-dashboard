"""0-DTE Lab: price and stress Reg T vs. portfolio-margin requirements for
same-day-expiring index, ETF and single-stock options."""
import sys
from datetime import date, datetime, time, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from zdte.clock import CLOSE, OPEN, clock_at, minutes_to_close
from zdte.engine import ModelConfig, pnl_curve, requirement_path, snapshot
from zdte.positions import dummy_account
from zdte.products import PRODUCTS

try:
    st.set_page_config(page_title="0-DTE Lab", page_icon="⏱️", layout="wide")
except Exception:
    pass

REGT_COLOR, PM_COLOR = "#2E6FBA", "#C2582B"
D0 = date(2000, 1, 1)


def money(x):
    return f"-${abs(x):,.0f}" if x < 0 else f"${x:,.0f}"


def stretch(fn, *args, **kwargs):
    """Full-width element on both newer (width="stretch") and older Streamlit versions."""
    try:
        return fn(*args, width="stretch", **kwargs)
    except Exception:
        return fn(*args, use_container_width=True, **kwargs)


def show_fig(fig):
    fig.update_layout(margin=dict(l=10, r=10, t=40, b=10), height=360,
                      legend=dict(orientation="h", yanchor="bottom", y=1.02, x=0))
    stretch(st.plotly_chart, fig)


def show_table(df, fmt):
    stretch(st.dataframe, df.style.format(fmt, na_rep=""), hide_index=True)


def clock_dt(mins_left):
    return datetime.combine(D0, clock_at(mins_left))


def add_minutes(t, mins):
    return (datetime.combine(D0, t) + timedelta(minutes=mins)).time()


# ---------------------------------------------------------------- sidebar
with st.sidebar:
    st.header("Clock and model")
    as_of = st.slider("Current time (ET)", min_value=OPEN, max_value=time(15, 59),
                      value=time(11, 0), step=timedelta(minutes=1),
                      help="Where the trading day stands now. Everything on the page is valued at this time "
                           "unless you move the simulated time on a security.")
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
    st.caption("Dummy positions and market data. Margin parameters are FINRA 4210 customer minimums with "
               "no house add-ons; edit them in zdte/products.py.")

cfg = ModelConfig(r=r, convention="calendar" if conv_label.startswith("Calendar") else "trading",
                  u_shape=u_shape, skew_mult=skew_mult, vol_overlay=overlay / 100.0)
mins_now = minutes_to_close(as_of)
account = dummy_account(ModelConfig(r=r, convention=cfg.convention, u_shape=u_shape, skew_mult=skew_mult))
symbols = list(dict.fromkeys(account["underlying"]))

# ---------------------------------------------------------------- header
st.title("0-DTE Lab")
st.write(f"Same-day expirations, valued at **{as_of.strftime('%H:%M')} ET** with "
         f"**{int(mins_now // 60)}h {int(mins_now % 60)}m** to the close.")

tab_acct, tab_sim, tab_notes = st.tabs(["Account", "Simulate a security", "How the lab works"])

# ---------------------------------------------------------------- account
with tab_acct:
    rows, snaps = [], {}
    for sym in symbols:
        prod, legs = PRODUCTS[sym], account[account.underlying == sym]
        s = snapshot(prod, legs, prod.spot, prod.iv, mins_now, cfg)
        snaps[sym] = s
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
              f"{(tot_pm / tot_regt - 1) * 100:+.0f}%" if tot_regt else None, delta_color="inverse")
    c4.metric("Theta, next hour", money(summary["Theta next hr"].sum()))

    show_table(summary, {"Spot": "{:,.2f}", "ATM IV": "{:.1f}%", "Contracts": "{:,.0f}",
                         "Delta $": money, "Gamma (Δ sh / 1%)": "{:,.0f}", "Theta next hr": money,
                         "Vega / pt": money, "Reg T": money, "PM": money, "PM vs Reg T": money})

    left, right = st.columns(2)
    with left:
        fig = go.Figure()
        fig.add_bar(name="Reg T", x=summary["Underlying"], y=summary["Reg T"], marker_color=REGT_COLOR)
        fig.add_bar(name="Portfolio margin", x=summary["Underlying"], y=summary["PM"], marker_color=PM_COLOR)
        fig.update_layout(title="Requirement by underlying", barmode="group", yaxis_tickprefix="$")
        show_fig(fig)
    with right:
        paths = []
        for sym in symbols:
            prod = PRODUCTS[sym]
            paths.append(requirement_path(prod, account[account.underlying == sym], prod.spot, prod.iv,
                                          mins_now, cfg, step=10.0).set_index("minutes_left")[["Reg T", "Portfolio margin"]])
        total_path = sum(paths)
        fig = go.Figure()
        xs = [clock_dt(m) for m in total_path.index]
        fig.add_scatter(name="Reg T", x=xs, y=total_path["Reg T"], line_color=REGT_COLOR)
        fig.add_scatter(name="Portfolio margin", x=xs, y=total_path["Portfolio margin"], line_color=PM_COLOR)
        fig.update_layout(title="Account requirement from now to the close (spot and vol unchanged)",
                          yaxis_tickprefix="$", xaxis_title="ET", xaxis_tickformat="%H:%M")
        show_fig(fig)

    with st.expander("Positions"):
        show_table(account[["underlying", "strategy", "option", "qty", "avg_price"]].rename(columns={
            "underlying": "Underlying", "strategy": "Strategy", "option": "Option", "qty": "Qty",
            "avg_price": "Avg price"}), {"Avg price": "{:,.2f}"})

# ---------------------------------------------------------------- simulator
with tab_sim:
    sym = st.selectbox("Security", symbols, format_func=lambda s: f"{PRODUCTS[s].label}, {PRODUCTS[s].name}")
    prod, legs = PRODUCTS[sym], account[account.underlying == sym].reset_index(drop=True)
    k_ds, k_dv, k_t = f"ds_{sym}", f"dv_{sym}", f"t_{sym}"

    st.session_state.setdefault(k_ds, 0.0)
    st.session_state.setdefault(k_dv, 0.0)
    st.session_state.setdefault(k_t, as_of)
    if st.session_state[k_t] < as_of:          # clock moved past the simulated time
        st.session_state[k_t] = as_of

    def _reset(ds=k_ds, dv=k_dv, kt=k_t, now=as_of):
        st.session_state[ds], st.session_state[dv], st.session_state[kt] = 0.0, 0.0, now

    rng = 15.0 if prod.kind == "equity" else 10.0
    c1, c2, c3, c4 = st.columns([3, 3, 3, 1])
    ds = c1.slider("Underlying move (%)", -rng, rng, step=0.05, key=k_ds,
                   help="Moves the underlying from today's spot. Every leg is repriced at the new level.")
    dv = c2.slider("ATM vol change (vol pts)", -10.0, 30.0, step=0.5, key=k_dv,
                   help="Shifts the whole vol curve up or down by this many points.")
    t_sim = c3.slider("Simulated time (ET)", min_value=as_of, max_value=CLOSE, step=timedelta(minutes=1),
                      key=k_t, help="Rolls the clock forward toward the 4:00 PM close.")
    c4.write("")
    stretch(c4.button, "Reset", on_click=_reset)

    S_now, iv_now = prod.spot, prod.iv
    S_sim, iv_sim = prod.spot * (1 + ds / 100.0), max(prod.iv + dv / 100.0, 0.02)
    mins_sim = minutes_to_close(t_sim)
    now, sim = snaps[sym], snapshot(prod, legs, S_sim, iv_sim, mins_sim, cfg)

    st.caption(f"{prod.exercise} · {prod.settlement} · multiplier {prod.multiplier} · "
               f"Reg T naked rate {prod.regt_pct:.0%} (minimum {prod.regt_min_pct:.0%}) · PM range: {prod.pm_class}")

    m1, m2, m3, m4, m5 = st.columns(5)
    m1.metric("Spot", f"{S_sim:,.2f}", f"{S_sim - S_now:+,.2f}" if ds else None)
    m2.metric("ATM IV", f"{iv_sim * 100:.1f}%", f"{dv:+.1f} pts" if dv else None)
    m3.metric("Reg T", money(sim["regt"]),
              money(sim["regt"] - now["regt"]) if abs(sim["regt"] - now["regt"]) > 0.5 else None,
              delta_color="inverse")
    m4.metric("Portfolio margin", money(sim["pm"]["requirement"]),
              money(sim["pm"]["requirement"] - now["pm"]["requirement"])
              if abs(sim["pm"]["requirement"] - now["pm"]["requirement"]) > 0.5 else None,
              delta_color="inverse")
    m5.metric("P&L vs now", money(sim["totals"]["value"] - now["totals"]["value"]),
              f"vs fills {money(sim['totals']['pnl_vs_fill'])}", delta_color="off")

    # legs
    L = sim["legs"]
    legs_tbl = pd.DataFrame({
        "Strategy": L["strategy"], "Option": L["option"], "Qty": L["qty"], "Avg": L["avg_price"],
        "Theo now": now["legs"]["theo"].to_numpy(), "Theo sim": L["theo"], "IV sim": L["iv"] * 100,
        "Delta": L["delta"], "Delta sh": L["delta_shares"], "Gamma (Δ sh / 1%)": L["gamma_shares_1pct"],
        "Theta next hr": L["theta_next_hr"], "Vega / pt": L["vega_per_pt"],
        "P&L vs now": L["value"].to_numpy() - now["legs"]["value"].to_numpy(), "P&L vs fill": L["pnl_vs_fill"]})
    show_table(legs_tbl, {"Avg": "{:,.2f}", "Theo now": "{:,.2f}", "Theo sim": "{:,.2f}", "IV sim": "{:.1f}%",
                          "Delta": "{:+.3f}", "Delta sh": "{:+,.0f}", "Gamma (Δ sh / 1%)": "{:+,.0f}",
                          "Theta next hr": money, "Vega / pt": money, "P&L vs now": money, "P&L vs fill": money})

    t = sim["totals"]
    g1, g2, g3, g4, g5 = st.columns(5)
    g1.metric("Net delta (shares)", f"{t['delta_shares']:+,.0f}")
    g2.metric("Delta $", money(t["dollar_delta"]))
    g3.metric("Gamma (Δ sh / 1%)", f"{t['gamma_shares_1pct']:+,.0f}")
    g4.metric("Theta next hr" if mins_sim >= 60 else "Theta to close", money(t["theta_next_hr"]))
    g5.metric("Vega / vol pt", money(t["vega_per_pt"]))

    # charts
    left, right = st.columns(2)
    with left:
        lo, hi = S_now * (1 - 1.5 * prod.pm_down), S_now * (1 + 1.5 * prod.pm_up)
        lo, hi = min(lo, S_sim * 0.99), max(hi, S_sim * 1.01)
        spots = np.linspace(lo, hi, 301)
        ref = now["totals"]["value"]
        fig = go.Figure()
        fig.add_vrect(x0=S_now * (1 - prod.pm_down), x1=S_now * (1 + prod.pm_up), fillcolor=PM_COLOR,
                      opacity=0.07, line_width=0, annotation_text="PM range", annotation_position="top left")
        fig.add_scatter(name=f"Now ({as_of.strftime('%H:%M')})", x=spots,
                        y=pnl_curve(prod, legs, spots, iv_now, mins_now, cfg, ref), line_color=REGT_COLOR)
        if mins_sim != mins_now or dv:
            fig.add_scatter(name=f"Simulated ({t_sim.strftime('%H:%M')}, {iv_sim * 100:.1f}% vol)", x=spots,
                            y=pnl_curve(prod, legs, spots, iv_sim, mins_sim, cfg, ref), line_color=PM_COLOR)
        fig.add_scatter(name="At expiry", x=spots, y=pnl_curve(prod, legs, spots, iv_now, 0.0, cfg, ref),
                        line=dict(color="gray", dash="dot"))
        fig.add_vline(x=S_now, line_dash="dash", line_color="gray")
        if ds:
            fig.add_vline(x=S_sim, line_color=PM_COLOR, annotation_text="Simulated spot")
        fig.update_layout(title="P&L vs. underlying price (from current value)", xaxis_title=sym,
                          yaxis_tickprefix="$")
        show_fig(fig)
    with right:
        pm = sim["pm"]
        pts = pm["points"] * 100
        colors = [PM_COLOR if i == pm["worst_idx"] else "#9AA5B1" for i in range(len(pts))]
        fig = go.Figure(go.Bar(x=[f"{p:+.1f}%" for p in pts], y=pm["pnl"], marker_color=colors))
        if pm["minimum"] > pm["scenario_loss"]:
            fig.add_hline(y=-pm["minimum"], line_dash="dot",
                          annotation_text=f"Per-contract minimum {money(pm['minimum'])}")
        fig.update_layout(title=f"PM price points at the simulated state; worst loss {money(-pm['pnl'].min())}",
                          yaxis_tickprefix="$", xaxis_title="Move in underlying")
        show_fig(fig)

    path = requirement_path(prod, legs, S_sim, iv_sim, minutes_to_close(as_of), cfg, step=5.0)
    fig = go.Figure()
    xs = [clock_dt(m) for m in path["minutes_left"]]
    fig.add_scatter(name="Reg T", x=xs, y=path["Reg T"], line_color=REGT_COLOR)
    fig.add_scatter(name="Portfolio margin", x=xs, y=path["Portfolio margin"], line_color=PM_COLOR)
    if t_sim != as_of:
        fig.add_vline(x=datetime.combine(D0, t_sim), line_dash="dash", line_color="gray")
    fig.update_layout(title="Requirement from now to the close at the simulated price and vol",
                      yaxis_tickprefix="$", xaxis_title="ET", xaxis_tickformat="%H:%M")
    show_fig(fig)

    st.subheader("Reg T by strategy")
    reg = pd.DataFrame(sim["regt_rows"])
    reg["Now"] = [r["requirement"] for r in now["regt_rows"]]
    show_table(reg.rename(columns={"strategy": "Strategy", "method": "How it's margined",
                                   "requirement": "Simulated"})[["Strategy", "How it's margined", "Now", "Simulated"]],
               {"Now": money, "Simulated": money})

# ---------------------------------------------------------------- notes
with tab_notes:
    st.markdown("""
**Time.** Each option's time to expiry is measured in minutes to the 4:00 PM ET close, then turned into a year
fraction. In trading time, the remaining share of today's variance is divided by 252, and the open and close carry
more of it than midday. In calendar time, raw minutes are divided by the minutes in a 365-day year. The same IV
gives very different prices under the two, so match the convention to how the IV was quoted. As time reaches zero,
options are valued at intrinsic value and gamma and vega go to zero.

**Pricing.** Black-Scholes-Merton with a continuous dividend yield and a simple skew around the ATM vol. American
options (ETFs and single stocks) are floored at intrinsic value; early exercise on the expiration day is otherwise
ignored.

**Reg T.** Legs are grouped by the strategy you tag them with. Long options are paid in full. Naked shorts use the
greater of 100% of the option value plus 15% (broad-based index and ETF) or 20% (equity) of the underlying, less any
out-of-the-money amount, or the option value plus 10% of the underlying (calls) or strike (puts). Credit spreads use
the strike width, debit spreads the net value, short straddles and strangles the greater side plus the other side's
value, and short iron condors the greater of the two widths. Reg T moves with price, vol and time because it is
built on option values and the underlying price.

**Portfolio margin.** Each underlying is revalued at five equally spaced moves down and five up across its range
(+6% / -8% for high-cap broad-based indexes and ETFs that track them, ±15% for single stocks), with the clock held
where it is. The requirement is the worst loss, but never less than $0.375 × multiplier per contract. Products are
not netted against each other, so SPX and SPY stand alone.

**What this leaves out.** House requirements, concentration add-ons, cross-product offsets, day-trading buying power,
and after-the-close exercise and assignment risk on physically settled options.
""")
