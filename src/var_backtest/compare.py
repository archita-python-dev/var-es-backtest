"""Comparison charts across methods, confidence levels and weighting schemes.

Reads the saved outputs of earlier runs (no re-computation):
    python -m var_backtest.compare [--config config.toml]
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from pathlib import Path

import matplotlib
import matplotlib.dates as mdates
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from matplotlib.colors import BoundaryNorm
from matplotlib.lines import Line2D
from matplotlib.patches import Patch
from matplotlib.ticker import FuncFormatter

from .backtest import METHODS
from .config import load_config
from .style import (BASELINE, BLUE_RAMP, GRID, INK, INK_MUTED, INK_SECONDARY, PNL_BAR, SEQUENTIAL,
                    SERIES_COLORS, STATUS, SURFACE, WEIGHTING_COLORS, WEIGHTING_LABELS, clean_axes, headline,
                    reserve, use_style)

SHORT = {"Historical": "Historical", "Parametric (Normal)": "Parametric", "Monte Carlo (Student-t)": "Monte Carlo"}
TARIFF_DATE = pd.Timestamp("2025-04-02")
COVID_LOW = pd.Timestamp("2020-03-23")


@dataclass
class RunResults:
    weighting: str
    summary: pd.DataFrame
    daily: pd.DataFrame
    monthly: pd.DataFrame
    weights: pd.DataFrame

    @property
    def label(self) -> str:
        return WEIGHTING_LABELS[self.weighting]

    def row(self, method: str, level: str) -> pd.Series:
        s = self.summary
        return s[(s["Method"] == method) & (s["Confidence"] == level)].iloc[0]


def load_runs(output_dir: Path) -> list[RunResults]:
    runs = []
    for weighting in WEIGHTING_LABELS:
        folder = output_dir / weighting
        if not (folder / "summary.csv").exists():
            continue
        runs.append(RunResults(
            weighting=weighting,
            summary=pd.read_csv(folder / "summary.csv"),
            daily=pd.read_csv(folder / "daily_forecasts.csv", parse_dates=["date", "window_start"]),
            monthly=pd.read_csv(folder / "monthly_breaches.csv", index_col="month"),
            weights=pd.read_csv(folder / "weights.csv", index_col=0),
        ))
    if not runs:
        raise FileNotFoundError(f"no backtest outputs in {output_dir}; run `python -m var_backtest` first")
    return runs


def _levels(run: RunResults) -> list[str]:
    return list(dict.fromkeys(run.summary["Confidence"]))


def _method_legend(fig, y_in: float = 0.98, extra: list | None = None) -> None:
    handles = [Patch(color=SERIES_COLORS[m], label=m) for m in METHODS] + (extra or [])
    fig.legend(handles=handles, loc="upper left", bbox_to_anchor=(0.006, 1 - y_in / fig.get_figheight()),
               ncol=len(handles), fontsize=9.5, handlelength=1.2, columnspacing=1.6)


def _save(fig, path: Path) -> Path:
    fig.savefig(path, dpi=200)
    plt.close(fig)
    return path


def _grouped_bars(ax, run: RunResults, column: str, fmt, label_pad: float, avoid: list[float] | None = None) -> None:
    """Grouped bars per confidence level. Value labels jump above any `avoid` line (one per group) they would hit."""
    levels = _levels(run)
    x = np.arange(len(levels))
    width = 0.24
    for j, method in enumerate(METHODS):
        values = [run.row(method, lvl)[column] for lvl in levels]
        pos = x + (j - 1) * (width + 0.03)
        ax.bar(pos, values, width=width, color=SERIES_COLORS[method], zorder=2)
        for i, (p, v) in enumerate(zip(pos, values)):
            if pd.notna(v):
                y = v + label_pad
                if avoid is not None and -label_pad * 4 < avoid[i] - y < label_pad * 3:
                    y = max(y, avoid[i] + label_pad)
                ax.text(p, y, fmt(v), ha="center", va="bottom", color=INK_SECONDARY, fontsize=9)
    ax.set_xticks(x)
    ax.set_xlim(-0.6, len(levels) - 0.4)
    clean_axes(ax)
    ax.set_title(run.label, loc="left", color=INK, fontsize=11.5, fontweight="bold", pad=10)


# 1 -------------------------------------------------------------------------------------------
def chart_breaches(runs: list[RunResults], path: Path, source: str) -> Path:
    fig, axes = plt.subplots(1, len(runs), figsize=(12, 5.8), sharey=True, squeeze=False)
    axes = axes[0]
    top = max(max(r.summary["Breaches"].max(), r.summary["Expected breaches"].max()) for r in runs)

    for ax, run in zip(axes, runs):
        levels = _levels(run)
        expected = [run.row(METHODS[0], lvl)["Expected breaches"] for lvl in levels]
        _grouped_bars(ax, run, "Breaches", lambda v: f"{int(v)}", label_pad=0.25, avoid=expected)
        for i, e in enumerate(expected):
            ax.hlines(e, i - 0.43, i + 0.43, color=INK, linewidth=1.6, zorder=3)
        ax.set_xticklabels([f"{lvl} confidence\nexpected {e:g}" for lvl, e in zip(levels, expected)],
                           color=INK_SECONDARY)
        ax.set_ylim(0, top * 1.18)
    axes[0].set_ylabel("Breach days in 2025")

    all_rows = pd.concat([r.summary for r in runs])
    ok = int((all_rows["Breach count OK (p>=0.05)"] == "Yes").sum())
    headline(fig, f"{ok} of {len(all_rows)} model runs had an acceptable number of breaches",
             "Days the actual loss exceeded the VaR forecast, against the number expected (black line)", source)
    _method_legend(fig, 0.95, [Line2D([], [], color=INK, linewidth=1.6, label="Expected breaches")])
    bottom, top_frac = reserve(fig, 1.35, 0.45)
    fig.tight_layout(rect=(0, bottom, 1, top_frac), w_pad=3)
    return _save(fig, path)


# 2 -------------------------------------------------------------------------------------------
def chart_var_vs_es(runs: list[RunResults], path: Path, source: str) -> Path:
    fig, axes = plt.subplots(1, len(runs), figsize=(12, 6.8), sharey=True, squeeze=False)
    axes = axes[0]
    levels = _levels(runs[0])
    xmax = max(r.summary["Avg ES ($)"].max() for r in runs) / 1e6

    for ax, run in zip(axes, runs):
        ticks, labels = [], []
        for i, lvl in enumerate(levels):
            base = i * 4.2
            ax.text(0, base - 0.85, f"{lvl} confidence", color=INK, fontsize=10, fontweight="bold",
                    ha="left", va="center", transform=ax.get_yaxis_transform())
            for j, method in enumerate(METHODS):
                y = base + j
                r = run.row(method, lvl)
                var, es = r["Avg VaR ($)"] / 1e6, r["Avg ES ($)"] / 1e6
                color = SERIES_COLORS[method]
                ax.plot([var, es], [y, y], color=color, linewidth=2.5, solid_capstyle="round", zorder=2)
                ax.scatter(var, y, s=80, facecolor=SURFACE, edgecolor=color, linewidth=2.2, zorder=3)
                ax.scatter(es, y, s=80, color=color, edgecolor=SURFACE, linewidth=2, zorder=4)
                ax.text(es + xmax * 0.025, y, f"${es:.1f}M", va="center", color=INK_SECONDARY, fontsize=9)
                ax.text(var - xmax * 0.025, y, f"${var:.1f}M", va="center", ha="right", color=INK_MUTED, fontsize=8.5)
                ticks.append(y)
                labels.append(SHORT[method])
        ax.set_yticks(ticks, labels, color=INK_SECONDARY)
        ax.set_xlim(0, xmax * 1.15)
        ax.xaxis.set_major_formatter(FuncFormatter(lambda v, _: f"${v:,.0f}M"))
        clean_axes(ax, grid_axis="x")
        ax.set_title(run.label, loc="left", color=INK, fontsize=11.5, fontweight="bold", pad=22)
    axes[0].set_ylim(len(levels) * 4.2 - 1.6, -1.6)

    headline(fig, "How far the average tail loss (ES) sits beyond VaR",
             "Average daily forecast over 2025. The longer the line, the heavier the tail the model expects.", source)
    _method_legend(fig, 0.95, [
        Line2D([], [], marker="o", linestyle="", markerfacecolor=SURFACE, markeredgecolor=INK_SECONDARY,
               markeredgewidth=2, markersize=8, label="VaR"),
        Line2D([], [], marker="o", linestyle="", color=INK_SECONDARY, markersize=8, label="Expected Shortfall"),
    ])
    bottom, top_frac = reserve(fig, 1.3, 0.45)
    fig.tight_layout(rect=(0, bottom, 1, top_frac), w_pad=3)
    return _save(fig, path)


# 3 -------------------------------------------------------------------------------------------
def chart_es_accuracy(runs: list[RunResults], path: Path, source: str) -> Path:
    """Forecast ES against the actual average loss on the days each model was breached."""
    # ES averaged over the breach days themselves, so both marks describe the same set of days.
    es_col, loss_col = "Avg ES on breach days ($)", "Avg loss on breach days ($)"
    fig, axes = plt.subplots(1, len(runs), figsize=(13, 7.4), sharey=True, squeeze=False)
    axes = axes[0]
    levels = _levels(runs[0])
    xmax = max(max(r.summary[es_col].max(), r.summary[loss_col].max()) for r in runs) / 1e6

    for ax, run in zip(axes, runs):
        ticks, labels = [], []
        for i, lvl in enumerate(levels):
            base = i * 4.2
            ax.text(0, base - 0.95, f"{lvl} confidence", color=INK, fontsize=10, fontweight="bold",
                    ha="left", va="center", transform=ax.get_yaxis_transform())
            for j, method in enumerate(METHODS):
                y = base + j
                r = run.row(method, lvl)
                es, loss, breaches = r[es_col] / 1e6, r[loss_col] / 1e6, int(r["Breaches"])
                color = SERIES_COLORS[method]
                if pd.isna(loss):
                    ax.scatter(es, y, s=80, facecolor=SURFACE, edgecolor=color, linewidth=2.2, zorder=3)
                    ax.text(es + xmax * 0.03, y, "no breaches", va="center", color=INK_MUTED, fontsize=9)
                else:
                    ax.plot([es, loss], [y, y], color=color, linewidth=2.5, solid_capstyle="round", zorder=2)
                    ax.scatter(es, y, s=80, facecolor=SURFACE, edgecolor=color, linewidth=2.2, zorder=3)
                    ax.scatter(loss, y, s=80, color=color, edgecolor=SURFACE, linewidth=2, zorder=4)
                    lo, hi = min(es, loss), max(es, loss)
                    ax.text(lo - xmax * 0.02, y, f"${lo:.1f}M", va="center", ha="right", color=INK_MUTED, fontsize=8.5)
                    ax.text(hi + xmax * 0.02, y, f"${hi:.1f}M   {loss / es:.2f}x", va="center",
                            color=INK_SECONDARY, fontsize=9)
                ticks.append(y)
                labels.append(SHORT[method] + "\n" + f"{breaches} breach days")
        ax.set_yticks(ticks, labels, color=INK_SECONDARY, fontsize=9)
        ax.set_xlim(0, xmax * 1.3)
        ax.xaxis.set_major_formatter(FuncFormatter(lambda v, _: f"${v:,.0f}M"))
        clean_axes(ax, grid_axis="x")
        ax.set_title(run.label, loc="left", color=INK, fontsize=11.5, fontweight="bold", pad=24)
    axes[0].set_ylim(len(levels) * 4.2 - 1.6, -1.7)

    all_rows = pd.concat([r.summary.assign(w=r.label) for r in runs], ignore_index=True)
    all_rows["plotted_ratio"] = all_rows[loss_col] / all_rows[es_col]  # same definition the chart labels use
    worst = all_rows.loc[all_rows["plotted_ratio"].idxmax()]
    headline(fig, f"{SHORT[worst['Method']]} ES fell furthest short: breach-day losses were "
                  f"{worst['plotted_ratio']:.2f} times what it forecast",
             "For each model, the ES it forecast on its own breach days against the loss actually suffered on those "
             "same days. Breach counts differ, so each model is averaged over a different set of days.", source)
    _method_legend(fig, 0.95, [
        Line2D([], [], marker="o", linestyle="", markerfacecolor=SURFACE, markeredgecolor=INK_SECONDARY,
               markeredgewidth=2, markersize=8, label="Forecast ES on those days"),
        Line2D([], [], marker="o", linestyle="", color=INK_SECONDARY, markersize=8, label="Actual loss on breach days"),
    ])
    bottom, top_frac = reserve(fig, 1.5, 0.45)
    fig.tight_layout(rect=(0, bottom, 1, top_frac), w_pad=3)
    return _save(fig, path)


# 4 -------------------------------------------------------------------------------------------
def chart_scorecard(runs: list[RunResults], path: Path, source: str) -> Path:
    levels = _levels(runs[0])
    n_rows = len(METHODS) * len(levels)
    fig = plt.figure(figsize=(13, 1.9 + 0.42 * n_rows + 0.9))
    bottom, top_frac = reserve(fig, 1.15, 0.45)
    ax = fig.add_axes((0.012, bottom, 0.976, top_frac - bottom))
    ax.set_axis_off()
    ax.set_xlim(0, 1)
    ax.set_ylim(n_rows + 0.2, -2.2)

    group_x = [0.215, 0.61]
    col_offsets = [0.0, 0.07, 0.175, 0.28]
    col_names = ["Breaches", "Count test", "Clustering test", "Basel zone"]

    def status_cell(x, y, state, text):
        color = STATUS.get(state)
        if color:
            ax.plot(x, y, marker="o", markersize=7, color=color, markeredgecolor=SURFACE, markeredgewidth=1)
        ax.text(x + 0.013, y, text, va="center", color=INK if color else INK_MUTED, fontsize=9.5)

    def test_cell(x, y, p):
        if pd.isna(p):
            return status_cell(x, y, None, "n/a (no breaches)")
        return status_cell(x, y, "good" if p >= 0.05 else "critical", f"{'Pass' if p >= 0.05 else 'Fail'}  p={p:.2f}")

    ax.text(0.0, -1.0, "Method", color=INK_MUTED, fontsize=9, va="center")
    ax.text(0.13, -1.0, "Confidence", color=INK_MUTED, fontsize=9, va="center")
    for gx, run in zip(group_x, runs):
        ax.text(gx, -1.85, run.label, color=INK, fontsize=11, fontweight="bold", va="center")
        ax.plot([gx, gx + 0.35], [-1.5, -1.5], color=BASELINE, linewidth=1)
        for off, name in zip(col_offsets, col_names):
            ax.text(gx + off, -1.0, name, color=INK_MUTED, fontsize=9, va="center")
    ax.plot([0, 1], [-0.55, -0.55], color=BASELINE, linewidth=1)

    y = 0
    for lvl in levels:
        for method in METHODS:
            ax.plot(0.004, y, marker="s", markersize=8, color=SERIES_COLORS[method])
            ax.text(0.018, y, SHORT[method], va="center", color=INK, fontsize=10)
            ax.text(0.13, y, lvl, va="center", color=INK, fontsize=10)
            for gx, run in zip(group_x, runs):
                r = run.row(method, lvl)
                ax.text(gx, y, f"{int(r['Breaches'])} / {r['Expected breaches']:g}", va="center", color=INK, fontsize=9.5)
                test_cell(gx + col_offsets[1], y, r["Kupiec p-value"])
                test_cell(gx + col_offsets[2], y, r["Clustering p-value"])
                zone = r["Basel zone"]
                status_cell(gx + col_offsets[3], y, {"Green": "good", "Yellow": "warning", "Red": "critical"}[zone], zone)
            y += 1
        ax.plot([0, 1], [y - 0.5, y - 0.5], color=GRID if y < n_rows else BASELINE, linewidth=1)

    all_rows = pd.concat([r.summary for r in runs])
    clustered = int((all_rows["Clustering p-value"] < 0.05).sum())
    count_ok = int((all_rows["Breach count OK (p>=0.05)"] == "Yes").sum())
    headline(fig, f"Breach counts pass in {count_ok} of {len(all_rows)} runs, "
                  f"but breaches cluster in {clustered} of them",
             "Count test: Kupiec proportion of failures. Clustering test: Christoffersen independence. "
             "Both pass when p ≥ 0.05.", source)
    return _save(fig, path)


# 5 -------------------------------------------------------------------------------------------
def chart_tariff_zoom(runs: list[RunResults], path: Path, source: str,
                      level: float = 0.99, start: str = "2025-01-02", end: str = "2025-05-30") -> Path:
    fig, axes = plt.subplots(len(runs), 1, figsize=(12, 3.7 * len(runs) + 1.6), sharex=True, squeeze=False)
    axes = axes[:, 0]
    notes = []

    for ax, run in zip(axes, runs):
        d = run.daily[(run.daily["confidence"].round(4) == level) & run.daily["date"].between(start, end)]
        pnl = d.drop_duplicates("date").set_index("date")["actual_pnl_usd"] / 1e6
        breach_any = d.groupby("date")["breach"].any().reindex(pnl.index)
        ax.bar(pnl.index, pnl.values, width=1.0, color=np.where(breach_any, INK_SECONDARY, PNL_BAR), zorder=1)
        for method in METHODS:
            m = d[d["method"] == method].set_index("date")["var_usd"] / 1e6
            ax.plot(m.index, -m.values, color=SERIES_COLORS[method], linewidth=2, solid_capstyle="round", zorder=3)

        worst_day = pnl.idxmin()
        ax.annotate(f"−${-pnl.min():.1f}M on {worst_day:%-d %b}", xy=(worst_day, pnl.min()),
                    xytext=(18, 0), textcoords="offset points", va="center", color=INK, fontsize=9.5,
                    arrowprops=dict(arrowstyle="-", color=INK_MUTED, linewidth=1))

        # The date the March 2020 low leaves the rolling window.
        leaves = d.loc[d["window_start"] > COVID_LOW, "date"].min()
        ymax = pnl.max() * 1.12
        for date, text in ((leaves, "Mar 2020 low leaves the window"), (TARIFF_DATE, "Tariff announcement")):
            if pd.notna(date):
                ax.axvline(date, color=INK_MUTED, linewidth=1, zorder=0)
                ax.text(date, ymax, f" {text}", color=INK_SECONDARY, fontsize=9, va="top")
        ax.set_ylim(pnl.min() * 1.15, ymax)
        ax.axhline(0, color=BASELINE, linewidth=1, zorder=2)
        clean_axes(ax)
        ax.set_ylabel("$ millions")
        ax.set_title(run.label, loc="left", color=INK, fontsize=11.5, fontweight="bold")

        pre = d[d["date"] < TARIFF_DATE]
        first, last = pre["date"].min(), pre["date"].max()
        for method in METHODS:
            s = pre[pre["method"] == method].set_index("date")["var_usd"]
            notes.append((run.label, method, s[first], s[last]))

    axes[-1].xaxis.set_major_locator(mdates.MonthLocator())
    axes[-1].xaxis.set_major_formatter(mdates.DateFormatter("%b %Y"))

    label, method, v0, v1 = max(notes, key=lambda n: 1 - n[3] / n[2])
    headline(fig, "VaR fell as the COVID crash left the window, just before the tariff shock",
             f"Daily P&L and {level:.0%} VaR, Jan–May 2025. {SHORT[method]} VaR ({label.lower()}) dropped "
             f"{1 - v1 / v0:.0%}, from ${v0 / 1e6:.1f}M to ${v1 / 1e6:.1f}M, before 2 April.", source)
    _method_legend(fig, 0.95, [Patch(color=PNL_BAR, label="Daily P&L"),
                               Patch(color=INK_SECONDARY, label="Breach day")])
    bottom, top_frac = reserve(fig, 1.35, 0.45)
    fig.tight_layout(rect=(0, bottom, 1, top_frac), h_pad=2)
    return _save(fig, path)


# 6 -------------------------------------------------------------------------------------------
def chart_monthly_heatmap(runs: list[RunResults], path: Path, source: str) -> Path:
    fig, axes = plt.subplots(1, len(runs), figsize=(12, 7.2), sharey=True, squeeze=False)
    axes = axes[0]
    vmax = max(int(r.monthly.to_numpy().max()) for r in runs)
    bounds = np.arange(-0.5, max(vmax, len(BLUE_RAMP) - 1) + 1.5)
    norm = BoundaryNorm(bounds, SEQUENTIAL.N, clip=True)
    levels = _levels(runs[0])

    for ax, run in zip(axes, runs):
        data = run.monthly.to_numpy()
        months = pd.PeriodIndex(run.monthly.index, freq="M")
        ax.pcolormesh(data, cmap=SEQUENTIAL, norm=norm, edgecolors=SURFACE, linewidth=2)
        for (i, j), v in np.ndenumerate(data):
            if v:
                ax.text(j + 0.5, i + 0.5, str(v), ha="center", va="center", fontsize=9.5,
                        color="#ffffff" if v >= 3 else INK)
        ax.set_yticks(np.arange(len(months)) + 0.5, [m.strftime("%b") for m in months], color=INK_SECONDARY)
        ax.set_xticks(np.arange(data.shape[1]) + 0.5, levels * len(METHODS), color=INK_SECONDARY, fontsize=9)
        ax.tick_params(length=0)
        for side in ax.spines.values():
            side.set_visible(False)
        for k, method in enumerate(METHODS):
            x0 = k * len(levels)
            ax.text(x0 + len(levels) / 2, -1.0, SHORT[method], ha="center", va="bottom", color=INK, fontsize=10)
            ax.plot([x0 + 0.15, x0 + len(levels) - 0.15], [-0.8, -0.8], color=SERIES_COLORS[method],
                    linewidth=3, solid_capstyle="round", clip_on=False)
        ax.set_title(run.label, loc="left", color=INK, fontsize=11.5, fontweight="bold", pad=62)

    axes[0].set_ylim(len(runs[0].monthly), 0)  # shared y axis, January on top; fixed so labels above don't stretch it
    for ax in axes:
        ax.xaxis.tick_top()
    total = sum(int(r.monthly.to_numpy().sum()) for r in runs)
    spring = sum(int(r.monthly.loc[[m for m in r.monthly.index if m[-2:] in ("03", "04")]].to_numpy().sum()) for r in runs)
    headline(fig, f"{spring / total:.0%} of all breaches happened in March and April 2025",
             "Breach days per month for each method and confidence level. Darker cells mean more breaches.", source)
    bottom, top_frac = reserve(fig, 1.0, 0.45)
    fig.tight_layout(rect=(0, bottom, 1, top_frac), w_pad=3)
    return _save(fig, path)


# 7 -------------------------------------------------------------------------------------------
def chart_runtime(runs: list[RunResults], path: Path, source: str, days: int, sims: int) -> Path:
    fig, ax = plt.subplots(figsize=(12, 1.6 + 0.5 * len(METHODS) * len(runs) + 0.4))
    y, ticks, labels = 0, [], []
    for method in METHODS:
        for run in runs:
            t = run.summary.loc[run.summary["Method"] == method, "Runtime, all days (s)"].iloc[0]
            ax.barh(y, t, height=0.62, color=SERIES_COLORS[method], zorder=2)
            ax.text(t * 1.12, y, f"{t:.2f} s", va="center", color=INK_SECONDARY, fontsize=9.5)
            ticks.append(y)
            labels.append(f"{SHORT[method]}  ·  {run.label.split()[0].lower()}")
            y += 1
        y += 0.5
    ax.set_xscale("log")
    ax.xaxis.set_minor_locator(matplotlib.ticker.NullLocator())
    ax.set_yticks(ticks, labels, color=INK_SECONDARY)
    ax.invert_yaxis()
    ax.xaxis.set_major_formatter(FuncFormatter(lambda v, _: f"{v:g} s"))
    clean_axes(ax, grid_axis="x")
    ax.spines["bottom"].set_visible(False)
    ax.set_xlim(right=ax.get_xlim()[1] * 3)

    r0 = runs[0].summary.groupby("Method")["Runtime, all days (s)"].first()
    headline(fig, f"Monte Carlo takes about {r0[METHODS[2]] / r0[METHODS[0]]:.0f}× longer than historical simulation",
             f"Total time for {days} daily forecasts at all confidence levels (log scale). "
             f"Monte Carlo simulates {sims:,} scenarios for 100 stocks each day.", source)
    bottom, top_frac = reserve(fig, 1.05, 0.45)
    fig.tight_layout(rect=(0, bottom, 1, top_frac))
    return _save(fig, path)


# 8 -------------------------------------------------------------------------------------------
def chart_concentration(runs: list[RunResults], path: Path, source: str, level: str = "99%") -> Path:
    by_w = {r.weighting: r for r in runs}
    if not {"equal", "market_cap"} <= set(by_w):
        return None
    eq, mc = by_w["equal"], by_w["market_cap"]
    fig, (left, right) = plt.subplots(1, 2, figsize=(12, 5.6), gridspec_kw={"width_ratios": [1.1, 1]})
    colors = WEIGHTING_COLORS

    for run in (eq, mc):
        cum = run.weights["weight"].sort_values(ascending=False).cumsum().to_numpy() * 100
        n = np.arange(1, len(cum) + 1)
        left.plot(n, cum, color=colors[run.weighting], linewidth=2.8, solid_capstyle="round", zorder=3)
    mc_cum = mc.weights["weight"].sort_values(ascending=False).cumsum() * 100
    for k in (5, 10, 25):
        v = mc_cum.iloc[k - 1]
        left.scatter(k, v, s=70, color=colors["market_cap"], edgecolor=SURFACE, linewidth=2, zorder=4)
        left.text(k + 2, v - 1, f"Top {k}: {v:.0f}%", color=INK, fontsize=9.5, va="top")
    left.text(62, 56, "Equal weights", color=INK_SECONDARY, fontsize=9.5, rotation=0)
    left.set_xlim(0, 101)
    left.set_ylim(0, 102)
    left.set_xlabel("Largest holdings, ranked")
    left.set_ylabel("Cumulative share of portfolio")
    left.yaxis.set_major_formatter(FuncFormatter(lambda v, _: f"{v:.0f}%"))
    clean_axes(left)
    left.set_title("Portfolio concentration", loc="left", color=INK, fontsize=11.5, fontweight="bold")

    increases = []
    for j, method in enumerate(METHODS):
        a, b = eq.row(method, level)["Avg VaR ($)"] / 1e6, mc.row(method, level)["Avg VaR ($)"] / 1e6
        increases.append(b / a - 1)
        right.plot([a, b], [j, j], color=GRID, linewidth=3, zorder=1)
        right.scatter(a, j, s=110, color=colors["equal"], edgecolor=SURFACE, linewidth=2, zorder=3)
        right.scatter(b, j, s=110, color=colors["market_cap"], edgecolor=SURFACE, linewidth=2, zorder=3)
        right.text(a - 0.7, j, f"${a:.1f}M", ha="right", va="center", color=INK_SECONDARY, fontsize=9.5)
        right.text(b + 0.7, j, f"${b:.1f}M  (+{b / a - 1:.0%})", ha="left", va="center", color=INK, fontsize=9.5)
    right.set_yticks(range(len(METHODS)), [SHORT[m] for m in METHODS], color=INK_SECONDARY)
    right.set_ylim(len(METHODS) - 0.4, -0.6)
    vals = [eq.row(m, level)["Avg VaR ($)"] for m in METHODS] + [mc.row(m, level)["Avg VaR ($)"] for m in METHODS]
    right.set_xlim(min(vals) / 1e6 - 6, max(vals) / 1e6 + 9)
    right.xaxis.set_major_formatter(FuncFormatter(lambda v, _: f"${v:.0f}M"))
    clean_axes(right, grid_axis="x")
    right.set_title(f"Average {level} VaR", loc="left", color=INK, fontsize=11.5, fontweight="bold")

    headline(fig, f"Market-cap weighting puts {mc_cum.iloc[9]:.0f}% in 10 stocks and raises {level} VaR "
                  f"by {min(increases):.0%}–{max(increases):.0%}",
             "The largest holdings are mostly big tech names, so a handful of stocks drive more of the portfolio's daily swings", source)
    handles = [Line2D([], [], color=colors["equal"], linewidth=2.8, marker="o", markersize=8, label="Equal-weighted"),
               Line2D([], [], color=colors["market_cap"], linewidth=2.8, marker="o", markersize=8,
                      label="Market-cap weighted")]
    fig.legend(handles=handles, loc="upper left", bbox_to_anchor=(0.006, 1 - 0.95 / fig.get_figheight()),
               ncol=2, fontsize=9.5)
    bottom, top_frac = reserve(fig, 1.35, 0.45)
    fig.tight_layout(rect=(0, bottom, 1, top_frac), w_pad=4)
    return _save(fig, path)


GALLERY = [
    ("01_breaches_vs_expected.png", "Breach counts", "Did each model breach about as often as its confidence level implies?"),
    ("02_backtest_scorecard.png", "Backtest scorecard", "Count test, clustering test and Basel zone for every run."),
    ("03_monthly_breach_heatmap.png", "When breaches happened", "Breaches by month show how tightly they bunch around the tariff shock."),
    ("04_tariff_shock_zoom.png", "The tariff shock, up close", "VaR drifted down as March 2020 left the window, just before the April losses."),
    ("05_var_vs_es.png", "VaR vs Expected Shortfall", "How much further the average tail loss sits beyond VaR, per model."),
    ("06_es_accuracy.png", "Was ES big enough?", "Forecast Expected Shortfall against the loss actually suffered on each breach day."),
    ("07_concentration_effect.png", "Equal vs market-cap weights", "Concentration in mega-caps and its effect on VaR."),
    ("08_runtime.png", "Speed", "Compute cost of each method."),
]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", default="config.toml")
    args = parser.parse_args(argv)

    cfg = load_config(args.config)
    runs = load_runs(cfg.output_dir)
    out = cfg.output_dir / "comparison"
    out.mkdir(parents=True, exist_ok=True)
    use_style()

    days = runs[0].daily["date"].nunique()
    source = (f"Source: Yahoo Finance daily prices. 1-day VaR and ES for a ${cfg.aum / 1e9:g}B portfolio of 100 US "
              f"large-cap stocks, backtested over {days} trading days in 2025 with a rolling {cfg.window_months}-month window.")

    builders = {
        "01_breaches_vs_expected.png": lambda p: chart_breaches(runs, p, source),
        "02_backtest_scorecard.png": lambda p: chart_scorecard(runs, p, source),
        "03_monthly_breach_heatmap.png": lambda p: chart_monthly_heatmap(runs, p, source),
        "04_tariff_shock_zoom.png": lambda p: chart_tariff_zoom(runs, p, source),
        "05_var_vs_es.png": lambda p: chart_var_vs_es(runs, p, source),
        "06_es_accuracy.png": lambda p: chart_es_accuracy(runs, p, source),
        "07_concentration_effect.png": lambda p: chart_concentration(runs, p, source),
        "08_runtime.png": lambda p: chart_runtime(runs, p, source, days, cfg.mc_simulations),
    }
    lines = ["# Comparison charts", "", f"Generated from `{cfg.output_dir.name}/` by `python -m var_backtest.compare`.", ""]
    for name, title, caption in GALLERY:
        if builders[name](out / name) is None:
            continue
        lines += [f"## {title}", "", caption, "", f"![{title}]({name})", ""]
        print(f"Wrote {out / name}")
    (out / "README.md").write_text("\n".join(lines))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
