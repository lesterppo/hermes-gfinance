#!/usr/bin/env python3
"""
GFinance — AI-agent-native token-efficient CLI for Google Finance (Wiz SPA).

Backend: fetches google.com/finance pages and parses AF_initDataCallback
embedded JSON (no batchexecute RPC required).  Covers full Finance surface:
quote/history/intraday/fundamentals/news/analyst/about/search/markets/
peers/compare/calendar/indices/futures/gainers/losers/most_active/trending/
crypto/fx/etf/convert/stats/overview + multi-turn chat (Finance AI).
Site map: google.com/finance (beta + canonical), /finance/markets/*,
/finance/quote/*, /finance/beta/search.  No API key.  Chat is deterministic
with live anchoring; optional Gemini API key for LLM rephrase.

Author: Peter/lesterppo
"""
from __future__ import annotations
import json
import re
import time
import uuid
from pathlib import Path
from typing import Any, Dict, List

try:
    from hermes_constants import get_hermes_home
except ImportError:
    def get_hermes_home() -> Path:
        return Path.home() / ".hermes"

import requests

_HDR = {"User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36"}
_TIMEOUT = 12
_INLINE_CAP = 9000
_VALID_WINDOWS = {"", "1D", "5D", "1M", "6M", "1Y", "5Y", "MAX"}
_CHAT_DIR = Path(get_hermes_home()) / "gfinance_output" / "chat_sessions"

# ── AF parser ────────────────────────────────────────────────────────────────

def _parse_af(html: str) -> Dict[str, Any]:
    out: Dict[str, Any] = {}
    pos = 0
    while True:
        idx = html.find("AF_initDataCallback", pos)
        if idx == -1:
            break
        k1 = html.find("'", idx)
        k2 = html.find("'", k1 + 1) if k1 != -1 else -1
        key = html[k1 + 1:k2] if k1 != -1 and k2 != -1 else "?"
        if key in ("(prefers-color-scheme: dark)", "?"):
            pos = idx + 1
            continue
        di = html.find("data:[", idx)
        if di == -1:
            pos = idx + 1
            continue
        start = di + 5
        depth = 0
        in_str = False
        esc = False
        end = -1
        for j, c in enumerate(html[start:]):
            if esc:
                esc = False
                continue
            if c == "\\":
                esc = True
                continue
            if c == '"' and not esc:
                in_str = not in_str
                continue
            if in_str:
                continue
            if c == "[":
                depth += 1
            elif c == "]":
                depth -= 1
                if depth == 0:
                    end = start + j + 1
                    break
        if end == -1:
            pos = idx + 1
            continue
        raw = html[start:end]
        try:
            data = json.loads(raw)
        except Exception:
            pos = end
            continue
        out[key] = data
        pos = end
    return out

def _fetch_blocks(url: str) -> tuple[str, Dict[str, Any]]:
    last: Exception | None = None
    for attempt in range(3):
        try:
            r = requests.get(url, headers=_HDR, timeout=_TIMEOUT)
            r.raise_for_status()
            html = r.text
            return html, _parse_af(html)
        except Exception as e:
            last = e
            if attempt < 2:
                time.sleep(0.6 * (attempt + 1))
                continue
            raise last  # type: ignore[misc]

def _resolve_ticker(ticker: str) -> str:
    t = ticker.strip().upper()
    if not t:
        return t
    # Google Finance uses dash for crypto/FX: BTC-USD not BTC/USD
    if "/" in t and ":" not in t and "-" not in t:
        # only convert slash pairs like BTC/USD, EUR/USD — not paths
        if re.match(r"^[A-Z0-9.]+/[A-Z0-9.]+$", t):
            t = t.replace("/", "-")
    return t

def _quote_url(ticker: str, window: str = "") -> str:
    ticker = _resolve_ticker(ticker)
    base = f"https://www.google.com/finance/quote/{ticker}"
    if window:
        return f"{base}?window={window}"
    return base

def _compare_url(ticker: str, comparisons: List[str]) -> str:
    base = _quote_url(ticker)
    if comparisons:
        qs = "&".join(f"comparison={requests.utils.quote(c)}" for c in comparisons)
        return f"{base}?{qs}"
    return base

# ── Decoders ─────────────────────────────────────────────────────────────────

def _rnd(v):
    if v is None or (isinstance(v, float) and (v != v)):
        return None
    if isinstance(v, (int, float)):
        return round(float(v), 4)
    return v

def _extract_quote(blocks: Dict[str, Any]) -> Dict[str, Any]:
    for k in ("ds:2", "ds:3", "ds:16", "ds:10", "ds:17", "ds:15"):
        v = blocks.get(k)
        if not v:
            continue
        try:
            if k in ("ds:2", "ds:3", "ds:16"):
                inner = v[0][0]
                rec = inner[0] if isinstance(inner[0], list) else inner
                if len(rec) < 8:
                    continue
                # Google repurposed ds:3 as a company-profile record
                # (description/HQ/founded/CEO at the old quote positions). A
                # real quote record always carries rec[5] = [price, chg,
                # chgpct, ...] with a numeric price — skip anything else.
                price_arr_chk = rec[5] if isinstance(rec[5], list) else []
                if not (len(price_arr_chk) >= 1 and isinstance(price_arr_chk[0], (int, float))):
                    continue
                mid = rec[0]
                pair = rec[1] if isinstance(rec[1], list) else [None, None]
                name = rec[2]
                cur = rec[4]
                price_arr = rec[5] if isinstance(rec[5], list) else []
                prev = rec[7]
                price = price_arr[0] if len(price_arr) > 0 else None
                chg = price_arr[1] if len(price_arr) > 1 else None
                chgp = price_arr[2] if len(price_arr) > 2 else None
                tz = rec[12] if len(rec) > 12 else None
                raw_after = rec[15] if len(rec) > 15 and isinstance(rec[15], list) and len(rec[15]) >= 3 else None
                after = raw_after if raw_after and isinstance(raw_after[0], (int,float)) else None
                return {
                    "mid": mid,
                    "t": pair[0] if len(pair) > 0 else None,
                    "ex": pair[1] if len(pair) > 1 else None,
                    "name": name,
                    "cur": cur,
                    "p": _rnd(price),
                    "ch": _rnd(chg),
                    "chp": _rnd(chgp) if chgp is not None else None,
                    "prev": _rnd(prev),
                    "tz": tz,
                    "after": {"p": _rnd(after[0]), "ch": _rnd(after[1]), "chp": _rnd(after[2])} if after and len(after) >= 3 else None,
                    "_src": k,
                }
            elif k == "ds:10":
                row = v[0][0]
                if not isinstance(row, list) or len(row) < 16:
                    continue
                pair = row[0][1] if isinstance(row[0], list) and len(row[0]) > 1 else [None, None]
                price = row[2]
                mid = row[3]
                prev = row[15] if len(row) > 15 else None
                chg = row[8] if len(row) > 8 else None
                chgp = row[10] if len(row) > 10 else None
                cur = row[12] if len(row) > 12 else None
                name = row[14] if len(row) > 14 else None
                return {
                    "t": pair[0] if isinstance(pair, list) and len(pair) > 0 else None,
                    "ex": pair[1] if isinstance(pair, list) and len(pair) > 1 else None,
                    "mid": mid,
                    "name": name,
                    "cur": cur,
                    "p": _rnd(price),
                    "ch": _rnd(chg),
                    "chp": _rnd(chgp if isinstance(chgp, (int, float)) else chgp),
                    "prev": _rnd(prev),
                    "_src": k,
                }
        except Exception:
            continue
    return {}

def _extract_ohlc_intraday(blocks: Dict[str, Any]) -> List[Dict[str, Any]]:
    v = blocks.get("ds:12")
    if not v:
        return []
    candles: List[Dict[str, Any]] = []
    try:
        for a in v:
            if not isinstance(a, list):
                continue
            for b in a:
                if not isinstance(b, list):
                    continue
                for c in b:
                    if not isinstance(c, list) or len(c) < 4:
                        continue
                    if len(c) >= 4 and isinstance(c[3], list):
                        inner = c[3]
                        if isinstance(inner, list) and len(inner) > 0:
                            for grp in inner:
                                if not isinstance(grp, list):
                                    continue
                                cand_list = None
                                if len(grp) >= 3 and isinstance(grp[2], list):
                                    cand_list = grp[2]
                                elif len(grp) >= 2 and isinstance(grp[1], list):
                                    cand_list = grp[1]
                                else:
                                    cand_list = grp
                                if not isinstance(cand_list, list):
                                    continue
                                for cand in cand_list:
                                    if not isinstance(cand, list):
                                        continue
                                    if len(cand) >= 5 and isinstance(cand[-2], str) and "T" in cand[-2]:
                                        iso = cand[-2]
                                        vol = cand[-1] if isinstance(cand[-1], (int, float)) else None
                                        nums = cand[:-2]
                                        candles.append({"t": iso, "v": nums, "vol": vol})
        if not candles:
            def walk(x):
                if isinstance(x, list):
                    if len(x) >= 5 and isinstance(x[4], str) and "T" in x[4] and isinstance(x[0], (int, float)):
                        candles.append({"t": x[4], "v": x[:4], "vol": x[5] if len(x) > 5 else None})
                    else:
                        for y in x:
                            walk(y)
            walk(v)
        return candles[:2000]
    except Exception:
        return []

