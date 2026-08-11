"""Quickstart - gfinance via Hermes tool call."""
import sys, json
sys.path.insert(0, "tools")
import tools.gfinance_tool as g
def run(**kw):
    return json.loads(g.gfinance_run(**kw))
print(run(action="help")["actions"])
print(run(action="quote", ticker="AAPL:NASDAQ"))
print(run(action="history", ticker="AAPL:NASDAQ", window="1M")["daily_count"])
print(run(action="peers", ticker="NVDA:NASDAQ")["peers"][:2])
print(run(action="chat", message="How is NVDA doing?")["reply"][:300])
