# VaR and Expected Shortfall backtest: equal weighted

Generated 2026-09-18 00:29. Portfolio $1B, 100 US large-cap stocks, 1-day horizon.
Test period 02 Jan 2025 to 31 Dec 2025 (250 trading days). Each day's forecast uses the previous 59 months only (first window: 03 Feb 2020, 1237 days).

## Results

| Method                  | Confidence   | Avg VaR   | Avg ES   |   Runtime (s) | Breaches (actual / expected)   |   Kupiec p | Count OK?   |   Clustering p | Basel zone   | Avg loss on breach days   |   Actual loss / ES |
|:------------------------|:-------------|:----------|:---------|--------------:|:-------------------------------|-----------:|:------------|---------------:|:-------------|:--------------------------|-------------------:|
| Historical              | 95%          | $15.9M    | $24.8M   |          0.08 | 10 / 12.5                      |      0.453 | Yes         |          0.401 | Green        | $27.1M                    |               1.12 |
| Historical              | 97%          | $20.0M    | $29.5M   |          0.08 | 6 / 7.5                        |      0.565 | Yes         |          0.12  | Green        | $33.9M                    |               1.19 |
| Historical              | 99%          | $30.6M    | $39.3M   |          0.08 | 3 / 2.5                        |      0.758 | Yes         |          0.02  | Green        | $46.5M                    |               1.26 |
| Monte Carlo (Student-t) | 95%          | $16.0M    | $23.3M   |          5.73 | 10 / 12.5                      |      0.453 | Yes         |          0.401 | Green        | $27.1M                    |               1.22 |
| Monte Carlo (Student-t) | 97%          | $19.4M    | $27.2M   |          5.73 | 6 / 7.5                        |      0.565 | Yes         |          0.12  | Green        | $33.9M                    |               1.32 |
| Monte Carlo (Student-t) | 99%          | $27.2M    | $36.4M   |          5.73 | 3 / 2.5                        |      0.758 | Yes         |          0.02  | Green        | $46.5M                    |               1.37 |
| Parametric (Normal)     | 95%          | $16.9M    | $21.4M   |          0.15 | 8 / 12.5                       |      0.163 | Yes         |          0.24  | Green        | $29.9M                    |               1.44 |
| Parametric (Normal)     | 97%          | $19.5M    | $23.7M   |          0.15 | 6 / 7.5                        |      0.565 | Yes         |          0.12  | Green        | $33.9M                    |               1.49 |
| Parametric (Normal)     | 99%          | $24.3M    | $27.9M   |          0.15 | 3 / 2.5                        |      0.758 | Yes         |          0.02  | Green        | $46.5M                    |               1.73 |
| Parametric (t + EWMA)   | 95%          | $14.4M    | $19.9M   |          0.38 | 15 / 12.5                      |      0.481 | Yes         |          0.28  | Green        | $19.5M                    |               1.21 |
| Parametric (t + EWMA)   | 97%          | $17.1M    | $22.7M   |          0.38 | 11 / 7.5                       |      0.224 | Yes         |          0.494 | Green        | $22.3M                    |               1.19 |
| Parametric (t + EWMA)   | 99%          | $23.1M    | $29.0M   |          0.38 | 4 / 2.5                        |      0.38  | Yes         |          0.043 | Green        | $36.9M                    |               1.37 |

How to read this table:
- **Avg VaR / Avg ES**: the average of the daily forecasts over the test year.
- **Kupiec p**: tests whether the breach count fits the confidence level. Below 0.05 means it does not.
- **Clustering p**: Christoffersen test. Below 0.05 means breaches bunch together instead of being spread out.
- **Basel zone**: Green is acceptable; Yellow and Red mean too many breaches.
- **Actual loss / ES**: on breach days, the actual loss divided by that day's ES forecast, averaged. Above 1 means ES understated the loss.
- **Avg ES** above is averaged over all test days. `summary.csv` also carries *Avg ES on breach days*, the average ES forecast on the breach days only, which is the like-for-like comparison against the realised loss.
- **Runtime**: total time for all 250 daily forecasts (Monte Carlo uses 10,000 scenarios per day).

![Daily P&L against VaR](charts/var_backtest.png)

## Breaches by month

