# Alpaca probe

Measured 2026-08-15T00:57:21-04:00

Trading day probed: **2026-08-14** (SPY printed 10 regular session bars, status 200)
Window: 04:00 to 08:30 ET
Universe: 2,745 symbols from data/universe.json

Every number below was observed. Nothing here is inferred from documentation.

**[corrected 2026-08-20: every measurement in this file was taken against a
COMPLETED session, and the answer in section 1 holds only for that case. The
heading asks whether the free plan actually serves SIP and the table answers
yes, without naming the restriction. The live probe found the same feed
refused: all 46 requests in data/probe-alpaca-live-2026-08-17.jsonl, sweeping
1Min sip bars over a window ending at the wall clock on a live trading
morning, came back HTTP 403, and the two sweeps of 2026-08-16 did the same.
So the free plan serves sip for a session that is over and refuses it for one
that is running. The tables below measure the first of those and say nothing
about the second. See DECISIONS.md 2026-08-17 on the free tier, whose own
account of that morning was corrected the same day for reading the refusals
as an empty feed. Written by hand rather than measured: probe_alpaca.py
generates this file, and regenerating it needs a network run against a vendor
this project no longer builds on, so a regeneration would drop this note.]**

## 1. Does the free plan actually serve SIP

Symbol AAPL, one feed against the other, measured in two windows. The regular session pass is a control: without it, IEX returning nothing in premarket cannot be told apart from IEX not being served at all.

| Window | Feed | Bars | Volume | Status |
| --- | --- | ---: | ---: | ---: |
| premarket | sip | 198 | 1,410,664 | 200 |
| premarket | iex | 0 | 0 | 200 |
| regular | sip | 61 | 3,196,427 | 200 |
| regular | iex | 61 | 128,881 | 200 |

**SIP to IEX volume ratio, regular session control: 24.8014**

**SIP to IEX volume ratio, premarket window: undefined. IEX returned 0 bars and 0 shares, so the denominator is zero while SIP returned 1,410,664 shares.**

## 2. Do non-trading symbols return nothing

| Symbol | Group | 20d dollar volume | Key present in response | Bars |
| --- | --- | ---: | --- | ---: |
| SNDK | liquid | 21,593,138,302.13 | True | 270 |
| NVDA | liquid | 25,972,291,934.39 | True | 254 |
| MU | liquid | 38,516,104,791.78 | True | 270 |
| CTNM | illiquid | 5,001,337.47 | False | 0 |
| BTX | illiquid | 5,004,825.15 | False | 0 |
| GDOT | illiquid | 5,142,903.96 | False | 0 |

Keys returned: MU, NVDA, SNDK

Extra observation, an invalid ticker alongside a good one: status 200, keys returned AAPL

## 3. How many symbols fit in one request

| Batch | Status | URL chars for the symbol list | Bars on first page | Seconds | Error |
| ---: | ---: | ---: | ---: | ---: | --- |
| 100 | 200 | 444 | 1,326 | 0.122 |  |
| 500 | 200 | 2,246 | 5,758 | 0.292 |  |
| 1,000 | 200 | 4,472 | 9,455 | 0.372 |  |
| 2,000 | 200 | 8,946 | 10,000 | 0.309 |  |

## 4. How much data actually comes back

Full universe sweep at 1Min, batch size 2,000.

| Measure | Value |
| --- | ---: |
| Symbols requested | 2,745 |
| Total bars returned | 29,125 |
| Distinct symbols with any bars | 1,684 |
| Pages consumed | 4 |
| Largest single page | 10,000 |
| Sweep complete | True |

## 5. How long it takes

| Measure | Value |
| --- | ---: |
| Wall clock, full 1Min sweep | 1.04 s |
| Requests used | 4 |
| Per request minimum | 0.108 s |
| Per request median | 0.274 s |
| Per request maximum | 0.332 s |

## 6. Rate limit headroom

| Header | Value |
| --- | --- |
| x-ratelimit-limit | 200 |
| x-ratelimit-remaining | 191 |
| x-ratelimit-reset | 1786769842 |

Requests used by the whole probe: 21
Requests used by the 1Min sweep alone: 4
429 retries: 0

## 7. Whether a coarser timeframe is worth it

| Measure | 1Min | 1Hour |
| --- | ---: | ---: |
| Total bars | 29,125 | 4,550 |
| Symbols with bars | 1,684 | 1,776 |
| Pages | 4 | 5 |
| Requests | 4 | 5 |
| Wall clock | 1.04 s | 1.11 s |
| Sweep complete | True | True |

The hourly sweep reports MORE symbols than the minute sweep, which cannot be true of the same window and is the measurement that decides this question.

| Measure | Value |
| --- | ---: |
| Symbols in 1Hour but not in 1Min | 92 |
| Of those, first 1Min bar falls AFTER the window end | 92 |

Window ends at 08:30 ET. Examples:

- AGIO first 1Min bar at ET 08:35
- AIR first 1Min bar at ET 08:43
- AMBP first 1Min bar at ET 08:55
- APLE first 1Min bar at ET 08:58
- ATEN first 1Min bar at ET 08:46

An hourly bar is returned when its START falls inside the window, but the bar aggregates the whole hour, so the bar stamped 08:00 carries trades through 09:00. A coarse first stage therefore reads past the boundary it appears to respect, and a symbol can show hourly premarket activity that had not happened yet at the moment the report is written.