def _extract_minute(blocks: Dict[str, Any]) -> List[Dict[str, Any]]:
    v = blocks.get("ds:11")
    if not v:
        return []
    out: List[Dict[str, Any]] = []
    try:
        def walk(x):
            if isinstance(x, list):
                if len(x) == 3 and isinstance(x[0], list) and isinstance(x[1], list) and isinstance(x[2], (int, float)):
                    ts_arr = x[0]
                    price_arr = x[1]
                    vol = x[2]
                    if len(ts_arr) >= 5 and isinstance(price_arr, list) and len(price_arr) >= 1:
                        y, mo, d, h, mi = ts_arr[0], ts_arr[1], ts_arr[2], ts_arr[3], ts_arr[4]
                        iso = f"{y:04d}-{mo:02d}-{d:02d}T{h:02d}:{mi:02d}:00"
                        out.append({"t": iso, "p": price_arr[0], "ch": price_arr[1] if len(price_arr) > 1 else None, "chp": price_arr[2] if len(price_arr) > 2 else None, "vol": vol})
                        return
                for y in x:
                    walk(y)
        walk(v)
        return out[:3000]
    except Exception:
        return out

def _extract_daily(blocks: Dict[str, Any]) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    for k in ("ds:13", "ds:14"):
        v = blocks.get(k)
        if not v:
            continue
        try:
            def walk(x):
                if isinstance(x, list):
                    if len(x) in (2, 3) and isinstance(x[0], list) and isinstance(x[1], list):
                        ts_arr = x[0]
                        price_arr = x[1]
                        vol = x[2] if len(x) == 3 else None
                        if len(ts_arr) >= 3 and ts_arr[0] and ts_arr[1] and ts_arr[2] and isinstance(price_arr, list):
                            y, mo, d = ts_arr[0], ts_arr[1], ts_arr[2]
                            iso = f"{y:04d}-{mo:02d}-{d:02d}"
                            if k == "ds:13":
                                out.append({"d": iso, "p": price_arr[0], "ch": price_arr[1] if len(price_arr) > 1 else None, "chp": price_arr[2] if len(price_arr) > 2 else None, "vol": vol})
                            return
                    if len(x) == 6 and isinstance(x[4], str) and "T" in x[4] and isinstance(x[0], (int, float)):
                        out.append({"d": x[4][:10], "o": x[0], "c": x[1], "h": x[2], "l": x[3], "vol": x[5], "_k": k})
                        return
                    for y in x:
                        walk(y)
            walk(v)
            if out:
                break
        except Exception:
            continue
    seen = set()
    deduped = []
    for r in out:
        key = r.get("d") or r.get("t")
        if key and key not in seen:
            seen.add(key)
            deduped.append(r)
    return deduped[:3000]

def _extract_fundamentals(blocks: Dict[str, Any]) -> Dict[str, Any]:
    for k in ("ds:18", "ds:8", "ds:9"):
        v = blocks.get(k)
        if not v or not isinstance(v, list):
            continue
        try:
            # ds:18 on quote page is [[[[2027,1,[nums...]]],...]] huge
            # just count and sample
            n = len(v)
            sample = None
            def find_nums(x):
                if isinstance(x, list) and len(x) > 0 and isinstance(x[0], (int, float)) and len(x) > 5:
                    # likely a fundamentals row
                    if any(isinstance(y, (int, float)) and abs(y) > 1e6 for y in x[:5]):
                        return x
                if isinstance(x, list):
                    for y in x:
                        r = find_nums(y)
                        if r:
                            return r
                return None
            sample = find_nums(v)
            return {"periods": n, "sample": sample[:12] if sample else None, "raw_chars": len(json.dumps(v)), "src": k}
        except Exception:
            continue
    return {}

def _extract_news(blocks: Dict[str, Any]) -> List[Dict[str, Any]]:
    out = []
    # Google moved news ds:19/ds:20 -> ds:15/ds:16; keep the old keys as fallback.
    for k in ("ds:15", "ds:16", "ds:19", "ds:20"):
        v = blocks.get(k)
        if not v or not isinstance(v, list):
            continue
        for entry in v:
            if not isinstance(entry, list):
                continue
            if len(entry) >= 3 and isinstance(entry[0], str) and entry[0].startswith("http"):
                out.append({"url": entry[0], "title": entry[1] if len(entry) > 1 else "", "src": entry[2] if len(entry) > 2 else "", "ts": entry[4] if len(entry) > 4 else None})
    if not out:
        for k in ("ds:15", "ds:16", "ds:19", "ds:20"):
            v = blocks.get(k)
            if not v:
                continue
            def walk(x):
                if isinstance(x, list) and len(x) >= 2 and isinstance(x[0], str) and x[0].startswith("http") and isinstance(x[1], str) and len(x[1]) > 8:
                    out.append({"url": x[0], "title": x[1], "src": x[2] if len(x) > 2 and isinstance(x[2], str) else ""})
                elif isinstance(x, list):
                    for y in x:
                        walk(y)
            walk(v)
    return out[:30]

def _extract_analyst(blocks: Dict[str, Any]) -> Dict[str, Any]:
    v = blocks.get("ds:7")
    if not v or not isinstance(v, list):
        return {}
    try:
        summ = v[0] if len(v) > 0 and isinstance(v[0], list) else []
        recs = v[1] if len(v) > 1 and isinstance(v[1], list) else []
        analysts = []
        for r in recs[:50]:
            if not isinstance(r, list) or len(r) < 6:
                continue
            analysts.append({"id": r[0], "name": r[1], "firm": r[2], "rating": r[3], "date": r[4], "url": r[5] if len(r) > 5 else "", "title": r[16] if len(r) > 16 else ""})
        return {"summary": summ, "analysts": analysts}
    except Exception:
        return {}

def _extract_about(blocks: Dict[str, Any]) -> Dict[str, Any]:
    v = blocks.get("ds:4")
    if not v or not isinstance(v, list):
        return {}
    try:
        rec = v[0][0] if isinstance(v[0], list) and isinstance(v[0][0], list) else v[0]
        if not isinstance(rec, list) or len(rec) < 3:
            return {}
        # ETF vs equity: ETF has different shape, detect
        if len(rec) > 8 and isinstance(rec[2], (int, float)) is False and isinstance(rec[7], (int, float)):
            # equity path
            return {"desc": rec[2][:1500] if isinstance(rec[2], str) else "", "name": rec[1], "founded": rec[4] if len(rec) > 4 else None, "ceo": rec[5] if len(rec) > 5 else None, "employees": rec[6] if len(rec) > 6 else None, "sector": rec[-1] if isinstance(rec[-1], str) else None}
        # fallback: try any string >100 chars as desc
        desc = ""
        for el in rec:
            if isinstance(el, str) and len(el) > 120:
                desc = el[:1500]
                break
        return {"desc": desc, "raw": rec[:6]}
    except Exception:
        return {}


