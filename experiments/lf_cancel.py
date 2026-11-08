"""Cancel test: start identify (no touch), cancel after 3 s; repeat for enroll; check the module still works."""
import gi
gi.require_version("FPrint", "2.0")
from gi.repository import FPrint, GLib, Gio

ctx = FPrint.Context()
dev = [x for x in ctx.get_devices() if x.get_driver() == "betterlife"][0]
dev.open_sync()
loop = GLib.MainLoop()

def run_cancelled(start, finish, name):
    c = Gio.Cancellable()
    res = {}
    def done(d, r):
        try:
            finish(r); res["r"] = "completed?!"
        except GLib.Error as e:
            res["r"] = f"{e.domain}:{e.code} {e.message}"
        loop.quit()
    start(c, done)
    GLib.timeout_add(3000, lambda: (c.cancel(), False)[1])
    loop.run()
    print(f"{name} cancelled ->", res["r"], flush=True)

run_cancelled(lambda c, cb: dev.identify([], c, None, None, cb), dev.identify_finish, "identify")
tpl = FPrint.Print.new(dev)
run_cancelled(lambda c, cb: dev.enroll(tpl, c, None, None, cb), dev.enroll_finish, "enroll")
run_cancelled(lambda c, cb: dev.identify([], c, None, None, cb), dev.identify_finish, "identify again")
dev.close_sync()
print("closed OK", flush=True)
