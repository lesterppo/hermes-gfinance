# Lint Cleanup — Why gfinance Was Red (2026-08-11)

The plugin showed red because `ruff check` failed. All errors had to be fixed before the
gateway would consider the tool clean.

## Errors

| code | trigger | fix |
|------|---------|-----|
| `E401` | `import json, re, time` | Split: `import json` / `import re` / `import time` |
| `F841` | `s = _j.dumps(v)` unused | Delete line (leave `import json as _j` removed entirely) |
| `F841` | `futures = []` unused | Delete `futures=[]`, keep `sectors=[]` |
| `F841` | `except Exception as e:` where `e` unused | `except Exception:` |
| `E702` | `a["ok"]=True; a["t"]=...; a["url"]=...` | Expand to 3 lines |
| `E702` | `res["daily_file"]=…; res["daily_n"]=…; res["daily_preview"]=…` | Expand to 3 lines each (daily/intraday/minute) |
| `E702` | `seen.add(h); uniq.append(h)` | 2 lines |

## Commands

```bash
python3 -m py_compile ~/.hermes/plugins/hermes_local_tools/gfinance_tool.py
ruff check ~/.hermes/plugins/hermes_local_tools/gfinance_tool.py  # must say "All checks passed!"
```

## Lesson

Any plugin `.py` is lint-gated for the red/green indicator. Fix all `ruff` findings in the
same pass as functional fixes — don't ship with lint still red. The percentage bug
(`_rnd(chgp*100)` → `_rnd(chgp)`) was caught in the same session; functional and lint fixes
were applied together.