def _extract_stats(blocks: Dict[str, Any]) -> Dict[str, Any]:
    out: Dict[str, Any] = {}
    # ds:10 detail OHLC + mcap etc
    v10 = blocks.get("ds:10")
    try:
        if v10 and isinstance(v10, list) and len(v10) > 0 and isinstance(v10[0], list) and len(v10[0]) > 0 and isinstance(v10[0][0], list):
            rec = v10[0][0]
            if isinstance(rec, list) and len(rec) >= 4:
                out["open"] = rec[4] if isinstance(rec[4], (int,float)) else None
                out["high"] = rec[5] if isinstance(rec[5], (int,float)) else None
                out["low"]  = rec[6] if isinstance(rec[6], (int,float)) else None
                out["close"] = out.get("close")
            # deeper: v10[0][0] is [[null,[T,EX]], null, close, mid, open, high, low, ... , mcap at [15]]
            if isinstance(rec, list) and len(rec) > 16:
                if isinstance(rec[15], (int,float)):
                    out["mcap"] = rec[15]
                if len(rec) > 17 and isinstance(rec[17], (int,float)):
                    out["vol"] = str(rec[17])
                if len(rec) > 18 and isinstance(rec[18], str):
                    out["sector"] = rec[18]
                # ds:17 duplicate carries prev etc
    except Exception:
        pass
    # ds:17 richer detail (prev, 52w etc) — mirror of ds:10 with extra fields
    v17 = blocks.get("ds:17")
    try:
        if v17 and isinstance(v17, list) and len(v17)>0 and isinstance(v17[0], list) and len(v17[0])>0 and isinstance(v17[0][0], list):
            r17 = v17[0][0]
            if isinstance(r17, list) and len(r17) > 15:
                if "mcap" not in out and len(r17) > 15 and isinstance(r17[15], (int,float)):
                    out["mcap"] = r17[15]
                if "vol" not in out and len(r17) > 17 and isinstance(r17[17], (int,float)):
                    out["vol"] = str(r17[17])
                if "sector" not in out and len(r17) > 18 and isinstance(r17[18], str):
                    out["sector"] = r17[18]
    except Exception:
        pass
    # ds:5 ratios: [null, null, [[ticker], r1..r12]]
    v5 = blocks.get("ds:5")
    try:
        if v5 and isinstance(v5, list) and len(v5) > 2 and isinstance(v5[2], list) and len(v5[2]) > 1 and isinstance(v5[2][1], (int,float)):
            ratios = v5[2]
            labels = ["pe","eps","beta","div_yield","pe2","eps2","rev","_a","_b","_c","_d","_e"]
            for i,lab in enumerate(labels):
                idx = 1+i
                if idx < len(ratios) and isinstance(ratios[idx], (int,float)):
                    out[lab] = _rnd(ratios[idx])
            # ds:5[1] holds [ [ticker], ... ] — keep
        elif v5 and isinstance(v5, list):
            # alternate: v5 is [null, null, [[ticker], r..]] nested one more
            for grp in v5:
                if isinstance(grp, list) and len(grp)>2 and isinstance(grp[2], list):
                    cand = grp[2]
                    if isinstance(cand, list) and len(cand)>1 and isinstance(cand[1], (int,float)):
                        for i in range(1, min(len(cand), 12)):
                            out[f"r{i}"] = _rnd(cand[i])
                        break
    except Exception:
        pass
    # ds:15 valuation: [[ticker], 12 floats] — merge as valuation block
    v15 = blocks.get("ds:15")
    try:
        if v15 and isinstance(v15, list):
            for grp in v15:
                if not isinstance(grp, list):
                    continue
                for entry in grp:
                    if isinstance(entry, list) and len(entry) >= 2 and isinstance(entry[0], list) and len(entry[0])==2:
                        # entry is [[T,EX], f1..f12]
                        if len(entry) > 1 and isinstance(entry[1], (int,float)):
                            names = ["beta","pe_ttm","eps_ttm","_x4","_x5","_x6","_x7","mcap2","_x9","_x10","_x11","div2"]
                            for i,nm in enumerate(names):
                                if 1+i < len(entry) and isinstance(entry[1+i], (int,float)):
                                    out.setdefault(nm, _rnd(entry[1+i]))
                        break
                break
    except Exception:
        pass
    # clean None/0 placeholders
    return {k:v for k,v in out.items() if v is not None}

def _extract_peers(blocks: Dict[str, Any]) -> List[Dict[str, Any]]:
    # Google moved peers ds:6 -> ds:5; ds:6 now holds analyst rows. Try both,
    # return the first that yields real quote records.
    for bk in ("ds:5", "ds:6"):
        v = blocks.get(bk)
        if not v or not isinstance(v, list):
            continue
        out = []
        for grp in v:
            if not isinstance(grp, list):
                continue
            for rec in grp:
                if not isinstance(rec, list) or len(rec) < 6:
                    continue
                # skip non-quote records (analyst rows, etc.)
                price_arr_chk = rec[5] if isinstance(rec[5], list) else []
                if not (len(price_arr_chk) >= 1 and isinstance(price_arr_chk[0], (int, float))):
                    continue
                # rec shape: ["/m/xxx", [T,EX], "Name", 0, "USD", [p,ch,pct,...], null, prev, color, country, ...]
                try:
                    mid = rec[0]
                    pair = rec[1] if isinstance(rec[1], list) else [None, None]
                    name = rec[2]
                    price_arr = rec[5] if isinstance(rec[5], list) else []
                    p = price_arr[0] if len(price_arr) > 0 else None
                    ch = price_arr[1] if len(price_arr) > 1 else None
                    chp = price_arr[2] if len(price_arr) > 2 else None
                    out.append({"t": pair[0] if len(pair) > 0 else None, "ex": pair[1] if len(pair) > 1 else None, "name": name, "p": _rnd(p), "ch": _rnd(ch), "chp": _rnd(chp), "mid": mid})
                except Exception:
                    continue
        if out:
            return out[:20]
    return []

