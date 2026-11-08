"""Enroll ONE template (writes module flash), then identify 3 times."""
import os, sys, time
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import btl
b = btl.Btl(debug=True)
P = lambda *a: print(*a, flush=True)
try:
    b.init()
    P("count before:", b.fp_count())
    st = b.enroll_start(); P("START", st.hex(" "))
    need, done = st[1], 0
    for attempt in range(25):
        P(f"--- touch {done + 1}/{need}: TOUCH, then lift")
        r = b.enroll_touch(done + 1, timeout=25)
        P("TOUCH RESULT", r, btl.STATUS.get(r[0]) if r else "timeout")
        if r is None:
            break
        if r[0] == 0:
            done += 1
            if r[1] is not None and r[1] >= need or done >= need:
                break
        time.sleep(0.3)
    fin = b.enroll_finish(b"BTLTEST2".ljust(32, b"\0"))
    P("FINISH", fin.hex(" "))
    P("count after:", b.fp_count())
    for i in range(3):
        P(f"--- identify {i + 1}/3: TOUCH")
        r = b.identify(timeout=25)
        P("ID RESULT", r[0] if r else None, r[1] if r else None, r[2].hex(" ") if r else "", btl.STATUS.get(r[0]) if r else "timeout")
except Exception as e:
    P("EXCEPTION", repr(e))
    try: b.enroll_cancel()
    except Exception: pass
finally:
    b.close()
    P("DONE")
