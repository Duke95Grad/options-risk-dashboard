"""FINRA 4210(g) portfolio margin for one underlying (no cross-product offsets).

Every position is revalued at ten equally spaced price moves inside the
product's range (five down, five up) plus the current price, holding the
clock where it is. The requirement is the largest loss across those points,
floored at $0.375 x multiplier per option contract held.
An optional house overlay also shocks volatility up and down at each point.
"""
import numpy as np

MIN_PER_CONTRACT = 0.375


def pm_points(down: float, up: float, per_side: int = 5):
    dn = -down * np.arange(per_side, 0, -1) / per_side
    upm = up * np.arange(1, per_side + 1) / per_side
    return np.concatenate([dn, [0.0], upm])


def pm_requirement(value_fn, base_value, S, prod, gross_contracts, vol_overlay=0.0):
    """value_fn(spots, vol_shift) -> position value at each spot (array)."""
    pts = pm_points(prod.pm_down, prod.pm_up)
    shocks = [0.0] + ([-vol_overlay, vol_overlay] if vol_overlay > 0 else [])
    pnl = np.min(np.vstack([value_fn(S * (1.0 + pts), dv) - base_value for dv in shocks]), axis=0)
    floor = MIN_PER_CONTRACT * prod.multiplier * gross_contracts
    worst = float(pnl.min())
    return {
        "points": pts,
        "pnl": pnl,
        "worst_idx": int(np.argmin(pnl)),
        "scenario_loss": max(-worst, 0.0),
        "minimum": floor,
        "requirement": max(-worst, floor),
    }