def _extract_markets_overview(blocks: Dict[str, Any]) -> Dict[str, Any]:
    sectors: List[Dict[str, Any]] = []
    indices: List[Dict[str, Any]] = []
    futures: List[Dict[str, Any]] = []
    # ds:2 sectors
    v = blocks.get("ds:2")
    if v:
        try:
            # ds:2 shape: v = [[["sectors", [...], "Equity sectors", [[sec,...],...]]]]  (double wrapped)
            inner = v[0][0] if len(v[0]) > 0 and isinstance(v[0][0], list) and len(v[0][0]) > 3 else (v[0] if len(v[0]) > 3 else [])
            recs = inner[3] if len(inner) > 3 and isinstance(inner[3], list) else []
            # recs is flat list of 11 sector records (not grouped)
            for sec in recs:
                if not isinstance(sec, list) or len(sec) < 3:
                    continue
                if not isinstance(sec[0], list) or len(sec[0]) < 2:
                    continue
                # sec = [[null,[SIXI,INDEXCBOE]], null, 1868.5, "/g/...", 1858.82, ... , "SIXI:INDEXCBOE", "Industrials", ...]
                pair = sec[0][1] if isinstance(sec[0], list) and len(sec[0]) > 1 else None
                tid = pair[0] if isinstance(pair, list) and len(pair) > 0 else None
                exch = pair[1] if isinstance(pair, list) and len(pair) > 1 else None
                price = sec[2] if len(sec) > 2 else None
                ch = sec[8] if len(sec) > 8 else None
                chp = sec[10] if len(sec) > 10 else None
                label = sec[13] if len(sec) > 13 and isinstance(sec[13], str) else None
                name = sec[14] if len(sec) > 14 and isinstance(sec[14], str) else (label or tid)
                sectors.append({"t": tid, "ex": exch, "name": name if isinstance(name, str) else str(name)[:60], "p": _rnd(price) if isinstance(price, (int, float)) else None, "ch": _rnd(ch) if isinstance(ch, (int,float)) else None, "chp": _rnd(chp) if isinstance(chp, (int,float)) else None, "label": label})
        except Exception:
            pass
    # ds:0 futures + indices — beta shape: [[[7, [[...futures...]], [1, [[...indices...]]]], ...], flag]
    # quote-shaped: [[7, [[...]]], [1, [[...]]]]
    v0 = blocks.get("ds:0")
    if v0 and isinstance(v0, list):
        try:
            # unwrap one level if v0[0] contains [7, ...] and [1, ...]
            # Unwrap beta outer: v0 is [groups, flag] where groups=[ [7,...],[1,...],[2,...] ]
            v0_unwrapped: Any = v0
            if len(v0) == 2 and isinstance(v0[0], list) and isinstance(v0[1], int):
                # beta shape: [[groups], flag]
                inner = v0[0]
                if len(inner) > 0 and isinstance(inner[0], list) and len(inner[0]) >= 1 and isinstance(inner[0][0], int):
                    v0_unwrapped = inner
            candidates: List[Any] = []
            if len(v0_unwrapped) >= 1 and isinstance(v0_unwrapped[0], list):
                first = v0_unwrapped[0]
                if len(first) >= 1 and isinstance(first[0], list) and len(first[0]) >= 1 and first[0][0] == 7:
                    candidates = v0_unwrapped
                elif len(first) >= 1 and isinstance(first[0], int) and first[0] == 7:
                    candidates = [first] + (v0_unwrapped[1:] if len(v0_unwrapped) > 1 else [])
                else:
                    if isinstance(first, list) and len(first) > 0 and isinstance(first[0], list):
                        candidates = first
                    else:
                        candidates = v0_unwrapped
            else:
                candidates = v0_unwrapped
            # drop int flags
            candidates = [c for c in candidates if not isinstance(c, int)]

            for entry in candidates:
                if not isinstance(entry, list) or len(entry) < 2:
                    continue
                kind = entry[0]
                payload = entry[1] if len(entry) > 1 else None
                if not isinstance(payload, list):
                    continue
                if kind == 7:
                    for fut in payload:
                        if not isinstance(fut, list) or len(fut) < 2:
                            continue
                        label = fut[2] if len(fut) > 2 and isinstance(fut[2], str) else (fut[1] if len(fut) > 1 and isinstance(fut[1], str) else None)
                        # fut is [null, [[mid,[T,EX],Name,4,cur,[p,ch,pct]...]], "Label"]
                        rec = None
                        if len(fut) >= 2 and isinstance(fut[1], list) and len(fut[1]) > 0 and isinstance(fut[1][0], list) and len(fut[1][0]) > 5:
                            rec = fut[1][0]
                        if rec and isinstance(rec, list) and len(rec) > 5:
                            pair = rec[1] if isinstance(rec[1], list) else [None, None]
                            price_arr = rec[5] if isinstance(rec[5], list) else []
                            futures.append({"t": pair[0] if len(pair) > 0 else None, "ex": pair[1] if len(pair) > 1 else None, "name": rec[2], "p": _rnd(price_arr[0] if len(price_arr) > 0 else None), "ch": _rnd(price_arr[1] if len(price_arr) > 1 else None), "chp": _rnd(price_arr[2] if len(price_arr) > 2 else None), "label": label})
                elif kind == 1:
                    for idx_item in payload:
                        if not isinstance(idx_item, list) or len(idx_item) < 2:
                            continue
                        label = idx_item[2] if len(idx_item) > 2 and isinstance(idx_item[2], str) else (idx_item[1] if len(idx_item) > 1 and isinstance(idx_item[1], str) else None)
                        rec = None
                        if len(idx_item) >= 2 and isinstance(idx_item[1], list) and len(idx_item[1]) > 0 and isinstance(idx_item[1][0], list) and len(idx_item[1][0]) > 5:
                            rec = idx_item[1][0]
                        if rec and isinstance(rec, list) and len(rec) > 5:
                            pair = rec[1] if isinstance(rec[1], list) else [None, None]
                            price_arr = rec[5] if isinstance(rec[5], list) else []
                            name = rec[2] if isinstance(rec[2], str) else label
                            indices.append({"t": pair[0] if len(pair) > 0 else None, "ex": pair[1] if len(pair) > 1 else None, "name": name, "p": _rnd(price_arr[0] if len(price_arr) > 0 else None), "ch": _rnd(price_arr[1] if len(price_arr) > 1 else None), "chp": _rnd(price_arr[2] if len(price_arr) > 2 else None), "label": label})
        except Exception:
            pass
    return {"sectors": sectors[:30], "indices": indices[:20], "futures": futures[:15]}

def _extract_calendar(blocks: Dict[str, Any]) -> List[Dict[str, Any]]:
    v = blocks.get("ds:3")
    if not v or not isinstance(v, list):
        return []
    out = []
    # ds:3 on beta is [[[[ticker,ex],date,"title",[mid,[T,EX],Name,q,fy,...[nums]], type, [ts], ...], flag], ...]
    for grp in v:
        if not isinstance(grp, list):
            continue
        for entry in grp:
            if not isinstance(entry, list) or len(entry) < 3:
                continue
            try:
                pair = entry[0] if isinstance(entry[0], list) else [None, None]
                date_arr = entry[1] if isinstance(entry[1], list) else []
                title = entry[2] if isinstance(entry[2], str) else ""
                # date_arr like [2026,8,11]
                dstr = f"{date_arr[0]:04d}-{date_arr[1]:02d}-{date_arr[2]:02d}" if len(date_arr) >= 3 and isinstance(date_arr[0], int) else None
                out.append({"t": pair[0] if len(pair) > 0 else None, "ex": pair[1] if len(pair) > 1 else None, "date": dstr, "title": title})
            except Exception:
                continue
    return out[:30]

def _extract_crypto_fx(blocks: Dict[str, Any], kind: str = "crypto") -> List[Dict[str, Any]]:
    # ds:6 on BTC/EUR pages lists related instruments
    peers = _extract_peers(blocks)
    return peers

def _ok(d: Dict[str, Any]) -> str:
    return json.dumps(d, ensure_ascii=False, separators=(",", ":"))

def _err(msg: str) -> str:
    return _ok({"ok": False, "error": msg})

def _spill(obj: Any) -> Dict[str, Any]:
    s = json.dumps(obj, ensure_ascii=False)
    if len(s) <= _INLINE_CAP:
        return {"inline": obj, "spilled": False}
    out_dir = Path(get_hermes_home()) / "gfinance_output"
    out_dir.mkdir(parents=True, exist_ok=True)
    f = out_dir / f"gfinance_{int(time.time() * 1000)}.json"
    f.write_text(s)
    return {"file": str(f), "n": len(obj) if isinstance(obj, list) else None, "chars": len(s), "preview": obj[:3] if isinstance(obj, list) else str(s)[:800], "spilled": True}

# ── Actions ────────────────────────────────────────────────────────────────

def _action_quote(ticker: str, window: str = "") -> str:
    if not ticker or not ticker.strip():
        return _err("ticker required (e.g. AAPL:NASDAQ or AAPL)")
    w = (window or "").upper()
    if w and w not in _VALID_WINDOWS:
        return _err(f"invalid window '{window}'. valid: {', '.join(sorted([x for x in _VALID_WINDOWS if x]))}")
    url = _quote_url(ticker, w if w else "")
    try:
        _, blocks = _fetch_blocks(url)
    except Exception as e:
        return _err(f"fetch failed: {e}")
    if not blocks:
        return _err("no data blocks parsed (page may be blocked or ticker invalid)")
    q = _extract_quote(blocks)
    if not q:
        return _err("quote not found — check ticker (try AAPL:NASDAQ, NVDA:NASDAQ, TSLA:NASDAQ, BTC-USD)")
    ds10 = blocks.get("ds:10")
    if ds10 and isinstance(ds10, list):
        try:
            row = ds10[0][0]
            if isinstance(row, list) and len(row) >= 18:
                q["lo"] = _rnd(row[4])
                q["hi"] = _rnd(row[5])
                q["op"] = _rnd(row[6]) if len(row) > 6 else None
                q["vol"] = row[17] if len(row) > 17 else None
                q["mcap"] = row[16] if len(row) > 16 else None
        except Exception:
            pass
    q["ok"] = True
    q["url"] = url
    about = _extract_about(blocks)
    if about.get("desc"):
        q["desc"] = about["desc"][:500]
    return _ok(q)

def _action_history(ticker: str, window: str = "1M") -> str:
    if not ticker or not ticker.strip():
        return _err("ticker required")
    w = (window or "1M").upper()
    if w not in _VALID_WINDOWS or w == "":
        w = "1M"
    url = _quote_url(ticker, w)
    try:
        _, blocks = _fetch_blocks(url)
    except Exception as e:
        return _err(f"fetch failed: {e}")
    daily = _extract_daily(blocks)
    intraday = _extract_ohlc_intraday(blocks)
    minute = _extract_minute(blocks)
    q = _extract_quote(blocks)
    res: Dict[str, Any] = {"ok": True, "t": q.get("t"), "ex": q.get("ex"), "window": w, "url": url}
    if daily:
        spill = _spill(daily)
        if spill["spilled"]:
            res["daily_file"] = spill["file"]
            res["daily_n"] = spill["n"]
            res["daily_preview"] = spill["preview"]
        else:
            res["daily"] = daily
        res["daily_count"] = len(daily)
    if intraday:
        spill = _spill(intraday)
        if spill["spilled"]:
            res["intraday_file"] = spill["file"]
            res["intraday_n"] = spill["n"]
            res["intraday_preview"] = spill["preview"]
        else:
            res["intraday"] = intraday
        res["intraday_count"] = len(intraday)
    if minute:
        spill = _spill(minute)
        if spill["spilled"]:
            res["minute_file"] = spill["file"]
            res["minute_n"] = spill["n"]
            res["minute_preview"] = spill["preview"]
        else:
            res["minute"] = minute
        res["minute_count"] = len(minute)
    if not daily and not intraday and not minute:
        return _err("no history parsed — empty ticker or window has no data")
    return _ok(res)

