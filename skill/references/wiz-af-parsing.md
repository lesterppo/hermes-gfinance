# Wiz AF Parsing — Google Finance

How `gfinance_tool.py` extracts data from `google.com/finance` Wiz pages without RPC.

## Extractor

```python
def _parse_af(html: str) -> dict[str, Any]:
    out = {}
    pos = 0
    while True:
        idx = html.find("AF_initDataCallback", pos)
        if idx == -1: break
        k1 = html.find("'", idx); k2 = html.find("'", k1+1)
        key = html[k1+1:k2] if k1!=-1 and k2!=-1 else "?"
        if key in ("(prefers-color-scheme: dark)", "?"):
            pos = idx+1; continue
        di = html.find("data:[", idx)
        if di == -1: pos = idx+1; continue
        start = di+5  # at [
        depth = 0; in_str = False; esc = False; end = -1
        for j,c in enumerate(html[start:]):
            if esc: esc=False; continue
            if c == "\\": esc=True; continue
            if c == '"' and not esc: in_str = not in_str; continue
            if in_str: continue
            if c == "[": depth+=1
            elif c == "]":
                depth-=1
                if depth==0: end = start+j+1; break
        raw = html[start:end]
        out[key] = json.loads(raw)
        pos = end
    return out
```

- Do **not** use regex for `data:[...]` — nested brackets require balanced walk with `in_str`/`esc`.
- Skip pseudo-key `"(prefers-color-scheme: dark)"`.

## ds:* Map (live-probed 2026-08-11/12, re-probed 2026-09-30 — Google moved several blocks; AAPL:NASDAQ + NVDA:NASDAQ + homepage)

> **2026-09-30 layout changes:** quote `ds:3`→`ds:2` (old `ds:3` is now a 72-field company-profile record: desc/HQ/founded/CEO/…), peers `ds:6`→`ds:5` (old `ds:6` now holds analyst rows), news `ds:19/20`→`ds:15/16` (old keys gone), homepage sectors `ds:2`→`ds:1`, homepage earnings calendar `ds:3`→`ds:2`, quote analysts `ds:7`→`ds:6` (old `ds:7` now holds earnings-estimate rows), quote about `ds:4`→`ds:3` (the company-profile record). Extractors try the new keys first with shape validation, falling back to the old keys.
>
> **Static-HTML limits (confirmed 2026-09-30):** the `?window=` param is ignored by the server for 1D/5D (byte-identical payloads); static pages only ever carry ~21 daily candles + today's session bars — 1Y/5Y/MAX need the chart RPC (requires running site JS). `/finance/beta/search?q=` renders the homepage without JS (no static results). ETF top-10 holdings weights are JS-rendered; the sector performance table IS in static HTML.

