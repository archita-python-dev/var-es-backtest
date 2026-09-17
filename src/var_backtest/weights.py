"""Portfolio weights: equal or market-cap, fixed as of the last trading day before the test year."""

from __future__ import annotations

import logging
from pathlib import Path

import numpy as np
import pandas as pd

from .config import Config

log = logging.getLogger(__name__)

SHARES_FILE = "shares_outstanding.csv"


def compute_weights(tickers: list[str], close: pd.DataFrame, cfg: Config) -> pd.DataFrame:
    """Return a frame indexed by ticker with a `weight` column summing to 1."""
    if cfg.weighting == "equal":
        return pd.DataFrame({"weight": np.full(len(tickers), 1 / len(tickers))}, index=pd.Index(tickers, name="ticker"))

    as_of = close.index[close.index < cfg.test_start][-1]
    shares = load_shares(tickers, as_of, cfg.cache_dir)
    price = close.loc[as_of, tickers]
    frame = shares.join(price.rename("close"))
    frame["market_cap"] = frame["shares"] * frame["close"]
    frame["weight"] = market_cap_weights(frame["shares"], frame["close"])
    log.info("Market-cap weights as of %s; largest: %s", as_of.date(),
             ", ".join(f"{t} {w:.1%}" for t, w in frame["weight"].nlargest(5).items()))
    return frame


def market_cap_weights(shares: pd.Series, price: pd.Series) -> pd.Series:
    cap = shares * price
    return cap / cap.sum()


def load_shares(tickers: list[str], as_of: pd.Timestamp, cache_dir: Path) -> pd.DataFrame:
    """Shares outstanding on or before `as_of`, cached. Falls back to today's count, logged per ticker."""
    path = cache_dir / SHARES_FILE
    cached = pd.read_csv(path, index_col="ticker") if path.exists() else pd.DataFrame()
    if not cached.empty and set(tickers) <= set(cached.index) and (cached["as_of"] == str(as_of.date())).all():
        log.info("Using cached shares outstanding from %s", path)
        return cached.loc[tickers]

    import yfinance as yf

    rows = []
    for ticker in tickers:
        t = yf.Ticker(ticker)
        shares, source = None, "historical"
        try:
            hist = t.get_shares_full(start=as_of - pd.Timedelta(days=120), end=as_of + pd.Timedelta(days=1))
            if hist is not None and len(hist):
                hist.index = hist.index.tz_localize(None)
                hist = hist[hist.index <= as_of + pd.Timedelta(days=1)]
                shares = float(hist.iloc[-1]) if len(hist) else None
        except Exception as exc:  # yfinance raises a variety of errors for missing data
            log.debug("get_shares_full failed for %s: %s", ticker, exc)
        if shares is None:
            shares = t.info.get("sharesOutstanding")
            source = "current (fallback - look-ahead approximation)"
            log.warning("No historical share count for %s; using current shares outstanding", ticker)
        if not shares:
            raise RuntimeError(f"no shares outstanding available for {ticker}")
        rows.append({"ticker": ticker, "shares": shares, "source": source, "as_of": str(as_of.date())})

    frame = pd.DataFrame(rows).set_index("ticker")
    path.parent.mkdir(parents=True, exist_ok=True)
    frame.to_csv(path)
    return frame
