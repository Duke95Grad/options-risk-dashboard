"""Ties clock, pricing and margin together for one underlying at one state."""
from dataclasses import dataclass

import numpy as np
import pandas as pd

from .clock import year_fraction, clock_at
from .pricing import bsm
from .regt import regt_requirement
from .pm import pm_requirement


@dataclass(frozen=True)
class ModelConfig:
    r: float = 0.04
    convention: str = "trading"   # "trading" or "calendar"
    u_shape: float = 1.5
    skew_mult: float = 1.0
    vol_overlay: float = 0.0      # PM house overlay, in vol (decimal), 0 = off


def leg_iv(prod, K, S, iv_atm, cfg):
    m = np.log(np.asarray(K, float) / np.asarray(S, float))
    return np.maximum(iv_atm + cfg.skew_mult * (prod.skew * m + prod.smile * m ** 2), 0.02)


def marks(prod, legs, S, iv_atm, minutes_left, cfg, vol_shift=0.0):
    """Per-unit marks. S may be a 1-D array (rows) to revalue across spots."""
    K = legs["strike"].to_numpy(float)
    is_call = (legs["type"] == "C").to_numpy()
    S_arr = np.asarray(S, float)
    S_b = S_arr[:, None] if S_arr.ndim == 1 else S_arr
    T = float(year_fraction(minutes_left, cfg.convention, cfg.u_shape))
    sig = leg_iv(prod, K, S_b, iv_atm + vol_shift, cfg)
    out = bsm(S_b, K, T, sig, cfg.r, prod.div_yield, is_call, prod.american)
    out["iv"] = np.broadcast_to(sig, out["price"].shape)
    return out


def position_value(prod, legs, S, iv_atm, minutes_left, cfg, vol_shift=0.0):
    qty = legs["qty"].to_numpy(float)
    p = marks(prod, legs, S, iv_atm, minutes_left, cfg, vol_shift)["price"]
    return (p * qty).sum(axis=-1) * prod.multiplier


def snapshot(prod, legs, S, iv_atm, minutes_left, cfg):
    """Everything the UI needs for one underlying at one (spot, vol, clock) state."""
    legs = legs.reset_index(drop=True)
    qty = legs["qty"].to_numpy(float)
    mult = prod.multiplier
    m = marks(prod, legs, S, iv_atm, minutes_left, cfg)
    m_next = marks(prod, legs, S, iv_atm, max(minutes_left - 60.0, 0.0), cfg)

    out = legs.copy()
    out["iv"] = m["iv"]
    out["theo"] = m["price"]
    out["delta"] = m["delta"]
    out["gamma"] = m["gamma"]
    out["value"] = m["price"] * qty * mult
    out["pnl_vs_fill"] = (m["price"] - legs["avg_price"].to_numpy(float)) * qty * mult
    out["delta_shares"] = m["delta"] * qty * mult
    out["gamma_shares_1pct"] = m["gamma"] * 0.01 * S * qty * mult
    out["theta_next_hr"] = (m_next["price"] - m["price"]) * qty * mult
    out["vega_per_pt"] = m["vega"] * qty * mult

    regt_total, regt_rows = regt_requirement(legs, m["price"], S, prod)
    base_value = float(out["value"].sum())
    pm = pm_requirement(
        lambda spots, dv: position_value(prod, legs, spots, iv_atm, minutes_left, cfg, dv),
        base_value, S, prod, float(np.abs(qty).sum()), cfg.vol_overlay)

    totals = {
        "value": base_value,
        "pnl_vs_fill": float(out["pnl_vs_fill"].sum()),
        "delta_shares": float(out["delta_shares"].sum()),
        "dollar_delta": float(out["delta_shares"].sum() * S),
        "gamma_shares_1pct": float(out["gamma_shares_1pct"].sum()),
        "theta_next_hr": float(out["theta_next_hr"].sum()),
        "vega_per_pt": float(out["vega_per_pt"].sum()),
        "contracts": float(np.abs(qty).sum()),
    }
    return {"legs": out, "totals": totals, "regt": regt_total, "regt_rows": regt_rows, "pm": pm}


def requirement_path(prod, legs, S, iv_atm, minutes_from, cfg, step=5.0):
    """Reg T and PM requirement at each step from minutes_from down to the close."""
    mins = np.arange(minutes_from, -1e-9, -step)
    if mins[-1] > 0:
        mins = np.append(mins, 0.0)
    rows = []
    for mn in mins:
        s = snapshot(prod, legs, S, iv_atm, float(mn), cfg)
        rows.append({"minutes_left": mn, "clock": clock_at(mn).strftime("%H:%M"),
                     "Reg T": s["regt"], "Portfolio margin": s["pm"]["requirement"]})
    return pd.DataFrame(rows)


def pnl_curve(prod, legs, spots, iv_atm, minutes_left, cfg, reference_value):
    return position_value(prod, legs, np.asarray(spots, float), iv_atm, minutes_left, cfg) - reference_value
