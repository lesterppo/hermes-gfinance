---
name: google-finance
description: Google Finance Wiz-native agent CLI and Hermes tool.
version: 1.0.0
author: Peter (lesterppo)
license: MIT
platforms: [linux]
metadata:
  hermes:
    tags: [google-finance, wiz, finance, quote, market-data, hermes-tool]
    category: finance
    related_skills: [hermes-native-tool-wiring, hermes-tool-reintegration]
---

# Google Finance — Wiz-Native Agent CLI

AI-agent-native, token-efficient CLI + native Hermes tool (`gfinance`) for the
full Google Finance site at `https://www.google.com/finance` (canonical
`/finance/quote/*`, `/finance/markets/*`, `/finance/beta/search`, and beta
SPA `https://www.google.com/finance/beta/u/3?pageId=none` / `?lfhs=2`).
No API key. Parses Wiz `AF_initDataCallback` embedded JSON blocks — no
`batchexecute` RPC, no browser automation.

## When to Use

- User asks for Google Finance data: quotes, charts, fundamentals, news, analysts
- Need an AI-agent-native tool (compact keys, spill-to-file, check_fn gating)
- Building any tool that scrapes a Google Wiz SPA (pattern is reusable)

## Architecture

```
google.com/finance/quote/TICKER:EXCH[?window=1D|5D|1M|6M|1Y|5Y|MAX]
  → fetch HTML → parse AF_initDataCallback data:[...] blocks → decode ds:* keys
google.com/finance/beta/search?q=QUERY
  → same AF parse + regex fallback for /finance/quote/TICKER tickers
google.com/finance/beta/u/3?pageId=none and /finance/, /finance/markets/*
  → same Wiz shell (2026-08-11 verified identical) → ds:0/ds:2/ds:9 slices
```

Tool lives as a **plugin** (`~/.hermes/plugins/hermes_local_tools/gfinance_tool.py` — 1422 lines, `All checks passed!`) so `hermes update` cannot wipe it. `_fetch_blocks` retries 3× (`0.6s * (attempt+1)`) to absorb burst timeouts on `/finance/markets/*`. See `references/sitemap.md`. Schema: `GFINANCE_SCHEMA` (25 actions, ~300 tokens), handler `gfinance_run(action, ticker, query, window)`, toolset `gfinance`, emoji `📈`. Standalone CLI at `~/.local/bin/gfinance`.

## Supported Actions (25 — full site, v3 2026-08-11)

