# hermes-gfinance

[![Hermes Tool](https://img.shields.io/badge/Hermes-Tool%20%E2%9C%85-blue)](https://github.com/lesterppo/hermes-gfinance) [![Google Finance](https://img.shields.io/badge/Google%20Finance-Wiz%20AF-green)](https://www.google.com/finance) [![No API Key](https://img.shields.io/badge/API%20Key-None-brightgreen)](#) [![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE) [![Python 3.11+](https://img.shields.io/badge/Python-3.11%2B-3776AB)](https://www.python.org) [![Live Test 91/91](https://img.shields.io/badge/Live%20Test-91%2F91-success)](skill/references/deep-test-2026-08-11.md)

**AI-agent-native, token-efficient Google Finance tool for Hermes Agent - full site, no API key.**

Live-parses the Google Finance Wiz SPA (AF_initDataCallback embedded JSON) - not batchexecute RPC, not browser automation. Covers google.com/finance (beta + /markets/* + /finance/quote/* + /finance/beta/search) with 25 actions and multi-turn Finance AI.

> For AI agents: read AGENTS.md first. Install via plugin.yaml -> tool gfinance (toolset gfinance). See skill/SKILL.md before calling.

## What you get

- Full surface: quote / history / intraday / fundamentals / news / analyst / about / search / markets / peers / compare / calendar / indices / futures / gainers / losers / most-active / trending / crypto / fx / etf / convert / stats / overview + chat
- No API key: plain requests + Mozilla/5.0 + balanced-bracket walk over AF_initDataCallback data:[...]
- Agent-native: 1-2 char keys (p/ch/chp/prev/mcap/vol/cur/tz), spill >9k -> file, chat 30-turn sessions
- Hermes-native: plugin survives hermes update, standalone CLI at ~/.local/bin/gfinance
- Finance AI: How is NVDA doing today? -> What about its peers? (allowlist + carry-forward)

## Quickstart

```python
from tools.gfinance_tool import gfinance_run
import json
print(json.loads(gfinance_run(action="quote", ticker="AAPL:NASDAQ")))
print(json.loads(gfinance_run(action="history", ticker="AAPL:NASDAQ", window="1M"))["daily_count"])
print(json.loads(gfinance_run(action="chat", message="How is NVDA doing today?"))["reply"][:300])
```

```bash
hermes tools call gfinance --action quote --ticker "0700:HKG"
hermes tools call gfinance --action chat --message "Convert 100 USD to EUR"
gfinance quote AAPL:NASDAQ
gfinance history TSLA:NASDAQ --window 5D
```

## Coverage map

| Source | URL | Wiz blocks | Action |
|---|---|---|---|
| Beta + Markets | google.com/finance/beta/u/3?pageId=none | ds:0 kinds 7/1/2/3/9/4/5 ds:2 11 sectors ds:9 movers | markets indices futures gainers/losers/most_active/trending calendar |
| Quote Equity/HK | /finance/quote/AAPL:NASDAQ /0700:HKG | ds:3/10/16 quote ds:11 tick ds:12 OHLC ds:13 daily ds:18 fundamentals ds:4 about ds:5/15 ratios ds:6 peers ds:7 analyst ds:19/20 news | quote history intraday fundamentals news analyst about peers stats overview compare |
| Quote Crypto/FX | /quote/BTC-USD /quote/EUR-USD (BTC/USD slash auto-normalized) | 24h buckets ds:13 len==2 fix | quote history crypto fx convert |
| Quote ETF | /quote/SPY:NYSEARCA | ds:18=news | etf |
| Search | /finance/beta/search?q=NVDA | ds:8/9/10 + regex | search |

Live sitemap: skill/references/sitemap.md

## SEO keywords

hermes-agent google-finance wiz af-initdatacallback market-data stock-quote equity ETF crypto forex FX futures indices earnings-calendar hermes-tool token-efficient agent-native

## Install

```bash
cp -r tools/gfinance_tool.py ~/.hermes/plugins/hermes_local_tools/
# merge plugin.yaml toolsets then restart gateway (outside shell):
# hermes gateway restart
cp -r skill ~/.hermes/skills/finance/google-finance
```

## Live test

2026-08-11 deep test: 91/91 (100%). Detail: skill/references/deep-test-2026-08-11.md

```bash
python tests/test_smoke.py
ruff check tools/gfinance_tool.py
```

## License

MIT - author Peter (lesterppo).
