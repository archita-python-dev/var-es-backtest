# Comparison charts

Generated from `outputs/` by `python -m var_backtest.compare`.

## Breach counts

Did each model breach about as often as its confidence level implies?

![Breach counts](01_breaches_vs_expected.png)

## Backtest scorecard

Count test, clustering test and Basel zone for every run.

![Backtest scorecard](02_backtest_scorecard.png)

## When breaches happened

Breaches by month show how tightly they bunch around the tariff shock.

![When breaches happened](03_monthly_breach_heatmap.png)

## The tariff shock, up close

VaR drifted down as March 2020 left the window, just before the April losses.

![The tariff shock, up close](04_tariff_shock_zoom.png)

## VaR vs Expected Shortfall

How much further the average tail loss sits beyond VaR, per model.

![VaR vs Expected Shortfall](05_var_vs_es.png)

## Was ES big enough?

Average actual loss on breach days, and how it compares with the ES forecast.

![Was ES big enough?](06_es_accuracy.png)

## Equal vs market-cap weights

Concentration in mega-caps and its effect on VaR.

![Equal vs market-cap weights](07_concentration_effect.png)

## Speed

Compute cost of each method.

![Speed](08_runtime.png)
