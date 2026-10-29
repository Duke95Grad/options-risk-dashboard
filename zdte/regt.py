"""Reg T / FINRA 4210(f) strategy-based requirements for one underlying.

Legs are grouped by strategy_id (the lab's deterministic pairing: you tag
which legs belong together). Recognized shapes, all same expiry:
  single long            option value, paid in full (no loan value)
  single short           naked formula
  vertical, credit       lesser of strike width or naked short + long value
  vertical, debit        net value, paid in full
  short straddle/strangle  greater naked side + value of the other side
  short iron condor      greater of the two spread widths
Anything else (or unequal quantities) is margined leg by leg.
"""


def naked_short(cp, K, price, S, prod, contracts):
    if cp == "C":
        otm = max(K - S, 0.0)
        per = max(price + prod.regt_pct * S - otm, price + prod.regt_min_pct * S)
    else:
        otm = max(S - K, 0.0)
        per = max(price + prod.regt_pct * S - otm, price + prod.regt_min_pct * K)
    return per * prod.multiplier * contracts


def _value(leg, prod):
    return leg["price"] * prod.multiplier * abs(leg["qty"])


def _single(leg, S, prod):
    if leg["qty"] > 0:
        return _value(leg, prod), "Long option, paid in full"
    return naked_short(leg["type"], leg["strike"], leg["price"], S, prod, abs(leg["qty"])), "Naked short"


def _is_vertical(a, b):
    return a["type"] == b["type"] and a["qty"] == -b["qty"] and a["strike"] != b["strike"]


def _vertical(a, b, S, prod):
    short, long_ = (a, b) if a["qty"] < 0 else (b, a)
    n = abs(short["qty"])
    credit = (short["strike"] < long_["strike"]) if short["type"] == "C" else (short["strike"] > long_["strike"])
    if credit:
        width = abs(short["strike"] - long_["strike"]) * prod.multiplier * n
        naked = naked_short(short["type"], short["strike"], short["price"], S, prod, n) + _value(long_, prod)
        return min(width, naked), "Credit spread: strike width", width
    return max(_value(long_, prod) - _value(short, prod), 0.0), "Debit spread: net value paid in full", 0.0


def _fallback(legs, S, prod):
    return sum(_single(l, S, prod)[0] for l in legs), "Not a recognized strategy: each leg margined on its own"


def strategy_requirement(legs, S, prod):
    """legs: list of dicts with type, strike, qty, price. Returns (requirement, method)."""
    n = len(legs)
    if n == 1:
        return _single(legs[0], S, prod)

    if n == 2:
        a, b = legs
        if _is_vertical(a, b):
            req, method, _ = _vertical(a, b, S, prod)
            return req, method
        if a["type"] != b["type"] and a["qty"] < 0 and b["qty"] < 0 and a["qty"] == b["qty"]:
            c, p = (a, b) if a["type"] == "C" else (b, a)
            q = abs(c["qty"])
            nc = naked_short("C", c["strike"], c["price"], S, prod, q)
            np_ = naked_short("P", p["strike"], p["price"], S, prod, q)
            if nc >= np_:
                req = nc + _value(p, prod)
            else:
                req = np_ + _value(c, prod)
            shape = "straddle" if c["strike"] == p["strike"] else "strangle"
            return req, f"Short {shape}: greater side + value of the other"
        return _fallback(legs, S, prod)

    if n == 4:
        calls = [l for l in legs if l["type"] == "C"]
        puts = [l for l in legs if l["type"] == "P"]
        if len(calls) == 2 and len(puts) == 2 and _is_vertical(*calls) and _is_vertical(*puts) \
                and abs(calls[0]["qty"]) == abs(puts[0]["qty"]):
            rc, mc, wc = _vertical(*calls, S, prod)
            rp, mp, wp = _vertical(*puts, S, prod)
            if wc > 0 and wp > 0:
                return max(wc, wp), "Short iron condor: greater of the two spread widths"
            return rc + rp, "Two verticals margined separately"
    return _fallback(legs, S, prod)


def regt_requirement(legs_df, prices, S, prod):
    """Returns (total, rows) where rows hold one entry per strategy."""
    df = legs_df.copy()
    df["price"] = prices
    rows, total = [], 0.0
    for sid, g in df.groupby("strategy_id", sort=False):
        legs = g[["type", "strike", "qty", "price"]].to_dict("records")
        req, method = strategy_requirement(legs, S, prod)
        rows.append({"strategy_id": sid, "strategy": g["strategy"].iloc[0], "method": method, "requirement": req})
        total += req
    return total, rows
