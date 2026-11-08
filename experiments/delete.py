"""Delete test: remove template 0 (identity BTLTEST1) via B2 p1=1, then identify twice."""
import os, sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import btl
P = lambda *a: print(*a, flush=True)
b = btl.Btl(debug=True)
try:
    b.init()
    P("count before:", b.fp_count())
    P("REMOVE reply:", b.remove_identity(b"BTLTEST1".ljust(32, b"\0")).hex(" "))
    P("count after:", b.fp_count())
    for f in ("RIGHT THUMB", "RIGHT INDEX"):
        P(f"--- identify: touch {f}")
        r = b.identify(timeout=40)
        P("ID RESULT", f, r[0] if r else None, r[1] if r else None, r[2].hex(" ") if r else "", btl.STATUS.get(r[0]) if r else "timeout")
except Exception as e:
    P("EXCEPTION", repr(e))
finally:
    b.close()
    P("DONE")
