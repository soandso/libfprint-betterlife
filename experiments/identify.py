"""Identify test: no flash writes. Usage: run from repo root."""
import os, sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import btl
b = btl.Btl(debug=True)
try:
    b.init()
    print("count:", b.fp_count(), flush=True)
    for i in range(2):
        print(f"--- identify #{i+1}: TOUCH NOW", flush=True)
        r = b.identify(timeout=25)
        print("RESULT", r, btl.STATUS.get(r[0]) if r else "timeout", flush=True)
finally:
    b.close()
