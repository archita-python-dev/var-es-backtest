"""Write CSV outputs, charts and a Markdown run report."""

from __future__ import annotations

import logging
from datetime import datetime
from pathlib import Path

import matplotlib
import matplotlib.dates as mdates
import matplotlib.pyplot as plt
from matplotlib.lines import Line2D
from matplotlib.patches import Patch
import numpy as np
import pandas as pd

from .backtest import METHODS, BacktestResult, exceptions, monthly_breaches, summarise
from .config import Config
from .style import BASELINE, GRID, INK, INK_MUTED, INK_SECONDARY, PNL_BAR, SERIES_COLORS, SURFACE

log = logging.getLogger(__name__)

EVENTS = {pd.Timestamp("2025-04-02"): "US tariff announcement (2 Apr)"}


def write_outputs(result: BacktestResult, weights: pd.DataFrame, quality: pd.DataFrame, cfg: Config) -> Path:
    out = cfg.output_dir / cfg.weighting
    (out / "charts").mkdir(parents=True, exist_ok=True)

    summary = summarise(result, cfg.confidence_levels)
    monthly = monthly_breaches(result)
    exc = exceptions(result)

    summary.to_csv(out / "summary.csv", index=False)
    monthly.to_csv(out / "monthly_breaches.csv")
    exc.to_csv(out / "exceptions.csv", index=False)
    result.daily.to_csv(out / "daily_forecasts.csv", index=False)
    result.t_df.rename_axis("date").to_csv(out / "student_t_df.csv")
    weights.to_csv(out / "weights.csv")
    quality.to_csv(out / "data_quality.csv", index=False)

    chart = out / "charts" / "var_backtest.png"
    plot_backtest(result, cfg, chart)
    (out / "report.md").write_text(render_report(summary, monthly, exc, weights, quality, result, cfg))
    log.info("Wrote outputs to %s", out)
    return out


def _money(x: float) -> str:
    return "n/a" if pd.isna(x) else f"${x / 1e6:,.1f}M"


def _p(x: float) -> str:
    return "n/a" if pd.isna(x) else f"{x:.3f}"


def summary_table(summary: pd.DataFrame) -> str:
    view = pd.DataFrame({
        "Method": summary["Method"],
        "Confidence": summary["Confidence"],
        "Avg VaR": summary["Avg VaR ($)"].map(_money),
        "Avg ES": summary["Avg ES ($)"].map(_money),
        "Runtime (s)": summary["Runtime, all days (s)"].map(lambda s: f"{s:.2f}"),
        "Breaches (actual / expected)": [f"{b} / {e:.1f}" for b, e in zip(summary["Breaches"], summary["Expected breaches"])],
        "Kupiec p": summary["Kupiec p-value"].map(_p),
        "Count OK?": summary["Breach count OK (p>=0.05)"],
        "Clustering p": summary["Clustering p-value"].map(_p),
        "Basel zone": summary["Basel zone"],
        "Avg loss on breach days": summary["Avg loss on breach days ($)"].map(_money),
        "Actual loss / ES": summary["Actual loss / forecast ES"].map(lambda r: "n/a" if pd.isna(r) else f"{r:.2f}"),
    })
    return view.to_markdown(index=False)


def render_report(summary, monthly, exc, weights, quality, result: BacktestResult, cfg: Config) -> str:
    daily = result.daily
    first = daily.iloc[0]
    included = quality[quality["status"] == "included"]
    dropped = quality[quality["status"] == "dropped"]
    flagged = included[included["flag"].fillna("") != ""]
    top = weights["weight"].sort_values(ascending=False).head(10)
    worst = (daily.drop_duplicates("date").nsmallest(5, "actual_pnl_usd")[["date", "actual_pnl_usd"]])

    lines = [
        f"# VaR and Expected Shortfall backtest: {cfg.weighting.replace('_', '-')} weighted",
        "",
        f"Generated {datetime.now():%Y-%m-%d %H:%M}. Portfolio {_aum_label(cfg.aum)}, "
        f"{len(included)} US large-cap stocks, 1-day horizon.",
        f"Test period {daily['date'].min():%d %b %Y} to {daily['date'].max():%d %b %Y} "
        f"({daily['date'].nunique()} trading days). Each day's forecast uses the previous "
        f"{cfg.window_months} months only (first window: {first['window_start']:%d %b %Y}, "
        f"{first['window_days']} days).",
        "",
        "## Results",
        "",
        summary_table(summary),
        "",
        "How to read this table:",
        "- **Avg VaR / Avg ES**: the average of the daily forecasts over the test year.",
        "- **Kupiec p**: tests whether the breach count fits the confidence level. Below 0.05 means it does not.",
        "- **Clustering p**: Christoffersen test. Below 0.05 means breaches bunch together instead of being spread out.",
        "- **Basel zone**: Green is acceptable; Yellow and Red mean too many breaches.",
        "- **Actual loss / ES**: on breach days, the actual loss divided by the ES forecast. Above 1 means ES understated the loss.",
        f"- **Runtime**: total time for all {daily['date'].nunique()} daily forecasts"
        f" (Monte Carlo uses {cfg.mc_simulations:,} scenarios per day).",
        "",
        "![Daily P&L against VaR](charts/var_backtest.png)",
        "",
        "## Breaches by month",
        "",
        monthly.to_markdown(),
        "",
        "## Worst days for the portfolio",
        "",
        pd.DataFrame({"Date": worst["date"].dt.strftime("%d %b %Y"),
                      "P&L": worst["actual_pnl_usd"].map(_money)}).to_markdown(index=False),
        "",
        f"Every breach is listed in `exceptions.csv` ({len(exc)} rows across all methods and confidence levels).",
        "",
        "## Monte Carlo tail thickness",
        "",
        f"Fitted Student-t degrees of freedom: median {result.t_df.median():.1f}, "
        f"range {result.t_df.min():.1f} to {result.t_df.max():.1f}. Lower values mean more extreme days.",
        "",
        "## Portfolio",
        "",
        "Top 10 weights:",
        "",
        pd.DataFrame({"Ticker": top.index, "Weight": top.map(lambda w: f"{w:.2%}")}).to_markdown(index=False),
        "",
        "## Data quality",
        "",
        f"- Candidates checked: {len(quality[quality['status'] != 'not used'])}; included: {len(included)}; dropped: {len(dropped)}.",
    ]
    lines += [f"- Dropped **{r.ticker}**: {r.reason}" for r in dropped.itertuples()]
    lines += [f"- Flagged **{r.ticker}**: {r.flag} (max move {r.max_abs_daily_return:.1%})" for r in flagged.itertuples()]
    lines += [f"- Forward-filled missing prices: {int(included['filled_gaps'].sum())} stock-days.", ""]
    if "source" in weights.columns:
        fallback = weights[weights["source"] != "historical"]
        lines += [f"- Share counts from current data instead of history: {len(fallback)} tickers"
                  + (f" ({', '.join(fallback.index)})" if len(fallback) else ""), ""]
    return "\n".join(lines)


