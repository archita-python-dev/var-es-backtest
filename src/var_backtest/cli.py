"""Command-line entry point: python -m var_backtest [--weighting equal|market_cap] [--refresh-data]."""

from __future__ import annotations

import argparse
import json
import logging
import sys
from datetime import datetime
from pathlib import Path

from .backtest import run_backtest, summarise
from .config import WEIGHTINGS, load_config
from .data import load_prices, select_universe
from .report import summary_table, write_outputs
from .weights import compute_weights

log = logging.getLogger("var_backtest")


def _setup_logging(log_dir: Path, weighting: str) -> Path:
    log_dir.mkdir(parents=True, exist_ok=True)
    path = log_dir / f"run_{datetime.now():%Y%m%d_%H%M%S}_{weighting}.log"
    fmt = logging.Formatter("%(asctime)s %(levelname)-7s %(name)s: %(message)s", "%Y-%m-%d %H:%M:%S")
    root = logging.getLogger()
    root.setLevel(logging.INFO)
    for handler in (logging.FileHandler(path), logging.StreamHandler(sys.stderr)):
        handler.setFormatter(fmt)
        root.addHandler(handler)
    for noisy in ("yfinance", "urllib3", "peewee", "matplotlib"):
        logging.getLogger(noisy).setLevel(logging.WARNING)
    return path


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", default="config.toml", help="path to the TOML config")
    parser.add_argument("--weighting", choices=WEIGHTINGS, help="override the config's weighting method")
    parser.add_argument("--refresh-data", action="store_true", help="re-download prices even if cached")
    args = parser.parse_args(argv)

    cfg = load_config(args.config, args.weighting)
    log_path = _setup_logging(cfg.log_dir, cfg.weighting)
    log.info("Run configuration: %s", json.dumps({k: v for k, v in cfg.to_dict().items() if k != "candidates"}))

    adj, close = load_prices(cfg, refresh=args.refresh_data)
    market = select_universe(adj, close, cfg)
    weights = compute_weights(list(market.returns.columns), market.close, cfg)
    w = weights.loc[market.returns.columns, "weight"].to_numpy()

    result = run_backtest(
        market.returns, w, cfg.aum, cfg.test_start, cfg.test_end, cfg.window_months,
        cfg.confidence_levels, cfg.mc_simulations, cfg.mc_seed, cfg.mc_df_bounds,
    )
    out = write_outputs(result, weights, market.quality, cfg)

    print(summary_table(summarise(result, cfg.confidence_levels)))
    print(f"\nReport: {out / 'report.md'}\nLog:    {log_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
