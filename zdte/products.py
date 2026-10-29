"""Product specs for the 0-DTE Lab.

Margin parameters are the FINRA Rule 4210 / Reg T customer minimums the lab
uses as defaults. They are deliberately editable here: confirm them against
your firm's margin configuration before relying on any number.

Spot, IV, dividend yield and skew values are dummy market data.
"""
from dataclasses import dataclass


@dataclass(frozen=True)
class Product:
    symbol: str          # underlying shown in the UI
    option_root: str     # root of the 0-DTE series
    name: str
    kind: str            # "index", "etf" or "equity"
    multiplier: int
    exercise: str        # "European" or "American"
    settlement: str
    regt_pct: float      # naked-short % of underlying (15% broad-based, 20% other)
    pm_down: float       # PM down-move range, e.g. 0.08 = -8%
    pm_up: float         # PM up-move range
    pm_class: str
    spot: float          # dummy
    iv: float            # dummy ATM implied vol (annualized)
    div_yield: float     # continuous dividend yield
    skew: float          # vol change per unit log-moneyness (negative = put skew)
    smile: float         # curvature on log-moneyness squared
    regt_min_pct: float = 0.10

    @property
    def american(self) -> bool:
        return self.exercise == "American"

    @property
    def label(self) -> str:
        return self.symbol if self.option_root == self.symbol else f"{self.symbol} ({self.option_root})"


_HIGH_CAP = "High-cap broad-based index: +6% / -8%"
_EQUITY = "Equity / narrow-based: +/-15%"

PRODUCTS = {
    p.symbol: p
    for p in [
        Product("SPX", "SPXW", "S&P 500 Index", "index", 100, "European",
                "Cash, PM-settled at the 4:00 PM ET close", 0.15, 0.08, 0.06, _HIGH_CAP,
                6850.0, 0.14, 0.013, -2.5, 15.0),
        Product("XSP", "XSP", "Mini-S&P 500 Index", "index", 100, "European",
                "Cash, PM-settled at the 4:00 PM ET close", 0.15, 0.08, 0.06, _HIGH_CAP,
                685.0, 0.14, 0.013, -2.5, 15.0),
        Product("NDX", "NDXP", "Nasdaq-100 Index", "index", 100, "European",
                "Cash, PM-settled at the 4:00 PM ET close", 0.15, 0.08, 0.06, _HIGH_CAP,
                25000.0, 0.18, 0.007, -2.0, 12.0),
        Product("SPY", "SPY", "SPDR S&P 500 ETF", "etf", 100, "American",
                "Physical delivery of shares; exercise/assignment after the close", 0.15, 0.08, 0.06,
                _HIGH_CAP + " (tracks a high-cap index)", 683.0, 0.14, 0.012, -2.5, 15.0),
        Product("QQQ", "QQQ", "Invesco QQQ ETF", "etf", 100, "American",
                "Physical delivery of shares; exercise/assignment after the close", 0.15, 0.08, 0.06,
                _HIGH_CAP + " (tracks a high-cap index)", 610.0, 0.19, 0.006, -2.0, 12.0),
        Product("TSLA", "TSLA", "Tesla, Inc.", "equity", 100, "American",
                "Physical delivery of shares; exercise/assignment after the close", 0.20, 0.15, 0.15,
                _EQUITY, 450.0, 0.65, 0.0, -0.6, 2.0),
        Product("NKE", "NKE", "Nike, Inc.", "equity", 100, "American",
                "Physical delivery of shares; exercise/assignment after the close", 0.20, 0.15, 0.15,
                _EQUITY, 70.0, 0.38, 0.022, -0.8, 3.0),
    ]
}
