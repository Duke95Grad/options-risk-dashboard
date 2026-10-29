/* 0-DTE Lab engine, browser copy.
 * Mirrors zdte/clock.py, pricing.py, regt.py, pm.py and engine.py so the
 * simulator can reprice on every slider movement without a Streamlit rerun.
 * tests/test_parity.py checks that both copies produce the same numbers.
 */
(function (root) {
  "use strict";
  const SESSION = 390, TRADING_DAYS = 252, T_EPS = 1e-10, MIN_PER_CONTRACT = 0.375;

  // Cumulative normal, Hart (1968) double-precision algorithm as given by West (2005); error ~1e-14
  function ncdf(x) {
    const a = Math.abs(x);
    let c;
    if (a > 37) c = 0;
    else {
      const e = Math.exp(-a * a / 2);
      if (a < 7.07106781186547) {
        let b = 3.52624965998911e-02 * a + 0.700383064443688;
        b = b * a + 6.37396220353165; b = b * a + 33.912866078383; b = b * a + 112.079291497871;
        b = b * a + 221.213596169931; b = b * a + 220.206867912376;
        c = e * b;
        b = 8.83883476483184e-02 * a + 1.75566716318264;
        b = b * a + 16.064177579207; b = b * a + 86.7807322029461; b = b * a + 296.564248779674;
        b = b * a + 637.333633378831; b = b * a + 793.826512519948; b = b * a + 440.413735824752;
        c = c / b;
      } else {
        let b = a + 0.65; b = a + 4 / b; b = a + 3 / b; b = a + 2 / b; b = a + 1 / b;
        c = e / b / 2.506628274631;
      }
    }
    return x > 0 ? 1 - c : c;
  }
  const INV_SQRT_2PI = 1 / Math.sqrt(2 * Math.PI);

  function yearFraction(minutesLeft, cfg) {
    const m = Math.min(Math.max(minutesLeft, 0), SESSION);
    if (cfg.convention === "calendar") return m / (365 * 1440);
    const x0 = 1 - 2 * m / SESSION, k = cfg.u_shape;
    return ((1 - x0) + k * (1 - x0 ** 3) / 3) / (2 + 2 * k / 3) / TRADING_DAYS;
  }

  function bsm(S, K, T, sigma, r, q, isCall, american) {
    const intrinsic = isCall ? Math.max(S - K, 0) : Math.max(K - S, 0);
    if (!(T > T_EPS)) {
      return { price: intrinsic, delta: isCall ? (S > K ? 1 : 0) : (S < K ? -1 : 0), gamma: 0, vega: 0 };
    }
    const sig = Math.max(sigma, 1e-6), sT = Math.sqrt(T);
    const d1 = (Math.log(S / K) + (r - q + 0.5 * sig * sig) * T) / (sig * sT), d2 = d1 - sig * sT;
    const dfq = Math.exp(-q * T), dfr = Math.exp(-r * T);
    const N1 = ncdf(d1), N2 = ncdf(d2), pdf = INV_SQRT_2PI * Math.exp(-0.5 * d1 * d1);
    let price = isCall ? S * dfq * N1 - K * dfr * N2 : K * dfr * (1 - N2) - S * dfq * (1 - N1);
    price = Math.max(price, 0);
    if (american) price = Math.max(price, intrinsic);
    return {
      price,
      delta: isCall ? dfq * N1 : dfq * (N1 - 1),
      gamma: (dfq * pdf / (S * sig * sT)) || 0,
      vega: (S * dfq * pdf * sT / 100) || 0,
    };
  }

  function legIv(prod, K, S, atm, cfg) {
    const m = Math.log(K / S);
    return Math.max(atm + cfg.skew_mult * (prod.skew * m + prod.smile * m * m), 0.02);
  }

  function marks(prod, legs, S, atm, minutes, cfg, volShift) {
    const T = yearFraction(minutes, cfg), dv = volShift || 0;
    return legs.map((l) => {
      const iv = legIv(prod, l.strike, S, atm + dv, cfg);
      const b = bsm(S, l.strike, T, iv, cfg.r, prod.div_yield, l.type === "C", prod.american);
      b.iv = iv;
      return b;
    });
  }

  function positionValue(prod, legs, S, atm, minutes, cfg, volShift) {
    const m = marks(prod, legs, S, atm, minutes, cfg, volShift);
    let v = 0;
    for (let i = 0; i < legs.length; i++) v += m[i].price * legs[i].qty;
    return v * prod.multiplier;
  }

  // ---------------------------------------------------------------- Reg T
  function nakedShort(cp, K, price, S, prod, n) {
    let per;
    if (cp === "C") per = Math.max(price + prod.regt_pct * S - Math.max(K - S, 0), price + prod.regt_min_pct * S);
    else per = Math.max(price + prod.regt_pct * S - Math.max(S - K, 0), price + prod.regt_min_pct * K);
    return per * prod.multiplier * n;
  }
  const legValue = (l, prod) => l.price * prod.multiplier * Math.abs(l.qty);
  function single(l, S, prod) {
    if (l.qty > 0) return [legValue(l, prod), "Long option, paid in full"];
    return [nakedShort(l.type, l.strike, l.price, S, prod, Math.abs(l.qty)), "Naked short"];
  }
  const isVertical = (a, b) => a.type === b.type && a.qty === -b.qty && a.strike !== b.strike;
  function vertical(a, b, S, prod) {
    const [sh, lg] = a.qty < 0 ? [a, b] : [b, a];
    const n = Math.abs(sh.qty);
    const credit = sh.type === "C" ? sh.strike < lg.strike : sh.strike > lg.strike;
    if (credit) {
      const width = Math.abs(sh.strike - lg.strike) * prod.multiplier * n;
      const naked = nakedShort(sh.type, sh.strike, sh.price, S, prod, n) + legValue(lg, prod);
      return [Math.min(width, naked), "Credit spread: strike width", width];
    }
    return [Math.max(legValue(lg, prod) - legValue(sh, prod), 0), "Debit spread: net value paid in full", 0];
  }
  function fallback(legs, S, prod) {
    return [legs.reduce((s, l) => s + single(l, S, prod)[0], 0),
      "Not a recognized strategy: each leg margined on its own"];
  }
  function strategyRequirement(legs, S, prod) {
    if (legs.length === 1) return single(legs[0], S, prod);
    if (legs.length === 2) {
      const [a, b] = legs;
      if (isVertical(a, b)) { const v = vertical(a, b, S, prod); return [v[0], v[1]]; }
      if (a.type !== b.type && a.qty < 0 && b.qty < 0 && a.qty === b.qty) {
        const [c, p] = a.type === "C" ? [a, b] : [b, a];
        const q = Math.abs(c.qty);
        const nc = nakedShort("C", c.strike, c.price, S, prod, q), np = nakedShort("P", p.strike, p.price, S, prod, q);
        const req = nc >= np ? nc + legValue(p, prod) : np + legValue(c, prod);
        const shape = c.strike === p.strike ? "straddle" : "strangle";
        return [req, `Short ${shape}: greater side + value of the other`];
      }
      return fallback(legs, S, prod);
    }
    if (legs.length === 4) {
      const calls = legs.filter((l) => l.type === "C"), puts = legs.filter((l) => l.type === "P");
      if (calls.length === 2 && puts.length === 2 && isVertical(...calls) && isVertical(...puts) &&
          Math.abs(calls[0].qty) === Math.abs(puts[0].qty)) {
        const vc = vertical(calls[0], calls[1], S, prod), vp = vertical(puts[0], puts[1], S, prod);
        if (vc[2] > 0 && vp[2] > 0) return [Math.max(vc[2], vp[2]), "Short iron condor: greater of the two spread widths"];
        return [vc[0] + vp[0], "Two verticals margined separately"];
      }
    }
    return fallback(legs, S, prod);
  }
  function regtRequirement(legs, prices, S, prod) {
    const groups = new Map();
    legs.forEach((l, i) => {
      if (!groups.has(l.strategy_id)) groups.set(l.strategy_id, []);
      groups.get(l.strategy_id).push({ ...l, price: prices[i] });
    });
    const rows = [];
    let total = 0;
    for (const [sid, g] of groups) {
      const [req, method] = strategyRequirement(g, S, prod);
      rows.push({ strategy_id: sid, strategy: g[0].strategy, method, requirement: req });
      total += req;
    }
    return [total, rows];
  }

  // ---------------------------------------------------------------- PM
  function pmPoints(down, up, perSide) {
    const n = perSide || 5, pts = [];
    for (let i = n; i >= 1; i--) pts.push(-down * i / n);
    pts.push(0);
    for (let i = 1; i <= n; i++) pts.push(up * i / n);
    return pts;
  }
  function pmRequirement(prod, legs, S, atm, minutes, cfg, baseValue, gross) {
    const pts = pmPoints(prod.pm_down, prod.pm_up);
    const shocks = cfg.vol_overlay > 0 ? [0, -cfg.vol_overlay, cfg.vol_overlay] : [0];
    const pnl = pts.map((x) => Math.min(...shocks.map((dv) =>
      positionValue(prod, legs, S * (1 + x), atm, minutes, cfg, dv) - baseValue)));
    let worstIdx = 0;
    pnl.forEach((v, i) => { if (v < pnl[worstIdx]) worstIdx = i; });
    const worst = pnl[worstIdx], minimum = MIN_PER_CONTRACT * prod.multiplier * gross;
    return { points: pts, pnl, worst_idx: worstIdx, scenario_loss: Math.max(-worst, 0),
             minimum, requirement: Math.max(-worst, minimum) };
  }

  // ---------------------------------------------------------------- snapshot
  function snapshot(prod, legs, S, atm, minutes, cfg) {
    const mult = prod.multiplier;
    const m = marks(prod, legs, S, atm, minutes, cfg);
    const mNext = marks(prod, legs, S, atm, Math.max(minutes - 60, 0), cfg);
    const out = legs.map((l, i) => ({
      ...l,
      iv: m[i].iv, theo: m[i].price, delta: m[i].delta, gamma: m[i].gamma,
      value: m[i].price * l.qty * mult,
      pnl_vs_fill: (m[i].price - l.avg_price) * l.qty * mult,
      delta_shares: m[i].delta * l.qty * mult,
      gamma_shares_1pct: m[i].gamma * 0.01 * S * l.qty * mult,
      theta_next_hr: (mNext[i].price - m[i].price) * l.qty * mult,
      vega_per_pt: m[i].vega * l.qty * mult,
    }));
    const sum = (k) => out.reduce((s, r) => s + r[k], 0);
    const [regt, regtRows] = regtRequirement(legs, m.map((x) => x.price), S, prod);
    const value = sum("value");
    const gross = legs.reduce((s, l) => s + Math.abs(l.qty), 0);
    const pm = pmRequirement(prod, legs, S, atm, minutes, cfg, value, gross);
    return {
      legs: out, regt, regt_rows: regtRows, pm,
      totals: {
        value, pnl_vs_fill: sum("pnl_vs_fill"), delta_shares: sum("delta_shares"),
        dollar_delta: sum("delta_shares") * S, gamma_shares_1pct: sum("gamma_shares_1pct"),
        theta_next_hr: sum("theta_next_hr"), vega_per_pt: sum("vega_per_pt"), contracts: gross,
      },
    };
  }

  function requirementPath(prod, legs, S, atm, minutesFrom, cfg, step) {
    const st = step || 5, rows = [];
    let mn = minutesFrom;
    for (; mn > -1e-9; mn -= st) {
      const s = snapshot(prod, legs, S, atm, mn, cfg);
      rows.push({ minutes_left: mn, regt: s.regt, pm: s.pm.requirement });
    }
    if (rows.length && rows[rows.length - 1].minutes_left > 0) {
      const s = snapshot(prod, legs, S, atm, 0, cfg);
      rows.push({ minutes_left: 0, regt: s.regt, pm: s.pm.requirement });
    }
    return rows;
  }

  const api = { yearFraction, bsm, marks, positionValue, regtRequirement, pmPoints, pmRequirement,
                snapshot, requirementPath, SESSION };
  root.ZDTE = api;
  if (typeof module !== "undefined" && module.exports) module.exports = api;
})(typeof window !== "undefined" ? window : globalThis);
