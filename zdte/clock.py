"""Intraday clock: converts minutes left in the session into a year fraction.

Two conventions:
  calendar  T = minutes / (365 * 24 * 60)
  trading   T = (share of today's variance still ahead) / 252

Trading time spreads the day's variance with a U-shaped weight so the open
and close carry more variance than midday:  w(x) = 1 + k * x^2, where x runs
from -1 at 9:30 to +1 at 4:00. k = 0 gives evenly spread (linear) time.
The ATM IV you enter must be annualized under the same convention.
"""
from datetime import datetime, time, timedelta, date

import numpy as np

OPEN = time(9, 30)
CLOSE = time(16, 0)
SESSION_MIN = 390.0
TRADING_DAYS = 252.0


def minutes_to_close(t: time) -> float:
    d = date(2000, 1, 1)
    m = (datetime.combine(d, CLOSE) - datetime.combine(d, t)).total_seconds() / 60.0
    return float(min(max(m, 0.0), SESSION_MIN))


def clock_at(minutes_left: float) -> time:
    d = date(2000, 1, 1)
    return (datetime.combine(d, CLOSE) - timedelta(minutes=float(minutes_left))).time()


def variance_share_remaining(minutes_left, u_shape: float):
    m = np.clip(np.asarray(minutes_left, dtype=float), 0.0, SESSION_MIN)
    x0 = 1.0 - 2.0 * m / SESSION_MIN
    k = float(u_shape)
    return ((1.0 - x0) + k * (1.0 - x0 ** 3) / 3.0) / (2.0 + 2.0 * k / 3.0)


def year_fraction(minutes_left, convention: str = "trading", u_shape: float = 1.5):
    m = np.clip(np.asarray(minutes_left, dtype=float), 0.0, SESSION_MIN)
    if convention == "calendar":
        return m / (365.0 * 1440.0)
    return variance_share_remaining(m, u_shape) / TRADING_DAYS