| month   |   Historical 95% |   Historical 97% |   Historical 99% |   Parametric (Normal) 95% |   Parametric (Normal) 97% |   Parametric (Normal) 99% |   Parametric (t + EWMA) 95% |   Parametric (t + EWMA) 97% |   Parametric (t + EWMA) 99% |   Monte Carlo (Student-t) 95% |   Monte Carlo (Student-t) 97% |   Monte Carlo (Student-t) 99% |
|:--------|-----------------:|-----------------:|-----------------:|--------------------------:|--------------------------:|--------------------------:|----------------------------:|----------------------------:|----------------------------:|------------------------------:|------------------------------:|------------------------------:|
| 2025-01 |                0 |                0 |                0 |                         0 |                         0 |                         0 |                           1 |                           1 |                           0 |                             0 |                             0 |                             0 |
| 2025-02 |                0 |                0 |                0 |                         0 |                         0 |                         0 |                           2 |                           1 |                           0 |                             0 |                             0 |                             0 |
| 2025-03 |                3 |                1 |                0 |                         1 |                         1 |                         0 |                           4 |                           3 |                           1 |                             3 |                             1 |                             0 |
| 2025-04 |                5 |                4 |                3 |                         5 |                         4 |                         3 |                           2 |                           2 |                           2 |                             5 |                             4 |                             3 |
| 2025-05 |                1 |                0 |                0 |                         1 |                         0 |                         0 |                           0 |                           0 |                           0 |                             1 |                             0 |                             0 |
| 2025-06 |                0 |                0 |                0 |                         0 |                         0 |                         0 |                           0 |                           0 |                           0 |                             0 |                             0 |                             0 |
| 2025-07 |                0 |                0 |                0 |                         0 |                         0 |                         0 |                           1 |                           1 |                           0 |                             0 |                             0 |                             0 |
| 2025-08 |                0 |                0 |                0 |                         0 |                         0 |                         0 |                           1 |                           0 |                           0 |                             0 |                             0 |                             0 |
| 2025-09 |                0 |                0 |                0 |                         0 |                         0 |                         0 |                           0 |                           0 |                           0 |                             0 |                             0 |                             0 |
| 2025-10 |                1 |                1 |                0 |                         1 |                         1 |                         0 |                           2 |                           2 |                           1 |                             1 |                             1 |                             0 |
| 2025-11 |                0 |                0 |                0 |                         0 |                         0 |                         0 |                           2 |                           1 |                           0 |                             0 |                             0 |                             0 |
| 2025-12 |                0 |                0 |                0 |                         0 |                         0 |                         0 |                           0 |                           0 |                           0 |                             0 |                             0 |                             0 |

## Worst days for the portfolio

| Date        | P&L     |
|:------------|:--------|
| 04 Apr 2025 | $-63.5M |
| 03 Apr 2025 | $-42.0M |
| 10 Apr 2025 | $-33.9M |
| 10 Mar 2025 | $-22.1M |
| 21 Apr 2025 | $-21.7M |

Every breach is listed in `exceptions.csv` (85 rows across all methods and confidence levels).

## Fitted tail thickness

- **Monte Carlo (Student-t)**: median df 5.0, range 4.3 to 6.4.
- **Parametric (t + EWMA)**: median df 7.3, range 6.9 to 8.5.
Lower degrees of freedom mean fatter tails: more extreme days than a normal distribution allows.

## Compute

- Forecast days run on 8 worker threads; wall clock 2.9s for 250 days.
- Shared inputs (window mean, sample covariance, EWMA covariance): 0.4s. Each model's runtime excludes these, since every model reads the same ones.
- Per-model seconds are measured on a serial sample of days and scaled to the full year, so they compare like with like; timing a model inside a worker thread would also count time spent waiting on the other threads.

| Stage                            | Kind   |   Seconds |
|:---------------------------------|:-------|----------:|
| Historical                       | model  |     0.083 |
| Parametric (Normal)              | model  |     0.145 |
| Parametric (t + EWMA)            | model  |     0.382 |
| Monte Carlo (Student-t)          | model  |     5.73  |
| Shared inputs (mean, covariance) | shared |     0.396 |
| Wall clock (8 workers)           | wall   |     2.858 |

## Portfolio

Top 10 weights:

| Ticker   | Weight   |
|:---------|:---------|
| AAPL     | 1.00%    |
| NVDA     | 1.00%    |
| MSFT     | 1.00%    |
| AMZN     | 1.00%    |
| GOOGL    | 1.00%    |
| META     | 1.00%    |
| TSLA     | 1.00%    |
| AVGO     | 1.00%    |
| BRK-B    | 1.00%    |
| WMT      | 1.00%    |

## Data quality

- Candidates checked: 102; included: 100; dropped: 2.
- Dropped **PLTR**: insufficient history (first price 2020-09-30)
- Dropped **GEV**: insufficient history (first price 2024-03-27)
- Flagged **META**: daily move above 25% - verify corporate actions (max move 26.4%)
- Flagged **ORCL**: daily move above 25% - verify corporate actions (max move 35.9%)
- Flagged **NFLX**: daily move above 25% - verify corporate actions (max move 35.1%)
- Flagged **CRM**: daily move above 25% - verify corporate actions (max move 26.0%)
- Flagged **UBER**: daily move above 25% - verify corporate actions (max move 38.3%)
- Flagged **COP**: daily move above 25% - verify corporate actions (max move 25.2%)
- Flagged **FISV**: daily move above 25% - verify corporate actions (max move 44.0%)
- Flagged **PANW**: daily move above 25% - verify corporate actions (max move 28.4%)
- Flagged **INTC**: daily move above 25% - verify corporate actions (max move 26.1%)
- Forward-filled missing prices: 1 stock-days.