def _action_intraday(ticker: str) -> str:
    return _action_history(ticker, window="1D")

def _action_fundamentals(ticker: str) -> str:
    if not ticker or not ticker.strip():
        return _err("ticker required")
    url = _quote_url(ticker, "")
    try:
        _, blocks = _fetch_blocks(url)
    except Exception as e:
        return _err(f"fetch failed: {e}")
    funds = _extract_fundamentals(blocks)
    return _ok({"ok": True, "t": ticker.upper(), "fundamentals": funds, "url": url})

def _action_news(ticker: str) -> str:
    if not ticker or not ticker.strip():
        return _err("ticker required")
    url = _quote_url(ticker, "")
    try:
        _, blocks = _fetch_blocks(url)
    except Exception as e:
        return _err(f"fetch failed: {e}")
    news = _extract_news(blocks)
    return _ok({"ok": True, "t": ticker.upper(), "n": len(news), "news": news, "url": url})

def _action_analyst(ticker: str) -> str:
    if not ticker or not ticker.strip():
        return _err("ticker required")
    url = _quote_url(ticker, "")
    try:
        _, blocks = _fetch_blocks(url)
    except Exception as e:
        return _err(f"fetch failed: {e}")
    a = _extract_analyst(blocks)
    a["ok"] = True
    a["t"] = ticker.upper()
    a["url"] = url
    return _ok(a)

def _action_about(ticker: str) -> str:
    if not ticker or not ticker.strip():
        return _err("ticker required")
    url = _quote_url(ticker, "")
    try:
        _, blocks = _fetch_blocks(url)
    except Exception as e:
        return _err(f"fetch failed: {e}")
    about = _extract_about(blocks)
    about["ok"] = True
    about["t"] = ticker.upper()
    about["url"] = url
    return _ok(about)

def _action_search(query: str) -> str:
    if not query or not query.strip():
        return _err("query required (e.g. 'NVDA' or 'Apple')")
    q = query.strip()
    url = f"https://www.google.com/finance/beta/search?q={requests.utils.quote(q)}"
    try:
        _, blocks = _fetch_blocks(url)
    except Exception as e:
        return _err(f"fetch failed: {e}")
    results = []
    for k, v in blocks.items():
        if not isinstance(v, list):
            continue
        if k in ("ds:8", "ds:9", "ds:10", "ds:5"):
            results.append({"ds": k, "preview": str(v)[:2000]})
    try:
        html = requests.get(url, headers=_HDR, timeout=_TIMEOUT).text
        hits = re.findall(r"/finance/quote/([A-Z0-9.\-:]+)", html)
        uniq = []
        seen = set()
        for h in hits:
            if h not in seen:
                seen.add(h)
                uniq.append(h)
        results.append({"tickers": uniq[:30]})
    except Exception:
        pass
    return _ok({"ok": True, "q": q, "results": results, "url": url})

def _action_markets() -> str:
    url = "https://www.google.com/finance/beta/?lfhs=2"
    try:
        _, blocks = _fetch_blocks(url)
    except Exception as e:
        return _err(f"fetch failed: {e}")
    m = _extract_markets_overview(blocks)
    m["ok"] = True
    m["url"] = url
    return _ok(m)

def _action_peers(ticker: str) -> str:
    if not ticker or not ticker.strip():
        return _err("ticker required")
    url = _quote_url(ticker, "")
    try:
        _, blocks = _fetch_blocks(url)
    except Exception as e:
        return _err(f"fetch failed: {e}")
    peers = _extract_peers(blocks)
    return _ok({"ok": True, "t": ticker.upper(), "n": len(peers), "peers": peers, "url": url})

def _action_calendar() -> str:
    url = "https://www.google.com/finance/beta/u/3?pageId=none"
    try:
        _, blocks = _fetch_blocks(url)
    except Exception as e:
        return _err(f"fetch failed: {e}")
    cal = _extract_calendar(blocks)
    overview = _extract_markets_overview(blocks)
    return _ok({"ok": True, "n": len(cal), "events": cal, "indices": overview.get("indices", [])[:10], "futures": overview.get("futures", [])[:10], "url": url})

def _action_compare(ticker: str, comparisons: List[str], window: str = "1M") -> str:
    if not ticker or not ticker.strip():
        return _err("ticker required; comparisons as comma-separated tickers (e.g. compare AAPL:NASDAQ MSFT:NASDAQ,GOOGL:NASDAQ)")
    comps = [c.strip().upper() for c in comparisons if c.strip()]
    w = (window or "1M").upper()
    if w not in _VALID_WINDOWS or not w:
        w = "1M"
    # fetch primary + each comparison separately (robust)
    series: Dict[str, Any] = {}
    for t in [ticker] + comps:
        try:
            _, blocks = _fetch_blocks(_quote_url(t, w))
            daily = _extract_daily(blocks)
            q = _extract_quote(blocks)
            # normalize to pct from first close
            norm = []
            if daily:
                base = None
                for d in daily:
                    px = d.get("p") or d.get("c")
                    if px is None:
                        continue
                    if base is None:
                        base = px
                    pct = ((px - base) / base * 100) if base else 0
                    norm.append({"d": d.get("d"), "p": px, "pct": round(pct, 4)})
            series[t.upper()] = {"quote": q, "n": len(daily), "norm": norm[:60], "url": _quote_url(t, w)}
        except Exception as e:
            series[t.upper()] = {"error": str(e)}
    return _ok({"ok": True, "window": w, "primary": ticker.upper(), "comparisons": comps, "series": series})

def _action_indices() -> str:
    url = "https://www.google.com/finance/beta/?lfhs=2"
    try:
        _, blocks = _fetch_blocks(url)
    except Exception as e:
        return _err(f"fetch failed: {e}")
    ov = _extract_markets_overview(blocks)
    return _ok({"ok": True, "n": len(ov["indices"]), "indices": ov["indices"], "url": url})

def _action_futures() -> str:
    url = "https://www.google.com/finance/beta/?lfhs=2"
    try:
        _, blocks = _fetch_blocks(url)
    except Exception as e:
        return _err(f"fetch failed: {e}")
    ov = _extract_markets_overview(blocks)
    return _ok({"ok": True, "n": len(ov["futures"]), "futures": ov["futures"], "url": url})


def _action_stats(ticker: str) -> str:
    if not ticker:
        return _err("ticker required")
    try:
        _, blocks = _fetch_blocks(_quote_url(ticker))
    except Exception as e:
        return _err(f"fetch failed: {e}")
    q = _extract_quote(blocks) or {}
    st = _extract_stats(blocks) or {}
    return _ok({"ok": True, "t": q.get("t"), "ex": q.get("ex"), "name": q.get("name"), "cur": q.get("cur"), "quote": q, "stats": st, "url": _quote_url(ticker)})

def _action_overview(ticker: str) -> str:
    if not ticker:
        return _err("ticker required")
    try:
        _, blocks = _fetch_blocks(_quote_url(ticker))
    except Exception as e:
        return _err(f"fetch failed: {e}")
    q = _extract_quote(blocks) or {}
    st = _extract_stats(blocks) or {}
    peers = _extract_peers(blocks)
    news = _extract_news(blocks)
    about = _extract_about(blocks)
    top = _extract_analyst(blocks)
    # history sparkline 1M
    hist = _extract_daily(blocks)  # 1M sparkline via d:13 daily
    return _ok({"ok": True, "t": q.get("t"), "ex": q.get("ex"), "name": q.get("name"), "cur": q.get("cur"),
                "quote": q, "stats": st, "peers": peers[:6], "news": news[:6], "about": {k: (v[:600] if isinstance(v,str) else v) for k,v in about.items()}, "analyst": top, "history": hist[:30], "url": _quote_url(ticker)})

def _action_trending() -> str:
    # Same shell as gainers; use markets/trending
    return _action_gainers("trending")
