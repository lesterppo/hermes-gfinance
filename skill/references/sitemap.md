# Google Finance — Full Site Map (live probe 2026-08-11)

Fetching `google.com/finance/*` with `Mozilla/5.0` `AF_initDataCallback` parse — all three roots probed + 7 markets pages + 8 quote varieties + search.

## Verified: Same Wiz Shell on Home + Markets

All tested URLs return **same shell** (identical `AF_initDataCallback` keys, `len≈1.67M`):

- `https://www.google.com/finance/beta/u/3?pageId=none` (200, ds:1/11/10/2/7/0/9/6/8/5/4/3)
- `https://www.google.com/finance/` (same)
- `https://www.google.com/finance/beta/?lfhs=2` (same)
- `https://www.google.com/finance/markets/{gainers,losers,most-active,trending,currencies,cryptocurrencies,indexes}` — all same `ds:0` kinds `[7,1,2,3,9,4,5]` + `ds:2` sectors + `ds:9` movers shape `[[[quote_rec]]]` — server does **not** differentiate without JS hydration; treat as same strip with different parser slice

## Home / Beta Blocks (shared)

- `ds:0` — `[ [groups], flag ]` double-wrapped; groups: `kind 7 futures`, `1 US indices`, `2 Intl`, `3 Nikkei`, `9 Latin`, `4 FX`, `5 crypto` + `ds:2 sectors`
- `ds:2` — `[[[ "sectors", [mids×11], "Equity sectors", [[sec…]] ]]]` → unwrap `v[0][0]` then `inner[3]` (11 CBOE: Industrials, Financials…)
- `ds:3` — on beta is **earnings calendar** not quote (`[[[ticker,ex],date,"title"]]`); on quote pages is canonical quote
- `ds:9` — on markets pages is `[[[quote_rec]]]×12` movers (gainers/losers/most_active/trending share same out-of-hours fallback ABCL trend: ABCL:NASDAQ +34% etc, 12 tickers)
- `ds:4/5/10/11/12/13/14/15/16/17/18/19/20` — also present as quote-page mirrors even on home (cross-page duplication)

## Quote Pages (rich, ~1.2–1.4M)

| Example | ds present | Notes |
|---|---|---|
| `AAPL:NASDAQ` (equity US) | `ds:0..ds:20` full | `ds:3/10/16/17` quote (p=308.26 ch=-4.80 chp=-1.53% prev=313.06), `ds:11` tick 1m, `ds:12` OHLC 5m, `ds:13/14` daily 21, `ds:18` fundamentals quarterly (~70k chars), `ds:4` about 72 fields, `ds:5` ratios, `ds:15` valuation×12, `ds:6` peers×4, `ds:7` analyst Buy 232→400, `ds:19/20` news×28 |
| `0700:HKG` (HK) | same full | HKD, Asia/Hong_Kong, ds:7 StrongBuy tp=685.9 |
| `SPY:NYSEARCA` (ETF) | `ds:18` is **news** not fundamentals, `ds:7` sparse, peers are sibling ETFs (QQQ) | etf-aware |
| `BTC-USD` (crypto) | `ds:11/13` 24h buckets `[null,mid,cur]` + `[[date],[p,ch,pct]]` with `len==2` in `ds:13`, `ds:10` OHLC 24h, `ds:18` news | crypto fix: daily `len==2` |
| `EUR-USD` (FX) | same crypto shape | fx; `EUR/USD` slash alias works via `quote_url` |
| `YMW00:CBOT` (futures) | `ds:10` CHICAGO tz, `ds:11` intraday, `ds:13` daily, `ds:18` minimal `[null,…,mid,name,pair]` | futures |
| `NI225:INDEXNIKKEI` (JP index) | `ds:12` OHLC with Asia/Tokyo | index |
| `GC00:COMEX` (thin commodity) | sparse, `ds:3` missing → `quote not found` | graceful empty, not parser bug |

## Search

`GET https://www.google.com/finance/beta/search?q=NVDA` — returns `ds:3` single matched quote (NVDA) + `ds:10` results list (AAPL mirror in trace due to same shell, actual list in `ds:8/9/10` group) + `ds:15` peer suggestions. Action `search` uses `ds:8/9/10` + HTML `/finance/quote/` regex fallback.

## ds Inventory → Action (25 actions, v3)

`quote` ← `ds:3/10/16/17`; `history/intraday` ← `ds:12/13/14` (`ds:11` minute); `fundamentals` ← `ds:18`; `news` ← `ds:19/20`; `analyst` ← `ds:7`; `about` ← `ds:4`; `search` ← `ds:8/9/10`; `markets` ← `ds:0+ds:2`; `peers` ← `ds:6`; `compare` ← multi-fetch `ds:13`; `calendar` ← beta `ds:3`; `indices` ← `ds:0 kind=1`; `futures` ← `ds:0 kind=7`; `gainers/losers/most_active/trending` ← `ds:9`; `crypto/fx` ← `quote BTC-USD/EUR-USD` + `ds:6` peers; `etf` ← `ds:4`; `convert` ← `USD-EUR` quote + inverse; `stats` ← `ds:10/17/5/15`; `overview` ← composite; `chat` ← `chat-multiturn.md`; `help` ← list.

Raw: `/tmp/GFINANCE_SITEMAP.json` (4245B), probe logs `/tmp/map_finance.py`, `/tmp/deep_ds.py`.
