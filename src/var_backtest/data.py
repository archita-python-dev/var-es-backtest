"""Download, cache and quality-check price data.

Prices are cached to CSV with a SHA-256 manifest so a run can be reproduced exactly
and any change to the underlying data is detectable.
"""

from __future__ import annotations

import hashlib
import json
import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

from .config import Config

log = logging.getLogger(__name__)

ADJ_FILE = "prices_adj_close.csv"
CLOSE_FILE = "prices_close.csv"
MANIFEST_FILE = "manifest.json"
EXTREME_MOVE = 0.25  # daily moves beyond +/-25% are flagged for review, not removed


@dataclass
class MarketData:
    returns: pd.DataFrame        # daily simple returns (dividend-adjusted), selected tickers only
    close: pd.DataFrame          # unadjusted closes, used for market-cap weights
    quality: pd.DataFrame        # one row per candidate: included/dropped and why


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_prices(cfg: Config, refresh: bool = False) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Return (adjusted close, unadjusted close), downloading only when the cache is missing."""
    cache = cfg.cache_dir
    adj_path, close_path, manifest_path = cache / ADJ_FILE, cache / CLOSE_FILE, cache / MANIFEST_FILE

    if refresh or not (adj_path.exists() and close_path.exists() and manifest_path.exists()):
        _download(cfg, adj_path, close_path, manifest_path)
    else:
        log.info("Using cached prices from %s", cache)
        manifest = json.loads(manifest_path.read_text())
        for path in (adj_path, close_path):
            if _sha256(path) != manifest["sha256"][path.name]:
                raise RuntimeError(f"{path} does not match its manifest hash; re-run with --refresh-data")
        missing = set(cfg.candidates) - set(manifest["tickers"])
        if missing:
            log.info("Cache lacks %d configured tickers; re-downloading", len(missing))
            _download(cfg, adj_path, close_path, manifest_path)

    adj = pd.read_csv(adj_path, index_col=0, parse_dates=True)
    close = pd.read_csv(close_path, index_col=0, parse_dates=True)
    return adj, close


def _download(cfg: Config, adj_path: Path, close_path: Path, manifest_path: Path) -> None:
    import yfinance as yf

    end = cfg.test_end + pd.Timedelta(days=1)  # yfinance's end date is exclusive
    log.info("Downloading %d tickers from Yahoo Finance (%s to %s)",
             len(cfg.candidates), cfg.data_start.date(), cfg.test_end.date())
    raw = yf.download(list(cfg.candidates), start=cfg.data_start, end=end,
                      auto_adjust=False, progress=False, threads=True)
    if raw.empty:
        raise RuntimeError("Yahoo Finance returned no data")

    # Network timeouts show up as empty columns; retry those once, one at a time, so a transient
    # failure doesn't silently change which stocks make the universe.
    failed = [t for t in cfg.candidates if t not in raw["Adj Close"] or raw["Adj Close"][t].isna().all()]
    if failed:
        log.info("Retrying %d tickers with no data: %s", len(failed), ", ".join(failed))
        retry = yf.download(failed, start=cfg.data_start, end=end, auto_adjust=False,
                            progress=False, threads=False, multi_level_index=True)
        for field in ("Adj Close", "Close"):
            for t in failed:
                if t in retry[field] and retry[field][t].notna().any():
                    raw[(field, t)] = retry[field][t]
        still = [t for t in failed if t not in retry["Adj Close"] or retry["Adj Close"][t].isna().all()]
        if still:
            log.warning("No data after retry: %s", ", ".join(still))

    adj_path.parent.mkdir(parents=True, exist_ok=True)
    raw["Adj Close"].to_csv(adj_path)
    raw["Close"].to_csv(close_path)
    manifest = {
        "source": "Yahoo Finance via yfinance",
        "downloaded_at_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "start": str(cfg.data_start.date()),
        "end": str(cfg.test_end.date()),
        "tickers": list(cfg.candidates),
        "sha256": {adj_path.name: _sha256(adj_path), close_path.name: _sha256(close_path)},
    }
    manifest_path.write_text(json.dumps(manifest, indent=2))
    log.info("Cached prices to %s", adj_path.parent)


def select_universe(adj: pd.DataFrame, close: pd.DataFrame, cfg: Config) -> MarketData:
    """Apply data-quality rules and keep the first `universe_size` candidates that pass."""
    adj = adj.loc[cfg.data_start:cfg.test_end]
    close = close.loc[cfg.data_start:cfg.test_end]

    # Trading calendar: days on which most candidates traded (drops stray non-trading rows).
    coverage = adj.notna().mean(axis=1)
    calendar = adj.index[coverage >= 0.9]
    adj, close = adj.loc[calendar], close.loc[calendar]

    rows, selected = [], []
    for ticker in cfg.candidates:
        row = {"ticker": ticker, "status": "dropped", "reason": "", "first_price": None,
               "filled_gaps": 0, "max_abs_daily_return": np.nan, "flag": ""}
        if len(selected) == cfg.universe_size:
            row.update(status="not used", reason="universe already full")
            rows.append(row)
            continue
        if ticker not in adj.columns or adj[ticker].notna().sum() == 0:
            row["reason"] = "no data returned"
            rows.append(row)
            continue

        series = adj[ticker]
        first, last = series.first_valid_index(), series.last_valid_index()
        row["first_price"] = str(first.date())
        gaps = int(series.loc[first:last].isna().sum())
        row["filled_gaps"] = gaps

        if first > calendar[0]:
            row["reason"] = f"insufficient history (first price {first.date()})"
        elif last < calendar[-1]:
            row["reason"] = f"no prices after {last.date()}"
        elif gaps > cfg.max_filled_gaps:
            row["reason"] = f"{gaps} missing days (limit {cfg.max_filled_gaps})"
        else:
            rets = series.ffill().pct_change().iloc[1:]
            row["max_abs_daily_return"] = round(float(rets.abs().max()), 4)
            if row["max_abs_daily_return"] > EXTREME_MOVE:
                row["flag"] = f"daily move above {EXTREME_MOVE:.0%} - verify corporate actions"
            row["status"] = "included"
            selected.append(ticker)
        rows.append(row)

    quality = pd.DataFrame(rows)
    if len(selected) < cfg.universe_size:
        raise RuntimeError(f"only {len(selected)} tickers passed data checks; add candidates")

    for r in quality.itertuples():
        if r.status == "dropped":
            log.warning("Dropped %s: %s", r.ticker, r.reason)
        elif r.flag:
            log.warning("Flagged %s: %s", r.ticker, r.flag)
    log.info("Universe: %d tickers selected from %d candidates", len(selected), len(cfg.candidates))

    returns = adj[selected].ffill().pct_change().iloc[1:]
    return MarketData(returns=returns, close=close[selected].ffill(), quality=quality)