def _action_gainers(mode: str = "gainers") -> str:
    # mode: gainers|losers|most_active
    url_map = {"gainers": "https://www.google.com/finance/markets/gainers", "losers": "https://www.google.com/finance/markets/losers", "most_active": "https://www.google.com/finance/markets/most-active", "trending": "https://www.google.com/finance/markets/trending"}
    url = url_map.get(mode, url_map["gainers"])
    try:
        html, blocks = _fetch_blocks(url)
    except Exception as e:
        return _err(f"fetch failed: {e}")
    quotes: List[Dict[str, Any]] = []
    tickers: List[str] = []
    # gainers live in ds:9 as [[[quote_rec]], [[quote_rec]], ...] (one per page, ~5 blocks)
    for k in ("ds:9", "ds:8", "ds:5"):
        v = blocks.get(k)
        if not isinstance(v, list):
            continue
        for grp in v:
            if not isinstance(grp, list):
                continue
            for entry in grp:
                if not isinstance(entry, list):
                    continue
                rec = None
                # ds:9 gainers shape: [[[ABCL quote_rec]]] -> entry is [[quote_rec]]
                # entry[0] is [quote_rec]
                if len(entry) >= 1 and isinstance(entry[0], list) and len(entry[0]) > 5 and isinstance(entry[0][1], list):
                    rec = entry[0]
                # alternative: entry itself is quote_rec (direct)
                elif isinstance(entry, list) and len(entry) > 5 and isinstance(entry[1], list) and isinstance(entry[1][0], str):
                    rec = entry
                # also handle entry == [[quote_rec]] unwrapped
                if rec is None and len(entry) == 1 and isinstance(entry[0], list) and len(entry[0]) > 0 and isinstance(entry[0][0], list) and len(entry[0][0]) > 5:
                    rec = entry[0][0]
                if rec and len(rec) > 5 and isinstance(rec[1], list):
                    pair = rec[1]
                    price_arr = rec[5] if isinstance(rec[5], list) else []
                    tk = f"{pair[0]}:{pair[1]}" if len(pair) > 1 and pair[0] and pair[1] else (pair[0] if pair[0] else str(rec[2])[:20])
                    if tk not in tickers:
                        tickers.append(tk)
                        quotes.append({"t": pair[0] if len(pair)>0 else None, "ex": pair[1] if len(pair)>1 else None, "name": rec[2], "p": _rnd(price_arr[0] if len(price_arr)>0 else None), "ch": _rnd(price_arr[1] if len(price_arr)>1 else None), "chp": _rnd(price_arr[2] if len(price_arr)>2 else None)})
        if tickers:
            break
    if not tickers:
        try:
            hits = re.findall(r"/finance/quote/([A-Z0-9.\-:]+)", html)
            seen = set()
            for h in hits:
                if h not in seen:
                    seen.add(h)
                    tickers.append(h)
            tickers = tickers[:30]
        except Exception:
            pass
    if not quotes and tickers:
        enriched: List[Dict[str, Any]] = []
        for t in tickers[:5]:
            try:
                _, b = _fetch_blocks(_quote_url(t))
                q = _extract_quote(b)
                if q:
                    enriched.append(q)
            except Exception:
                continue
        quotes = enriched
    return _ok({"ok": True, "mode": mode, "n": len(tickers), "tickers": tickers[:30], "quotes": quotes[:15], "url": url})

def _action_crypto() -> str:
    url = "https://www.google.com/finance/quote/BTC-USD"
    try:
        _, blocks = _fetch_blocks(url)
    except Exception as e:
        return _err(f"fetch failed: {e}")
    q = _extract_quote(blocks)
    peers = _extract_crypto_fx(blocks)
    news = _extract_news(blocks)
    return _ok({"ok": True, "btc": q, "peers": peers[:15], "news": news[:10], "url": url})

def _action_fx() -> str:
    url = "https://www.google.com/finance/quote/EUR-USD"
    try:
        _, blocks = _fetch_blocks(url)
    except Exception as e:
        return _err(f"fetch failed: {e}")
    q = _extract_quote(blocks)
    peers = _extract_crypto_fx(blocks)
    return _ok({"ok": True, "eurusd": q, "pairs": peers[:15], "url": url})

def _action_convert(amount: float, frm: str, to: str) -> str:
    if not frm or not to:
        return _err("convert requires from and to currencies (e.g. convert 100 USD EUR or fx EUR-USD)")
    frm = frm.strip().upper()
    to = to.strip().upper()
    pair = f"{frm}-{to}"
    rev_pair = f"{to}-{frm}"
    for p in (pair, rev_pair):
        try:
            _, blocks = _fetch_blocks(_quote_url(p))
            q = _extract_quote(blocks)
            if q and q.get("p"):
                rate = q["p"]
                # if we fetched reverse, invert
                if p == rev_pair and rate:
                    rate = 1 / rate if rate else None
                if rate:
                    return _ok({"ok": True, "from": frm, "to": to, "amount": amount, "rate": _rnd(rate), "converted": _rnd(amount * rate), "pair": pair, "quote": q})
        except Exception:
            continue
    return _err(f"fx rate not found for {frm}/{to} (tried {pair}, {rev_pair})")

def _action_etf(ticker: str) -> str:
    if not ticker or not ticker.strip():
        return _err("ticker required (e.g. SPY:NYSEARCA, QQQ:NASDAQ)")
    url = _quote_url(ticker, "")
    try:
        html, blocks = _fetch_blocks(url)
    except Exception as e:
        return _err(f"fetch failed: {e}")
    q = _extract_quote(blocks)
    v = blocks.get("ds:4")
    holdings: Dict[str, Any] = {}
    if v and isinstance(v, list):
        try:
            rec = v[0][0] if isinstance(v[0], list) and isinstance(v[0][0], list) else v[0] if isinstance(v[0], list) else None
            if rec and isinstance(rec, list):
                holdings = {"raw": rec[:20], "aum": rec[7] if len(rec) > 7 else None, "expense": rec[20] if len(rec) > 20 else None}
        except Exception:
            pass
    about = _extract_about(blocks)
    return _ok({"ok": True, "t": ticker.upper(), "quote": q, "holdings": holdings, "about": about, "url": url})

# ── Multi-turn Chat (Finance AI) ─────────────────────────────────────────

_KNOWN_TICKERS = {"AAPL","NVDA","TSLA","MSFT","GOOGL","GOOG","AMZN","META","SPY","QQQ","BTC","ETH","AMD","NFLX","NFLX","BA","JPM","JNJ","V","MA","WMT","HD","DIS","NFLX","INTC","CSCO","ORCL","AVGO","COST","BRK.A","BRK.B"}
def _detect_tickers(msg: str) -> List[str]:
    # 1) explicit TICKER:EXCH or XXX-YYY
    cands = re.findall(r"[A-Z]{1,6}(?::[A-Z]{2,10}|-[A-Z]{2,6})", msg.upper())
    out: List[str] = []
    seen = set()
    for c in cands:
        if c not in seen:
            seen.add(c)
            out.append(c)
    # 2) known bare tickers only (avoid noise like "IS","HOW")
    for tok in re.findall(r"\b[A-Z]{2,6}\b", msg.upper()):
        if tok in _KNOWN_TICKERS and tok not in seen:
            seen.add(tok)
            out.append(tok)
    return out[:6]

def _chat_context(tickers: List[str]) -> Dict[str, Any]:
    ctx: Dict[str, Any] = {"quotes": [], "news": [], "peers": []}
    for t in tickers[:4]:
        # normalize bare -> try NASDAQ first for equities
        candidates = [t]
        if ":" not in t and "-" not in t:
            candidates = [f"{t}:NASDAQ", f"{t}:NYSE", t]
        for cand in candidates:
            try:
                _, blocks = _fetch_blocks(_quote_url(cand))
                q = _extract_quote(blocks)
                if q and q.get("p"):
                    ctx["quotes"].append(q)
                    # add news for first ticker
                    if len(ctx["news"]) == 0:
                        ctx["news"] = _extract_news(blocks)[:5]
                    break
            except Exception:
                continue
    return ctx

