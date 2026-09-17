"""Shared chart style: palette, typography and axis treatment used by every figure."""

from __future__ import annotations

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.colors import ListedColormap

from .backtest import METHODS

# Categorical slots 1-3, validated colour-blind safe as a set. Each method keeps its colour in every chart.
SERIES_COLORS = dict(zip(METHODS, ("#2a78d6", "#eb6834", "#1baf7a")))
ACCENT = "#4a3aa7"  # slot 7, for non-method series (e.g. market-cap weights)

INK, INK_SECONDARY, INK_MUTED = "#0b0b0b", "#52514e", "#898781"
GRID, BASELINE, SURFACE, PNL_BAR = "#e1e0d9", "#c3c2b7", "#fcfcfb", "#c3c2b7"
STATUS = {"good": "#0ca30c", "warning": "#fab219", "critical": "#d03b3b"}

# Sequential blue ramp (light to dark) for heatmaps; the first step is near-surface for zero.
BLUE_RAMP = ["#f0efec", "#cde2fb", "#9ec5f4", "#6da7ec", "#3987e5", "#256abf", "#184f95", "#0d366b"]
SEQUENTIAL = ListedColormap(BLUE_RAMP)

WEIGHTING_LABELS = {"equal": "Equal-weighted", "market_cap": "Market-cap weighted"}


def use_style() -> None:
    plt.rcParams.update({
        "font.family": "sans-serif",
        "font.sans-serif": ["Helvetica Neue", "Helvetica", "Arial", "DejaVu Sans"],
        "font.size": 10,
        "figure.facecolor": SURFACE,
        "axes.facecolor": SURFACE,
        "savefig.facecolor": SURFACE,
        "axes.edgecolor": BASELINE,
        "axes.labelcolor": INK_SECONDARY,
        "xtick.color": INK_MUTED,
        "ytick.color": INK_MUTED,
        "xtick.major.size": 0,
        "ytick.major.size": 0,
        "legend.frameon": False,
        "legend.labelcolor": INK_SECONDARY,
        "text.parse_math": False,  # "$" in labels is currency, not maths
    })


def clean_axes(ax, grid_axis: str | None = "y") -> None:
    """Recessive chrome: hairline grid on one axis, baseline only, no ticks."""
    for side in ("top", "right", "left"):
        ax.spines[side].set_visible(False)
    ax.spines["bottom"].set_color(BASELINE)
    if grid_axis:
        ax.grid(axis=grid_axis, color=GRID, linewidth=1)
    ax.set_axisbelow(True)


def headline(fig, title: str, subtitle: str | None = None, source: str | None = None) -> None:
    """Left-aligned title and subtitle at the top of the figure, source note at the bottom."""
    height = fig.get_figheight()
    fig.text(0.012, 1 - 0.28 / height, title, ha="left", va="top", color=INK, fontsize=14, fontweight="bold")
    if subtitle:
        fig.text(0.012, 1 - 0.62 / height, subtitle, ha="left", va="top", color=INK_SECONDARY, fontsize=10.5)
    if source:
        fig.text(0.012, 0.12 / height, source, ha="left", va="bottom", color=INK_MUTED, fontsize=8.5)


def reserve(fig, top_in: float = 1.05, bottom_in: float = 0.45) -> tuple[float, float]:
    """Figure-fraction bounds that leave `top_in` / `bottom_in` inches for the headline and source."""
    h = fig.get_figheight()
    return bottom_in / h, 1 - top_in / h
