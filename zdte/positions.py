"""Dummy 0-DTE account. Fills are model prices at 9:35 ET, a touch off today's spot."""
import pandas as pd

from .engine import ModelConfig, marks
from .products import PRODUCTS

_LEGS = [
    # underlying, strategy_id, strategy, type, strike, qty (signed contracts)
    ("SPX", "SPX-1", "Short iron condor", "P", 6780, 10),
    ("SPX", "SPX-1", "Short iron condor", "P", 6800, -10),
    ("SPX", "SPX-1", "Short iron condor", "C", 6900, -10),
    ("SPX", "SPX-1", "Short iron condor", "C", 6920, 10),
    ("SPX", "SPX-2", "Long call", "C", 6850, 2),
    ("XSP", "XSP-1", "Short put spread", "P", 680, -20),
    ("XSP", "XSP-1", "Short put spread", "P", 675, 20),
    ("NDX", "NDX-1", "Short strangle", "P", 24700, -1),
    ("NDX", "NDX-1", "Short strangle", "C", 25300, -1),
    ("SPY", "SPY-1", "Short straddle", "C", 683, -10),
    ("SPY", "SPY-1", "Short straddle", "P", 683, -10),
    ("QQQ", "QQQ-1", "Long call spread", "C", 610, 15),
    ("QQQ", "QQQ-1", "Long call spread", "C", 615, -15),
    ("TSLA", "TSLA-1", "Short put", "P", 440, -5),
    ("TSLA", "TSLA-2", "Long call", "C", 470, 5),
    ("NKE", "NKE-1", "Short call spread", "C", 71, -10),
    ("NKE", "NKE-1", "Short call spread", "C", 72, 10),
]


def dummy_account(cfg: ModelConfig = ModelConfig()) -> pd.DataFrame:
    df = pd.DataFrame(_LEGS, columns=["underlying", "strategy_id", "strategy", "type", "strike", "qty"])
    df["option"] = [f"{PRODUCTS[u].option_root} {k:g}{t}" for u, k, t in zip(df.underlying, df.strike, df.type)]
    fills = []
    for u, g in df.groupby("underlying", sort=False):
        prod = PRODUCTS[u]
        p = marks(prod, g, prod.spot * 0.9985, prod.iv, 385.0, cfg)["price"]
        fills.extend(zip(g.index, p))
    for i, p in fills:
        df.loc[i, "avg_price"] = round(float(p), 2)
    return df