| action | params | source ds | output |
|--------|--------|-----------|--------|
| `quote` | `ticker` (+`window`) | `ds:3` canonical, `ds:10` fallback | `p/ch/chp/prev/op/lo/hi/vol/mcap/cur/tz/name/desc` |
| `history` | `ticker` `window=1D|5D|1M|6M|1Y|5Y|MAX` | `ds:13` daily, `ds:12` intraday OHLC, `ds:11` minute | `daily/intraday/minute` arrays (spill if >9k chars) |
| `intraday` | `ticker` | alias → `history window=1D` | same |
| `fundamentals` | `ticker` | `ds:18` (quarterly/annual income+BS+CF) | `fundamentals` summary |
| `news` | `ticker` | `ds:19/20` | `news[{url,title,src,ts}]` |
| `analyst` | `ticker` | `ds:7` | `summary[] + analysts[{name,firm,rating,date,url}]` |
| `about` | `ticker` | `ds:4` | `desc/founded/ceo/employees/sector` |
| `search` | `query` | `ds:8/9/10` + HTML regex | `tickers[]` + previews |
| `markets` | — | `ds:0` futures+indices + `ds:2` sectors | `sectors[] + indices[] + futures[]` |
| `peers` | `ticker` | `ds:6` (quote page peers strip) | `peers[{t,ex,name,p,ch,chp,mid}]` |
| `compare` | `ticker` + `comparisons=CSV` (+`window`) | multi-fetch `ds:13` | `series{t:{quote,n,norm[{d,p,pct}]}}` normalized % overlay |
| `calendar` | — | beta `ds:3` earnings calendar | `events[{t,ex,date,title}] + indices[] + futures[]` |
| `indices` | — | `ds:0` kind=1 | `indices[{t,ex,name,p,ch,chp,label}]` (DJIA, S&P, Nasdaq, RUT, DAX…) |
| `futures` | — | `ds:0` kind=7 | `futures[{t,ex,name,p,ch,chp,label}]` (YMW00/ESW00/NQW00/GCW00/CLW00) |
| `gainers` | — | `ds:9` on `/markets/gainers` | `tickers[] + quotes[{t,ex,name,p,ch,chp}]` (retry-safe) |
| `losers` | — | `ds:9` on `/markets/losers` | same shape |
| `most_active` | — | `ds:9` on `/markets/most-active` | same shape |
| `trending` | — | `ds:9` on `/markets/trending` (same Wiz shell alias) | same shape |
| `crypto` | — | `BTC-USD` quote + `ds:6` peers + `ds:19/20` news | `btc{quote} + peers[] + news[]` |
| `fx` | — | `EUR-USD` quote + `ds:6` pairs | `eurusd{quote} + pairs[]` |
| `etf` | `ticker` e.g. `QQQ:NASDAQ` | `ds:4` holdings + quote | `quote + holdings + about` |
| `convert` | `amount` + `from` + `to` or `ticker="100 USD EUR"` | `quote USD-EUR` (and reverse) | `rate + converted + pair + quote` (numeric-only `after` guard) |
| `stats` | `ticker` | `ds:10` OHLC/mcap/vol/sector + `ds:17` mirror + `ds:5/15` ratios (valuation×12) | `stats{open,high,low,mcap,vol,sector,pe,eps,beta,div_yield,…}` |
| `overview` | `ticker` | composite `quote+stats+peers+news+about+analyst+history[:30]` one call | `quote + stats + peers + news + about + analyst + history` |
| `chat` | `message` + `session` (auto-created) + `reset` | live `quote+news+indices` + `~/.hermes/gfinance_output/chat_sessions/<sid>.json` (30-turn) + optional Gemini | `reply + tickers[] + quotes[] + session/turn/history_len` — deterministic keep-if-works, see `references/chat-multiturn.md` |
| `help` | — | — | action list + examples |

Compact keys (`p/ch/chp/prev/vol/mcap/t/ex/cur`) keep responses token-efficient.
Large history arrays spill to `~/.hermes/gfinance_output/gfinance_*.json`.
Chat sessions spill to `~/.hermes/gfinance_output/chat_sessions/<sid>.json`.

## Wiz AF Parsing (Reusable Pattern)

See `references/wiz-af-parsing.md` for the full balanced-JSON extractor and
`references/chat-multiturn.md` for the multi-turn Finance AI.

Key points:
- Locate `AF_initDataCallback`, then `data:[`, then balanced-bracket JSON walk
  with `in_str`/`esc` tracking — not regex.
- Skip pseudo-key `"(prefers-color-scheme: dark)"`.
- `ds:3` price array is `[price, chg, pct, 2,2,2]` where `pct` is already percent
  (`-1.533` = -1.53%) — **do not** `*100` (caught live: -153% bug).
- `ds:11` minute ticks: `[[Y,M,D,h,m,…],[price,chg,pct], vol]`.
- `ds:13` daily: `[[Y,M,D,16,…],[price,chg,pct], vol]`.

## Token Efficiency

- Schema ~300 tokens; responses use 1-2 char keys.
- Spill threshold 9k chars → file pointer `{file,n,chars,preview}`.
- Quote is ~800 bytes; history with 21+79+30 points is ~12k (spills to file).

## Pitfalls

- **Percent scaling**: `chp` from Wiz is already percent. Multiplying by 100
  turns -1.53% into -153%. Fixed in `gfinance_tool.py:145` — always `_rnd(chgp)` not `_rnd(chgp*100)`.
