# Chat — Multi-Turn Finance AI (gfinance `chat`)

Live-anchored chat over Google Finance Wiz data. No API key required; optional Gemini enhancement when `GEMINI_API_KEY` / `GOOGLE_API_KEY` is set.

## Interface

```python
gfinance chat message="How is NVDA doing today?"                # → {session, reply, tickers, quotes, turn}
gfinance chat message="What about its peers?" session=<sid>     # follow-up carries NVDA context
gfinance chat session=<sid>                                      # history only: {history, n}
gfinance chat session=<sid> reset=true                           # clear session
```

- `session` auto-created (`uuid hex[:12]`) if omitted; pass back for multi-turn.
- History kept at `~/.hermes/gfinance_output/chat_sessions/<sid>.json` — last 30 messages (`{role, content, tickers, quotes, ts}`).
- Schema additions: `message`, `session`, `comparisons`, `amount`, `from`, `to`.

## How It Works

1. **Ticker detection** (`_detect_tickers`): regex `TICKER:EXCH` / `XXX-YYY` plus 30 known bare tickers (`AAPL,NVDA,TSLA,MSFT,GOOGL,AMZN,META,SPY,QQQ,BTC,ETH,AMD,NFLX…`). Bare words like `IS/DOING/TODAY` are NOT kept — fixes v1 noise where "How is NVDA doing today?" yielded `["IS","NVDA","DOING","TODAY"]`.
2. **Live context** (`_chat_context`): for each detected ticker (≤4), fetch `quote + news[:5]` via `_quote_url` → `_parse_af` → `_extract_quote/_extract_news`. Normalized candidates: `NVDA` → `[NVDA:NASDAQ, NVDA:NYSE, NVDA]`.
3. **Intent routing**: `peer/competitor/rival/compar` in `message.lower()` → fetch `ds:6` peers via `_extract_peers` and return `**Peers of NVDA:**` list (early return, saves history). Other intents (`news/history/compare`) currently handled via live context + carry-forward; reserved slots in `lower_msg` for future expansion.
4. **Carry-forward**: if current `tickers==[]` and history has prior tickers, reuse `effective_tickers` from last 4 turns (filtered to `_KNOWN_TICKERS` or `:`/`-` forms) — e.g. "What about its peers?" after NVDA → peers of NVDA; `_chat_context([effective])` prefills reply header `Carrying context from **NVDA**: …`.
5. **Deterministic reply** (always works): formats `Name (T:EX) **p** ▲/▼ ch (chp%)` + `**Headlines:**` (3). Falls back to `markets` snapshot (`_extract_markets_overview` indices[:5]) or prompt to ask a ticker. No external LLM needed.
6. **Optional Gemini**: if `api_key` (kw or env) and `len(message)<2000`, calls `google.generativeai.GenerativeModel("gemini-1.5-flash")` with `live_block={quotes[:3], news[:3]}` + `hist_block` (last 6 turns); failure silently keeps deterministic reply.

## Dispatcher Fix (Pitfall)

`gfinance_run` previously did `_action_chat(message=kw.get("message") or ticker…, ticker=ticker, **kw)` causing `TypeError: got multiple values for message` when `ticker`/`query` leaked via `**kw`. Fixed to:

```python
chat_msg = (kw.get("message") or ticker or query or "").strip()
chat_session = (kw.get("session") or kw.get("session_id") or kw.get("sid") or "").strip()
kw2 = {k:v for k,v in kw.items() if k not in ("message","session","session_id","sid","reset")}
return _action_chat(message=chat_msg, session=chat_session, reset=bool(kw.get("reset")), **kw2)
```

## Live Test (2026-08-12)

```
chat1 "How is NVDA doing today?" → tickers=['NVDA'] → NVIDIA Corp **217.55** ▼ -6.41 (-2.86%) + 3 headlines
chat2 "What about its peers?"    → Peers of NVDA: AAPL 308.26 ▼ -1.53%, TSLA 330.88 ▲ +0.70%, …
chat3 "Compare it with AAPL"     → AAPL quote + headlines (effective_tickers carry)
history → n=6 msgs, session=0b8ade1b7fc5
```

## Pitfalls

- Empty `message` with `session` returns history — not an error.
- `reset=true` deletes `<sid>.json` and returns `{reset:true}`.
- Ticker detection must NOT keep bare common words; use allowlist `KNOWN_TICKERS`.
- Always strip `message/session/reset` from `**kw` before delegating to `_action_chat`.
