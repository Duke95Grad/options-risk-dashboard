"""Vectorized Black-Scholes-Merton with continuous dividend yield, safe as T -> 0."""
import math

import numpy as np

try:
    from scipy.special import ndtr as _ndtr
except Exception:  # scipy not installed: fall back to math.erf
    _erf = np.vectorize(math.erf, otypes=[float])

    def _ndtr(x):
        return 0.5 * (1.0 + _erf(np.asarray(x, dtype=float) / math.sqrt(2.0)))

_INV_SQRT_2PI = 1.0 / math.sqrt(2.0 * math.pi)
T_EPS = 1e-10  # below this the option is treated as expired (intrinsic value)


def bsm(S, K, T, sigma, r, q, is_call, american=False):
    """Returns price, delta, gamma and vega (per 1 vol point) per unit of underlying."""
    S, K, T, sigma, is_call = np.broadcast_arrays(
        np.asarray(S, float), np.asarray(K, float), np.asarray(T, float),
        np.asarray(sigma, float), np.asarray(is_call, bool))
    live = T > T_EPS
    Ts = np.where(live, T, 1.0)
    sig = np.maximum(sigma, 1e-6)
    sqrtT = np.sqrt(Ts)
    with np.errstate(divide="ignore", invalid="ignore", over="ignore"):
        d1 = (np.log(S / K) + (r - q + 0.5 * sig ** 2) * Ts) / (sig * sqrtT)
        d2 = d1 - sig * sqrtT
        dfq, dfr = np.exp(-q * Ts), np.exp(-r * Ts)
        Nd1, Nd2 = _ndtr(d1), _ndtr(d2)
        pdf = _INV_SQRT_2PI * np.exp(-0.5 * d1 ** 2)
        call = S * dfq * Nd1 - K * dfr * Nd2
        put = K * dfr * (1.0 - Nd2) - S * dfq * (1.0 - Nd1)
        gamma = dfq * pdf / (S * sig * sqrtT)
        vega = S * dfq * pdf * sqrtT / 100.0

    intrinsic = np.where(is_call, np.maximum(S - K, 0.0), np.maximum(K - S, 0.0))
    model = np.maximum(np.where(is_call, call, put), 0.0)
    if american:
        model = np.maximum(model, intrinsic)
    delta_live = np.where(is_call, dfq * Nd1, dfq * (Nd1 - 1.0))
    delta_exp = np.where(is_call, (S > K).astype(float), -(S < K).astype(float))

    return {
        "price": np.where(live, model, intrinsic),
        "delta": np.where(live, delta_live, delta_exp),
        "gamma": np.where(live, np.nan_to_num(gamma), 0.0),
        "vega": np.where(live, np.nan_to_num(vega), 0.0),
    }