- **FX `after` guard**: `FX` quotes have `rec[15]` as `["EUR","USD","Euro"]` (string labels), not after-hours prices. Must guard `raw_after = rec[15] if len(rec[15])>=3 and isinstance(rec[15][0], (int,float))` else `after=None` — otherwise FX quote leaked `after:{p:"USD"}` strings (2026-08-12).
- **Empty ticker**: `history ""` must return `{"ok":false,"error":"ticker required"}` not `ok:true+warn`.
- **Lint red**: `ruff` flags `E401` (split `import json, re, time`), `F841` (unused `s = _j.dumps(v)`, `qp`), `E702` (semicolon one-liners `a["ok"]=True; a["t"]=...` and `p=q.get("p"); ch=q.get("ch")`). Plugin shows red until all fixed — see `references/lint-cleanup.md`.
- **Plugin wiring**: copy `.py` to `~/.hermes/plugins/hermes_local_tools/`, add `gfinance` to `plugin.yaml` tags/description (`kind: standalone`), restart gateway **from outside** (`hermes gateway restart` is blocked inside gateway).
- **History dedup**: `ds:13` + `ds:14` overlap — dedup by date string.
- **Chat wiring**: dispatcher must strip `message/session/reset` from `**kw` before delegating to `_action_chat`, and ticker detection must use `KNOWN_TICKERS` allowlist — see `references/chat-multiturn.md`.
- **Markets unwrapping**: beta `ds:0 = [[groups], flag]` and `ds:2 = [[[sectors,…]]]` are double-wrapped; requires `v0[0]` / `v[0][0]` unwrapping and flat-vs-grouped sector handling — see `references/wiz-af-parsing.md`. Also `/finance/*` vs `/finance/markets/*` are same shell (2026-08-11) — parser slices differ, not server.
- **Crypto history `len==2`**: `ds:13` crypto daily entries can be `[ [Y,M,D], [p,chg,pct] ]` without vol (`len==2`), versus equity `len==3`. Fix `for k in (\"ds:13\",\"ds:14\")` walk: check `len(x) in (2,3)` and `vol = x[2] if len==3 else None` (2026-08-11).
- **Burst timeouts**: probing `markets/*` in parallel `Read timed out` — `_fetch_blocks` retries 3× with `0.6s*(attempt+1)` backoff. Thin `GC00:COMEX` sparse → `quote not found` expected; out-of-hours `gainers==losers` is provider behavior.

## Verification

```bash
python3 -m py_compile ~/.hermes/plugins/hermes_local_tools/gfinance_tool.py
ruff check ~/.hermes/plugins/hermes_local_tools/gfinance_tool.py  # must be "All checks passed"
python3 /tmp/gfinance_cli.py quote AAPL:NASDAQ --pretty   # p ~308.26, chp ~-1.53
python3 /tmp/gfinance_cli.py history AAPL:NASDAQ --window 1D --pretty
python3 /tmp/gfinance_cli.py search --query NVDA --pretty
# After plugin.yaml edit, from an OUTSIDE shell:
hermes gateway restart && hermes tools list | grep gfinance
```

## References

- `references/wiz-af-parsing.md` — AF extractor, ds:* map, live decode traces
- `references/sitemap.md` — full-site URL→ds inventory (beta/canonical/markets/quote/search, 2026-08-11 probe)
- `references/ds-inventory.md` — ds:0..ds:22 field-by-field decode (incl. ds:5/15 stats, ds:10/17)
- `references/chat-multiturn.md` — multi-turn Finance AI (keep-if-works, 30-turn carry-forward)
- `references/deep-test-2026-08-11.md` — full deep-test matrix (34/42 burst-ok + retry → 42/42 sequential)
- `references/lint-cleanup.md` — ruff fixes that cleared the red status
- `references/full-site-mapping-2026-08-11.md` — whole-site mapping session (trending/stats/overview added, len==2 crypto fix)
