#!/usr/bin/env python3
"""Standalone CLI wrapper for gfinance_tool — also usable outside Hermes."""
import sys, json, argparse, os, re
sys.path.insert(0, os.path.expanduser("~/.hermes/plugins/hermes_local_tools"))
import gfinance_tool

def main():
    p=argparse.ArgumentParser(prog="gfinance", description="Google Finance CLI (google.com/finance Wiz)")
    p.add_argument("action", nargs="?", default="help", help="quote|history|intraday|fundamentals|news|analyst|about|search|markets")
    p.add_argument("ticker", nargs="?", default="", help="ticker e.g. AAPL:NASDAQ, 0700:HKG, BTC-USD")
    p.add_argument("--query","-q", default="")
    p.add_argument("--window","-w", default="")
    p.add_argument("--pretty", action="store_true")
    a, extra = p.parse_known_args()
    # map positional ticker to correct field
    kwargs=dict(action=a.action, ticker=a.ticker, query=a.query, window=a.window)
    # accept key=value extras (e.g. convert amount=100 from=USD to=EUR,
    # compare AAPL:NASDAQ comparisons=MSFT:NASDAQ,GOOGL:NASDAQ,
    # chat message='...' session=abc). Note: argparse grabs the first
    # key=value token as the ticker positional, so reclassify it.
    kv_tokens = list(extra)
    if re.match(r"^[A-Za-z_][\w.-]*=", kwargs["ticker"] or ""):
        kv_tokens.insert(0, kwargs["ticker"])
        kwargs["ticker"] = ""
    for tok in kv_tokens:
        m = re.match(r"^([A-Za-z_][\w.-]*)=(.*)$", tok)
        if m:
            kwargs[m.group(1)] = m.group(2)
        else:
            p.error(f"unrecognized arguments: {tok}")
    out=gfinance_tool.gfinance_run(**kwargs)
    if a.pretty:
        try: print(json.dumps(json.loads(out), indent=2, ensure_ascii=False))
        except: print(out)
    else:
        print(out)
    # match the other finance CLIs: exit 2 when the result is an error
    try:
        sys.exit(0 if json.loads(out).get("ok") else 2)
    except Exception:
        sys.exit(0)

if __name__=="__main__":
    main()
