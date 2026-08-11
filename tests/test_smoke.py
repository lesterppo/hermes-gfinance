import sys, json, pathlib, types
sys.path.insert(0, "tools")
sys.path.insert(0, ".")
stub = types.ModuleType("hermes_constants")
stub.get_hermes_home = lambda: pathlib.Path("/tmp")
sys.modules["hermes_constants"] = stub
import tools.gfinance_tool as g
def j(**kw): return json.loads(g.gfinance_run(**kw))
def test_help(): assert len(j(action="help")["actions"]) == 25
def test_invalid(): assert j(action="quote", ticker="INVALID_TICKER_XYZ")["ok"] is False
def test_empty(): assert j(action="quote", ticker="")["ok"] is False