| key | content | shape |
|-----|---------|-------|
| `ds:0` | Markets overview (beta) — `[[groups], flag]` double-wrapped. Groups by `kind`: `7=futures`, `1=US indices`, `2=Intl indices`, `3=Nikkei`, `4=FX`, `5=crypto` | `[7, [[null, [[mid,[T,EX],name,4,cur,[p,chg,pct]]], label], …]]` per kind; unwrap `v0[0]` if `v0==[[groups],flag]` |
| `ds:1` | **Equity sectors** on the homepage (moved from `ds:2` 2026-09-30) | `[[["sectors",[mids],"Equity sectors",[[sec,…]]]]]` double-wrapped → unwrap `v[0][0]`, `inner[3]` flat sector records |
| `ds:2` | **Canonical quote (preferred) on quote pages** (moved from `ds:3` 2026-09-30); **earnings calendar** on the homepage (moved from `ds:3` 2026-09-30) | quote: `[[[[mid,[t,ex],name,0,cur,[p,chg,pct,2,2,2],null,prev,…]]]]` (27 fields); calendar: `[[[["JBL","NYSE"],[2026,9,30],"Q4 2026 Earnings Announcement",…]]]` |
| `ds:3` | **Company-profile record on quote pages** (moved here 2026-09-30; was the canonical quote): 72 fields — `[mid,name,desc,[city,state,country,code,address],[Y,M,D]founded,CEO,employees,mcap,price,…,sector@71]` | NOT a quote record (guard: `rec[5]` must be `[p,chg,pct,…]` with numeric price, else it's the profile) |
| `ds:4` | Was about (now thin — use `ds:3` profile); ETF raw block on ETF pages | — |
| `ds:5` | **Peers strip on quote page** (moved from `ds:6` 2026-09-30; also reuse for crypto peers via `BTC-USD` page) | `[[[mid,[t,ex],name,0,"USD",[p,chg,pct]…]]]` per peer group |
| `ds:6` | **Analyst summary + recs on quote pages** (moved here 2026-09-30; was peers) | `[summary[], recs[]]` — `summary=[name,cur,lo,hi,avg,…,n,"Buy",buy,hold,sell,…]`; `recs=[id,name,firm,rating,date,url,…,pt,title]` |
| `ds:7` | **Earnings-estimate rows** on quote pages (was analysts — moved to `ds:6` 2026-09-30) | — |
| `ds:8/9` | Search-preview / earnings stubs; **`ds:9` on `/markets/gainers` = gainers list `[[[quote_rec]],…]`** | gainers: `[[[[mid,[T,EX],name,0,"USD",[p,chg,pct]…]]], …]` one per group |
| `ds:10` | Quote page: **10-field quote record** `v[0][0]` + **today's 5-min session bars** at `v[0][0][3]` = `[[session_meta,[bars…]],…]`, each bar `[[Y,M,D,h,mi,…],[price,chg,pct,…],vol]` (391 regular + after-hours) | old ds:10 intraday/OHLC layout is obsolete |
| `ds:11` | **21 daily closes** `[[[Y,M,D,16,null,…],[close,chg,pct],vol]]` — NOTE: minutes are null, so the iso formatter must guard None (was silently swallowing to `[]`) | — |
| `ds:12` | **21 daily OHLC candles** (reliable; use as fallback when ds:13 lacks the series) | walker finds `[o,c,h,l,iso,vol]` → normalized to `{d,o,c,h,l,vol,_k:"ds:12"}` |
| `ds:13` | Daily close series — **absent on some page variants** (only the quote record present); `_daily_series()` falls back to ds:12 | `[[Y,M,D,16,…],[p,chg,pct],vol]` or `[o,c,h,l,iso,vol]` |
| `ds:14` | **Quarterly fundamentals** (111 metrics × recent quarters) — NOT daily OHLC (old docs were wrong); metric labels are not in the AF payload | `[year,q,[vals…],[vals…]]` per metric |
| `ds:15` | **News** (moved from `ds:19/20` 2026-09-30); alt quote on some pages | news: `[[url,title,src,favicon,ts,…]]` |
| `ds:16/17` | **News** (alt, moved from `ds:19/20` 2026-09-30); alt quotes | — |

### Stats panel (HTML, not AF)

`_extract_stats` no longer reads AF positions (`ds:10` is now the session record, `ds:5` the peers block — both yielded garbage like `high: -14400`). It parses the server-rendered stats table instead:

```python
pairs = re.findall(r'<div class="SwQK7"[^>]*>([^<]+)</div>\s*<div class="dO6ijd"[^>]*>([^<]+)</div>', html)
```

16 fields (Open, High, Low, Mkt cap, Avg vol, Volume, Dividend, Quarterly dividend, Ex-div date, P/E, 52-wk high/low, EPS, Beta, Shares outstanding, No. of employees), deduplicated by label (rendered twice for responsive layouts). Values are display strings (`"$336.96"`, `"4.81T"`).
| `ds:18` | Full fundamentals (50+ quarters, income+BS+CF per slot) | `[[[y,q,[rev,net,eps,…], [nextQ…]], …]]` — ~70k chars |
| `ds:19/20` | News (old location, pre-2026-09-30; keys now absent) | `[[url,title,src,favicon,ts,…]]` |

## Quote Decode (ds:2; was ds:3 before 2026-09-30)

```
rec = v[0][0][0]          # first quote record
mid  = rec[0]
pair = rec[1]             # [ticker, exch]
name = rec[2]
cur  = rec[4]
price_arr = rec[5]        # [p, chg, pct, 2,2,2] — pct is already %
prev = rec[7]
tz   = rec[12]
after = rec[15]           # [p,chg,pct] after-hours or null
```

Critical: `pct` is already percent (`-1.533` = -1.53%). Never `*100`.

## History Decode

- `ds:11` minute: `[[Y,M,D,h,m,…],[p,chg,pct],vol]` → `{"t":"YYYY-MM-DDThh:mm:00","p":…}`
- `ds:13` daily: `[[Y,M,D,16,…],[p,chg,pct],vol]` → `{"d":"YYYY-MM-DD","p":…}`
- `ds:12` OHLC: `[o,c,h,l,iso,vol]`; dedup daily by `d`.

## Live Probe Snippet (AAPL:NASDAQ 2026-08-11)

`ds:3` → `p=308.26 ch=-4.80 chp=-1.53 prev=313.06 tz=America/New_York`
`ds:10` extras → `lo=304.61 hi=308.26 op=308.26 vol=175894 mcap=4498802069321`
`history 1D` → `daily 21, intraday 79, minute 30`
