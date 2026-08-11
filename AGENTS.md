# AGENTS.md - hermes-gfinance

AI-agent-native Google Finance tool. Read this first.

## What it is

- Wiz SPA at `google.com/finance` -> AF_initDataCallback data:[...] balanced parse - no batchexecute RPC, no browser, no API key.
- 25 actions: quote | history | intraday | fundamentals | news | analyst | about | search | markets | peers | compare | calendar | indices | futures | gainers | losers | most_active | trending | crypto | fx | etf | convert | stats | overview | chat (+ help).
- Token-efficient: compact keys (p/ch/chp/prev/mcap/vol), history spill >9k -> file, chat sessions at ~/.hermes/gfinance_output/chat_sessions/<sid>.json (30-turn).
- Plugin at ~/.hermes/plugins/hermes_local_tools/gfinance_tool.py (survives hermes update); skill at ~/.hermes/skills/finance/google-finance/.

## How agents call it

```python
from tools.gfinance_tool import gfinance_run
import json
j = json.loads(gfinance_run(action="quote", ticker="AAPL:NASDAQ"))
j = json.loads(gfinance_run(action="history", ticker="AAPL:NASDAQ", window="1M"))
j = json.loads(gfinance_run(action="chat", message="How is NVDA doing?", session="abc123"))
j = json.loads(gfinance_run(action="help"))
```

Via Hermes tool: gfinance toolset - action is the only required param.

```bash
hermes tools call gfinance --action quote --ticker AAPL:NASDAQ
hermes tools call gfinance --action chat --message "What about NVDA peers?" --session <sid>
```

CLI: ~/.local/bin/gfinance (wrapper over same tool).

## Site coverage

- google.com/finance (beta pageId=none + ?lfhs=2 + /finance/markets/*) -> same Wiz shell -> ds:0 (futures/indices by kind) + ds:2 (11 CBOE sectors) + ds:9 movers [[[quote_rec]]]x12.
- /finance/quote/{TICKER:EXCH} -> rich ds:3..ds:20.
- /finance/beta/search?q= -> search.
- Crypto/FX dash form BTC-USD / EUR-USD; slash BTC/USD auto-normalized. History ds:13 len==2 crypto fix.

## References

- skill/SKILL.md - full action table + Wiz notes
- skill/references/wiz-af-parsing.md - extractor + ds:* map
- skill/references/sitemap.md - live site map (2026-08-11 probe)
- skill/references/chat-multiturn.md - multi-turn Finance AI
- plugin.yaml - plugin registration (toolset gfinance, emoji chart)