def _aum_label(aum: float) -> str:
    return f"${aum / 1e9:,.0f}B" if aum >= 1e9 and aum % 1e9 == 0 else _money(aum)


def plot_backtest(result: BacktestResult, cfg: Config, path: Path) -> None:
    """Small multiples, one panel per confidence level: daily P&L bars with each method's -VaR line."""
    daily = result.daily
    pnl = daily.drop_duplicates("date").set_index("date")["actual_pnl_usd"] / 1e6
    levels = cfg.confidence_levels

    plt.rcParams.update({"font.family": "sans-serif", "font.size": 10})
    fig, axes = plt.subplots(len(levels), 1, figsize=(12, 3.3 * len(levels) + 0.8), sharex=True, facecolor=SURFACE)
    axes = np.atleast_1d(axes)

    for ax, level in zip(axes, levels):
        at_level = daily[daily["confidence"] == level]
        breach_any = at_level.groupby("date")["breach"].any().reindex(pnl.index)
        ax.set_facecolor(SURFACE)
        ax.bar(pnl.index, pnl.values, width=1.0, zorder=1,
               color=np.where(breach_any, INK_SECONDARY, PNL_BAR))
        counts = []
        for method in METHODS:
            d = at_level[at_level["method"] == method].set_index("date")
            ax.plot(d.index, -d["var_usd"] / 1e6, color=SERIES_COLORS[method], linewidth=2,
                    solid_joinstyle="round", solid_capstyle="round", zorder=3)
            counts.append(f"{method.split(' (')[0]} {int(d['breach'].sum())}")
        for date, label in EVENTS.items():
            if pnl.index.min() <= date <= pnl.index.max():
                ax.axvline(date, color=INK_MUTED, linewidth=1, zorder=0)
                ax.text(date, ax.get_ylim()[1], f"  {label}", color=INK_SECONDARY, fontsize=9, va="top")

        ax.set_title(f"{level:.0%} confidence", loc="left", color=INK, fontsize=11, fontweight="bold")
        ax.set_title("Breaches: " + ", ".join(counts), loc="right", color=INK_SECONDARY, fontsize=10)
        ax.set_ylabel("$ millions", color=INK_SECONDARY)
        ax.axhline(0, color=BASELINE, linewidth=1, zorder=2)
        ax.grid(axis="y", color=GRID, linewidth=1)
        ax.set_axisbelow(True)
        for side in ("top", "right", "left"):
            ax.spines[side].set_visible(False)
        ax.spines["bottom"].set_color(BASELINE)
        ax.tick_params(colors=INK_MUTED, length=0)
        ax.yaxis.set_major_formatter(matplotlib.ticker.FuncFormatter(lambda v, _: f"{v:,.0f}"))

    axes[-1].xaxis.set_major_locator(mdates.MonthLocator())
    axes[-1].xaxis.set_major_formatter(mdates.DateFormatter("%b %Y"))

    handles = [Line2D([], [], color=SERIES_COLORS[m], linewidth=2, label=f"{m} VaR") for m in METHODS]
    handles += [Patch(color=PNL_BAR, label="Daily P&L"), Patch(color=INK_SECONDARY, label="Breach day (any method)")]
    fig.suptitle(f"Daily P&L vs 1-day VaR: {cfg.weighting.replace('_', '-')}-weighted {_aum_label(cfg.aum)} portfolio, "
                 f"{pnl.index.min():%Y}", x=0.012, y=0.992, ha="left", color=INK, fontsize=13, fontweight="bold")
    fig.legend(handles=handles, loc="upper left", bbox_to_anchor=(0.005, 0.965), ncol=5, frameon=False,
               fontsize=9.5, labelcolor=INK_SECONDARY, handlelength=1.6)
    fig.tight_layout(rect=(0, 0, 1, 1 - 0.75 / fig.get_figheight()))
    fig.savefig(path, dpi=150, facecolor=SURFACE)
    plt.close(fig)