def _action_chat(message: str = "", session: str = "", reset: bool = False, **kw) -> str:
    # kw may contain 'session_id' alias
    if not session:
        session = kw.get("session_id") or kw.get("sid") or ""
    if reset and session:
        p = _CHAT_DIR / f"{session}.json"
        if p.exists():
            p.unlink()
        return _ok({"ok": True, "session": session, "reset": True, "msg": "session cleared"})
    if not message or not message.strip():
        # return history if session given
        if session:
            pf = _CHAT_DIR / f"{session}.json"
            if pf.exists():
                try:
                    data = json.loads(pf.read_text())
                    return _ok({"ok": True, "session": session, "history": data.get("messages", []), "n": len(data.get("messages", []))})
                except Exception as e:
                    return _err(f"read session failed: {e}")
            return _ok({"ok": True, "session": session, "history": [], "n": 0})
        return _err("message required (and optional session for multi-turn)")

    sid = session.strip() if session and session.strip() else uuid.uuid4().hex[:12]
    _CHAT_DIR.mkdir(parents=True, exist_ok=True)
    pf = _CHAT_DIR / f"{sid}.json"
    hist: List[Dict[str, Any]] = []
    if pf.exists():
        try:
            hist = json.loads(pf.read_text()).get("messages", [])
        except Exception:
            hist = []

    tickers = _detect_tickers(message)
    # also handle explicit ticker param
    explicit = (kw.get("ticker") or "").strip().upper()
    if explicit and explicit not in tickers:
        tickers.insert(0, explicit)

    ctx = _chat_context(tickers) if tickers else {}
    quotes = ctx.get("quotes", [])
    news = ctx.get("news", [])

    # Build live-anchored reply (deterministic, no external LLM key required)
    # This makes chat fully functional offline; if GEMINI_API_KEY is present, an LLM can be layered on top.
    # Intent routing for natural language follow-ups
    lower_msg = message.lower()
    intent_peers = any(w in lower_msg for w in ("peer", "competitor", "rival", "compar"))
    # reserved for future intents (news/history/compare handled via live context + history carry)
    _ = ("news" in lower_msg, "history" in lower_msg, " vs " in lower_msg)
    # resolve effective tickers: current or carried from history
    effective_tickers = tickers[:]
    if not effective_tickers and hist:
        for m in reversed(hist[-4:]):
            if m.get("tickers"):
                effective_tickers = m["tickers"][:]
                # filter to known tickers only for carry
                effective_tickers = [t for t in effective_tickers if t in _KNOWN_TICKERS or ":" in t or "-" in t]
                if effective_tickers:
                    break
    reply_parts: List[str] = []
    # Handle peers intent
    if intent_peers and effective_tickers:
        try:
            pt = effective_tickers[0]
            # normalize bare
            if ":" not in pt and "-" not in pt:
                pt = f"{pt}:NASDAQ"
            _, b = _fetch_blocks(_quote_url(pt))
            peers = _extract_peers(b)
            if peers:
                reply_parts.append(f"**Peers of {effective_tickers[0]}:**")
                for pr in peers[:6]:
                    arrow = "▲" if (pr.get("ch") or 0) >= 0 else "▼"
                    reply_parts.append(f"- {pr.get('name')} ({pr.get('t')}:{pr.get('ex')}) {pr.get('p')} {arrow} {pr.get('chp'):+.2f}%" if pr.get("chp") is not None else f"- {pr.get('name')} ({pr.get('t')}:{pr.get('ex')}) {pr.get('p')}")
                if quotes:
                    # also keep quote header
                    pass
                # peers answer is complete; skip to history save
                reply = "\n".join(reply_parts)
                entry_user = {"role": "user", "content": message, "tickers": tickers, "ts": int(time.time())}
                entry_asst = {"role": "assistant", "content": reply, "quotes": quotes[:3], "ts": int(time.time())}
                hist.extend([entry_user, entry_asst])
                hist = hist[-30:]
                pf.write_text(json.dumps({"session": sid, "messages": hist, "updated": int(time.time())}, ensure_ascii=False, indent=2))
                return _ok({"ok": True, "session": sid, "turn": len(hist)//2, "reply": reply, "tickers": tickers or effective_tickers, "quotes": quotes[:3], "history_len": len(hist)})
        except Exception:
            pass
    if quotes:
        for q in quotes:
            t = q.get("t") or "?"
            ex = q.get("ex") or ""
            tag = f"{t}:{ex}" if ex else t
            p = q.get("p")
            ch = q.get("ch")
            chp = q.get("chp")
            name = q.get("name") or tag
            if ch is not None and chp is not None:
                arrow = "▲" if ch >= 0 else "▼"
                reply_parts.append(f"{name} ({tag}) **{p}** {arrow} {ch:+.2f} ({chp:+.2f}%)")
            elif p is not None:
                reply_parts.append(f"{name} ({tag}) **{p}**")
        # add brief news
        if news:
            reply_parts.append("")
            reply_parts.append("**Headlines:**")
            for n in news[:3]:
                reply_parts.append(f"- {n.get('title','')[:110]} — {n.get('src','')}")
    else:
        # no ticker detected: provide general market snapshot
        try:
            _, b = _fetch_blocks("https://www.google.com/finance/beta/?lfhs=2")
            ov = _extract_markets_overview(b)
            if ov.get("indices"):
                reply_parts.append("**Markets snapshot (live):**")
                for idx in ov["indices"][:5]:
                    reply_parts.append(f"- {idx.get('name') or idx.get('label') or idx.get('t')}: {idx.get('p')} ({idx.get('chp'):+.2f}%)" if idx.get("chp") is not None else f"- {idx.get('name')}: {idx.get('p')}")
        except Exception:
            pass
        if not reply_parts:
            reply_parts.append("Ask me about a ticker (e.g. `AAPL:NASDAQ`, `NVDA`, `BTC-USD`, `EUR-USD`) — I pull live Google Finance data and keep conversation history for multi-turn follow-ups.")

    # incorporate history context for follow-ups
    context_note = ""
    if hist:
        # if prior turn mentioned a ticker, carry it forward when current message is ambiguous (e.g. "what about its peers?")
        prior_tickers = []
        for m in hist[-4:]:
            if m.get("tickers"):
                prior_tickers.extend(m["tickers"])
        if not tickers and prior_tickers:
            context_note = f"\n\n> Follow-up on **{prior_tickers[0]}** (from prior turns)."
            # fetch that prior ticker as context
            try:
                extra = _chat_context([prior_tickers[0]])
                if extra.get("quotes") and not quotes:
                    q = extra["quotes"][0]
                    reply_parts.insert(0, f"Carrying context from **{prior_tickers[0]}**: {q.get('name')} {q.get('p')} ({q.get('chp'):+.2f}%)")
            except Exception:
                pass

    reply = "\n".join(reply_parts) + context_note

    # optional LLM enhancement if key present (non-fatal)
    api_key = kw.get("api_key") or ""
    if not api_key:
        import os
        api_key = os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY") or ""
    if api_key and len(message) < 2000:
        try:
            import google.generativeai as genai  # type: ignore
            genai.configure(api_key=api_key)
            model = genai.GenerativeModel("gemini-1.5-flash")
            sys_prompt = "You are Google Finance AI. Answer concisely using the live market data provided. Cite prices exactly as given. Keep token-efficient."
            live_block = json.dumps({"quotes": quotes[:3], "news": news[:3]}, ensure_ascii=False)
            hist_block = "\n".join(f"{m['role']}: {m['content'][:300]}" for m in hist[-6:])
            prompt = f"{sys_prompt}\n\nHistory:\n{hist_block}\n\nLive data:\n{live_block}\n\nUser: {message}\nAssistant:"
            resp = model.generate_content(prompt)
            if resp and getattr(resp, "text", None):
                reply = resp.text.strip()[:3000]
        except Exception:
            pass  # keep deterministic reply

    entry_user = {"role": "user", "content": message, "tickers": tickers, "ts": int(time.time())}
    entry_asst = {"role": "assistant", "content": reply, "quotes": quotes[:3], "ts": int(time.time())}
    hist.extend([entry_user, entry_asst])
    # keep last 30 turns
    hist = hist[-30:]
    pf.write_text(json.dumps({"session": sid, "messages": hist, "updated": int(time.time())}, ensure_ascii=False, indent=2))

    return _ok({"ok": True, "session": sid, "turn": len(hist) // 2, "reply": reply, "tickers": tickers, "quotes": quotes[:3], "news": news[:3], "history_len": len(hist)})

# ── Dispatcher ─────────────────────────────────────────────────────────────
def gfinance_run(action: str = "", ticker: str = "", query: str = "", window: str = "", **kw: Any) -> str:
    a = (action or "").strip().lower()
    aliases = {"q": "quote", "chart": "history", "hbar": "history", "analysts": "analyst", "analyse": "analyst", "fundamental": "fundamentals", "funds": "fundamentals", "mkt": "markets", "m": "markets", "h": "history", "i": "intraday", "fxs": "fx", "forex": "fx", "currencies": "fx", "etfs": "etf", "compare": "compare", "comparison": "compare", "peers": "peers", "peer": "peers", "calendar": "calendar", "earnings": "calendar", "chat": "chat", "ask": "chat", "ai": "chat", "convert": "convert", "cc": "convert", "stats": "stats", "overview": "overview", "ov": "overview", "trending": "trending"}
    a = aliases.get(a, a)
    ticker = (ticker or kw.get("t") or kw.get("symbol") or "").strip()
    query = (query or kw.get("q") or "").strip()
    window = (window or kw.get("w") or kw.get("period") or "").strip()
    try:
        if a in ("quote", "q"):
            return _action_quote(ticker or query, window)
        elif a in ("history", "chart"):
            return _action_history(ticker or query, window or "1M")
        elif a in ("intraday", "minute"):
            return _action_intraday(ticker or query)
        elif a in ("fundamentals", "fundamental", "funds"):
            return _action_fundamentals(ticker or query)
        elif a in ("news",):
            return _action_news(ticker or query)
        elif a in ("analyst", "analysts"):
            return _action_analyst(ticker or query)
        elif a in ("about", "desc", "info"):
            return _action_about(ticker or query)
        elif a in ("search",):
            return _action_search(query or ticker)
        elif a in ("markets", "market"):
            return _action_markets()
        elif a in ("peers", "peer"):
            return _action_peers(ticker or query)
        elif a in ("calendar", "earnings"):
            return _action_calendar()
        elif a in ("compare", "comparison"):
            comps_raw = kw.get("comparisons") or kw.get("comparison") or kw.get("tickers") or query
            if isinstance(comps_raw, str):
                comps = [c.strip() for c in re.split(r"[,\s]+", comps_raw) if c.strip()]
                # if ticker already in comps, remove it
                comps = [c for c in comps if c.upper() != ticker.upper()]
            elif isinstance(comps_raw, list):
                comps = [str(c).strip().upper() for c in comps_raw if str(c).strip()]
            else:
                comps = []
            return _action_compare(ticker or query, comps, window or "1M")
        elif a in ("indices", "index"):
            return _action_indices()
        elif a in ("futures", "future"):
            return _action_futures()
        elif a in ("gainers", "losers", "most_active", "trending", "trending"):
            return _action_gainers(a)
        elif a in ("stats", "stat"):
            return _action_stats(ticker or query)
        elif a in ("overview", "ov"):
            return _action_overview(ticker or query)
        elif a in ("crypto",):
            return _action_crypto()
        elif a in ("fx", "forex", "currencies"):
            return _action_fx()
        elif a in ("convert", "cc"):
            amt_raw = kw.get("amount") or kw.get("amt") or ticker or query
            # parse "100 USD EUR" or "100" with frm/to
            frm = kw.get("from") or kw.get("frm") or ""
            to = kw.get("to") or ""
            amt = 1.0
            # if ticker looks like "100 USD" try parse
            m = re.match(r"^\s*([0-9.]+)\s*([A-Z]{3})\s+([A-Z]{3})\s*$", (ticker or query or "").strip().upper())
            if m:
                amt = float(m.group(1))
                frm = m.group(2)
                to = m.group(3)
            else:
                try:
                    amt = float(str(amt_raw).strip().split()[0]) if amt_raw else 1.0
                except Exception:
                    amt = 1.0
                if not frm:
                    frm = (kw.get("pair") or "").split("-")[0] if kw.get("pair") else ""
                if not to:
                    frm_to = (kw.get("pair") or "")
                    if "-" in frm_to:
                        parts = frm_to.split("-")
                        frm = frm or parts[0]
                        to = parts[1] if len(parts) > 1 else to
            return _action_convert(amt, frm, to)
        elif a in ("etf",):
            return _action_etf(ticker or query)
        elif a in ("chat", "ask", "ai"):
            chat_msg = (kw.get("message") or ticker or query or "").strip()
            chat_session = (kw.get("session") or kw.get("session_id") or kw.get("sid") or "").strip()
            # remove conflicting keys so **kw doesn't duplicate
            kw2 = {k: v for k, v in kw.items() if k not in ("message", "session", "session_id", "sid", "reset")}
            return _action_chat(message=chat_msg, session=chat_session, reset=bool(kw.get("reset")), **kw2)
        elif a in ("", "help"):
            return _ok({"ok": True, "actions": ["quote","history","intraday","fundamentals","news","analyst","about","search","markets","peers","compare","calendar","indices","futures","gainers","losers","most_active","trending","crypto","fx","etf","convert","stats","overview","chat"], "examples": ["gfinance quote AAPL:NASDAQ","gfinance history TSLA:NASDAQ window=5D","gfinance peers NVDA:NASDAQ","gfinance compare AAPL:NASDAQ MSFT:NASDAQ,GOOGL:NASDAQ","gfinance calendar","gfinance indices","gfinance futures","gfinance gainers","gfinance crypto","gfinance fx","gfinance etf SPY:NYSEARCA","gfinance convert amount=100 from=USD to=EUR","gfinance chat message='How is NVDA doing vs peers?' session=abc"], "params": {"ticker":"TICKER:EXCH (e.g. AAPL:NASDAQ, 0700:HKG, BTC-USD)","window":"1D|5D|1M|6M|1Y|5Y|MAX","query":"search term","message":"chat message","session":"chat session id (auto-created)","comparisons":"comma-separated tickers"}, "note": "All data from google.com/finance Wiz AF blocks; no API key. Chat is multi-turn with live quotes + optional Gemini enhancement."})
        else:
            return _err(f"unknown action '{action}'. valid: quote, history, intraday, fundamentals, news, analyst, about, search, markets, peers, compare, calendar, indices, futures, gainers, losers, most_active, trending, crypto, fx, etf, convert, stats, overview, chat")
    except Exception as e:
        return _err(f"handler error: {type(e).__name__}: {e}")

# ── Schema ─────────────────────────────────────────────────────────────────
GFINANCE_SCHEMA: Dict[str, Any] = {
    "name": "gfinance",
    "description": "Google Finance — full site: quote/history/intraday/fundamentals/news/analyst/about/search/markets/peers/compare/calendar/indices/futures/gainers/losers/most_active/trending/crypto/fx/etf/convert/stats/overview + multi-turn chat (Finance AI live-anchored). AF_initDataCallback Wiz SPA. No API key.",
    "parameters": {
        "type": "object",
        "properties": {
            "action": {"type": "string", "description": "quote|history|intraday|fundamentals|news|analyst|about|search|markets|peers|compare|calendar|indices|futures|gainers|losers|most_active|trending|crypto|fx|etf|convert|stats|overview|chat"},
            "ticker": {"type": "string", "description": "Ticker like AAPL:NASDAQ, NVDA:NASDAQ, 0700:HKG, BTC-USD. For search/compare, also holds query."},
            "query": {"type": "string", "description": "Search term or comparisons (comma-separated)."},
            "window": {"type": "string", "description": "Chart window: 1D|5D|1M|6M|1Y|5Y|MAX (for quote/history/compare). Default 1M."},
            "message": {"type": "string", "description": "Chat message (for action=chat). Auto-detects tickers and pulls live context."},
            "session": {"type": "string", "description": "Chat session id (auto-created if omitted; pass back for multi-turn)."},
            "comparisons": {"type": "string", "description": "Comma-separated tickers for compare (e.g. MSFT:NASDAQ,GOOGL:NASDAQ)."},
            "amount": {"type": "number", "description": "Amount for convert."},
            "from": {"type": "string", "description": "From currency for convert (e.g. USD)."},
            "to": {"type": "string", "description": "To currency for convert (e.g. EUR)."},
        },
        "required": ["action"],
    },
}

# ── Registration ──────────────────────────────────────────────────────────
def _check() -> bool:
    try:
        import requests  # noqa: F401
        return True
    except ImportError:
        return False

try:
    from tools.registry import registry
    registry.register(
        name="gfinance",
        toolset="gfinance",
        schema=GFINANCE_SCHEMA,
        handler=lambda args, **kw: gfinance_run(
            action=args.get("action", ""),
            ticker=args.get("ticker", ""),
            query=args.get("query", ""),
            window=args.get("window", ""),
            message=args.get("message", ""),
            session=args.get("session", ""),
            comparisons=args.get("comparisons", ""),
            amount=args.get("amount", ""),
            **{**args, **kw},
        ),
        check_fn=_check,
        description=GFINANCE_SCHEMA["description"],
        emoji="📈",
    )
except Exception:
    pass
