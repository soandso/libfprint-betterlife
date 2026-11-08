"""One identify, no writes."""
import os, sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import btl
b = btl.Btl(debug=True)
try:
    b.init()
    print("count:", b.fp_count(), flush=True)
    print("--- TOUCH NOW", flush=True)
    r = b.identify(timeout=40)
    print("RESULT", r[0] if r else None, r[1] if r else None, r[2].hex(" ") if r else "", btl.STATUS.get(r[0]) if r else "timeout", flush=True)
finally:
    b.close()
