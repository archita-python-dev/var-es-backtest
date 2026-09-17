# VaR and Expected Shortfall backtest: market-cap weighted

Generated 2026-09-18 00:30. Portfolio $1B, 100 US large-cap stocks, 1-day horizon.
Test period 02 Jan 2025 to 31 Dec 2025 (250 trading days). Each day's forecast uses the previous 59 months only (first window: 03 Feb 2020, 1237 days).

## Results

| Method                  | Confidence   | Avg VaR   | Avg ES   |   Runtime (s) | Breaches (actual / expected)   |   Kupiec p | Count OK?   |   Clustering p | Basel zone   | Avg loss on breach days   |   Actual loss / ES |
|:------------------------|:-------------|:----------|:---------|--------------:|:-------------------------------|-----------:|:------------|---------------:|:-------------|:--------------------------|-------------------:|
| Historical              | 95%          | $19.9M    | $30.4M   |          0.09 | 10 / 12.5                      |      0.453 | Yes         |          0.401 | Green        | $33.0M                    |               1.11 |
| Historical              | 97%          | $25.0M    | $35.5M   |          0.09 | 7 / 7.5                        |      0.851 | Yes         |          0.174 | Green        | $38.1M                    |               1.1  |
| Historical              | 99%          | $37.0M    | $45.9M   |          0.09 | 3 / 2.5                        |      0.758 | Yes         |          0.02  | Green        | $50.3M                    |               1.13 |
| Monte Carlo (Student-t) | 95%          | $19.8M    | $28.7M   |          5.75 | 11 / 12.5                      |      0.657 | Yes         |          0.494 | Green        | $31.8M                    |               1.16 |
| Monte Carlo (Student-t) | 97%          | $23.9M    | $33.3M   |          5.75 | 7 / 7.5                        |      0.851 | Yes         |          0.174 | Green        | $38.1M                    |               1.2  |
| Monte Carlo (Student-t) | 99%          | $33.5M    | $44.4M   |          5.75 | 4 / 2.5                        |      0.38  | Yes         |          0.043 | Green        | $46.3M                    |               1.15 |
| Parametric (Normal)     | 95%          | $20.9M    | $26.4M   |          0.15 | 9 / 12.5                       |      0.286 | Yes         |          0.316 | Green        | $34.5M                    |               1.34 |
| Parametric (Normal)     | 97%          | $24.0M    | $29.2M   |          0.15 | 7 / 7.5                        |      0.851 | Yes         |          0.174 | Green        | $38.1M                    |               1.34 |
| Parametric (Normal)     | 99%          | $30.0M    | $34.5M   |          0.15 | 4 / 2.5                        |      0.38  | Yes         |          0.043 | Green        | $46.3M                    |               1.39 |
| Parametric (t + EWMA)   | 95%          | $17.6M    | $24.0M   |          0.39 | 16 / 12.5                      |      0.329 | Yes         |          0.976 | Green        | $23.6M                    |               1.19 |
| Parametric (t + EWMA)   | 97%          | $20.9M    | $27.4M   |          0.39 | 10 / 7.5                       |      0.377 | Yes         |          0.401 | Green        | $28.4M                    |               1.25 |
| Parametric (t + EWMA)   | 99%          | $27.8M    | $34.6M   |          0.39 | 5 / 2.5                        |      0.162 | Yes         |          0.076 | Yellow       | $38.4M                    |               1.27 |

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
| 2025-01 |                0 |                0 |                0 |                         0 |                         0 |                         0 |                           2 |                           1 |                           0 |                             0 |                             0 |                             0 |
| 2025-02 |                0 |                0 |                0 |                         0 |                         0 |                         0 |                           2 |                           2 |                           0 |                             1 |                             0 |                             0 |
| 2025-03 |                4 |                1 |                0 |                         3 |                         1 |                         1 |                           4 |                           2 |                           1 |                             4 |                             1 |                             1 |
| 2025-04 |                5 |                5 |                3 |                         5 |                         5 |                         3 |                           2 |                           2 |                           2 |                             5 |                             5 |                             3 |
| 2025-05 |                0 |                0 |                0 |                         0 |                         0 |                         0 |                           0 |                           0 |                           0 |                             0 |                             0 |                             0 |
| 2025-06 |                0 |                0 |                0 |                         0 |                         0 |                         0 |                           0 |                           0 |                           0 |                             0 |                             0 |                             0 |
| 2025-07 |                0 |                0 |                0 |                         0 |                         0 |                         0 |                           0 |                           0 |                           0 |                             0 |                             0 |                             0 |
| 2025-08 |                0 |                0 |                0 |                         0 |                         0 |                         0 |                           1 |                           1 |                           1 |                             0 |                             0 |                             0 |
| 2025-09 |                0 |                0 |                0 |                         0 |                         0 |                         0 |                           0 |                           0 |                           0 |                             0 |                             0 |                             0 |
| 2025-10 |                1 |                1 |                0 |                         1 |                         1 |                         0 |                           1 |                           1 |                           1 |                             1 |                             1 |                             0 |
| 2025-11 |                0 |                0 |                0 |                         0 |                         0 |                         0 |                           3 |                           1 |                           0 |                             0 |                             0 |                             0 |
| 2025-12 |                0 |                0 |                0 |                         0 |                         0 |                         0 |                           1 |                           0 |                           0 |                             0 |                             0 |                             0 |

## Worst days for the portfolio

| Date        | P&L     |
|:------------|:--------|
| 04 Apr 2025 | $-60.3M |
| 03 Apr 2025 | $-52.5M |
| 10 Apr 2025 | $-38.3M |
| 10 Mar 2025 | $-34.2M |
| 16 Apr 2025 | $-27.8M |

Every breach is listed in `exceptions.csv` (93 rows across all methods and confidence levels).

## Fitted tail thickness

- **Monte Carlo (Student-t)**: median df 5.1, range 4.6 to 7.1.
- **Parametric (t + EWMA)**: median df 8.2, range 7.3 to 9.8.
Lower degrees of freedom mean fatter tails: more extreme days than a normal distribution allows.

## Compute

- Forecast days run on 8 worker threads; wall clock 2.8s for 250 days.
- Shared inputs (window mean, sample covariance, EWMA covariance): 0.4s. Each model's runtime excludes these, since every model reads the same ones.
- Per-model seconds are measured on a serial sample of days and scaled to the full year, so they compare like with like; timing a model inside a worker thread would also count time spent waiting on the other threads.

| Stage                            | Kind   |   Seconds |
|:---------------------------------|:-------|----------:|
| Historical                       | model  |     0.086 |
| Parametric (Normal)              | model  |     0.145 |
| Parametric (t + EWMA)            | model  |     0.391 |
| Monte Carlo (Student-t)          | model  |     5.746 |
| Shared inputs (mean, covariance) | shared |     0.417 |
| Wall clock (8 workers)           | wall   |     2.848 |

## Portfolio

Top 10 weights:

| Ticker   | Weight   |
|:---------|:---------|
| AAPL     | 9.88%    |
| NVDA     | 8.91%    |
| MSFT     | 8.18%    |
| GOOGL    | 6.06%    |
| AMZN     | 6.02%    |
| META     | 3.86%    |
| TSLA     | 3.38%    |
| AVGO     | 2.84%    |
| BRK-B    | 2.55%    |
| WMT      | 1.91%    |

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

- Share counts from current data instead of history: 2 tickers (FISV, MRSH)
