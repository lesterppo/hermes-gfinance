#!/usr/bin/env python3
"""Standalone CLI wrapper for gfinance_tool — also usable outside Hermes."""
import sys, json, argparse
sys.path.insert(0, "~/.hermes/plugins/hermes_local_tools")
import gfinance_tool

def main():
    p=argparse.ArgumentParser(prog="gfinance", description="Google Finance CLI (google.com/finance Wiz)")
    p.add_argument("action", nargs="?", default="help", help="quote|history|intraday|fundamentals|news|analyst|about|search|markets")
    p.add_argument("ticker", nargs="?", default="", help="ticker e.g. AAPL:NASDAQ, 0700:HKG, BTC-USD")
    p.add_argument("--query","-q", default="")
    p.add_argument("--window","-w", default="")
    p.add_argument("--pretty", action="store_true")
    a=p.parse_args()
    # map positional ticker to correct field
    kwargs=dict(action=a.action, ticker=a.ticker, query=a.query, window=a.window)
    out=gfinance_tool.gfinance_run(**kwargs)
    if a.pretty:
        try: print(json.dumps(json.loads(out), indent=2, ensure_ascii=False))
        except: print(out)
    else:
        print(out)

if __name__=="__main__":
    main()
