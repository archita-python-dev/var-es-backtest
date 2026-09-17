"""Load and validate the TOML run configuration."""

from __future__ import annotations

import tomllib
from dataclasses import asdict, dataclass
from pathlib import Path

import pandas as pd

WEIGHTINGS = ("equal", "market_cap")


@dataclass(frozen=True)
class Config:
    aum: float
    weighting: str
    universe_size: int
    data_start: pd.Timestamp
    test_start: pd.Timestamp
    test_end: pd.Timestamp
    window_months: int
    confidence_levels: tuple[float, ...]
    mc_simulations: int
    mc_seed: int
    mc_df_bounds: tuple[float, float]
    cache_dir: Path
    max_filled_gaps: int
    output_dir: Path
    log_dir: Path
    candidates: tuple[str, ...]

    def to_dict(self) -> dict:
        return {k: str(v) if isinstance(v, (Path, pd.Timestamp)) else v for k, v in asdict(self).items()}


def load_config(path: str | Path, weighting: str | None = None) -> Config:
    path = Path(path)
    with path.open("rb") as f:
        raw = tomllib.load(f)
    root = path.parent

    cfg = Config(
        aum=float(raw["portfolio"]["aum"]),
        weighting=weighting or raw["portfolio"]["weighting"],
        universe_size=int(raw["portfolio"]["universe_size"]),
        data_start=pd.Timestamp(raw["dates"]["data_start"]),
        test_start=pd.Timestamp(raw["dates"]["test_start"]),
        test_end=pd.Timestamp(raw["dates"]["test_end"]),
        window_months=int(raw["dates"]["window_months"]),
        confidence_levels=tuple(float(c) for c in raw["risk"]["confidence_levels"]),
        mc_simulations=int(raw["risk"]["mc_simulations"]),
        mc_seed=int(raw["risk"]["mc_seed"]),
        mc_df_bounds=tuple(float(b) for b in raw["risk"]["mc_df_bounds"]),
        cache_dir=root / raw["data"]["cache_dir"],
        max_filled_gaps=int(raw["data"]["max_filled_gaps"]),
        output_dir=root / raw["output"]["output_dir"],
        log_dir=root / raw["output"]["log_dir"],
        candidates=tuple(raw["universe"]["candidates"]),
    )
    _validate(cfg)
    return cfg


def _validate(cfg: Config) -> None:
    if cfg.weighting not in WEIGHTINGS:
        raise ValueError(f"weighting must be one of {WEIGHTINGS}, got {cfg.weighting!r}")
    if not all(0.5 < c < 1 for c in cfg.confidence_levels):
        raise ValueError("confidence levels must be between 0.5 and 1")
    if cfg.test_start - pd.DateOffset(months=cfg.window_months) < cfg.data_start:
        raise ValueError("data_start is too late to fill the first estimation window")
    if cfg.test_end <= cfg.test_start:
        raise ValueError("test_end must be after test_start")
    if len(set(cfg.candidates)) < cfg.universe_size:
        raise ValueError("fewer unique candidate tickers than universe_size")
    if cfg.mc_df_bounds[0] <= 2:
        raise ValueError("Student-t degrees of freedom must stay above 2 (finite variance)")
