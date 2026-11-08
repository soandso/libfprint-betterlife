"""Verify the print saved by the enroll example, then delete it, through libfprint/build."""
import sys
import gi
gi.require_version("FPrint", "2.0")
from gi.repository import FPrint, GLib

data = open(sys.argv[1], "rb").read()
d = GLib.Variant.new_from_bytes(GLib.VariantType("a{sv}"), GLib.Bytes.new(data), False).unpack()
ctx = FPrint.Context()
dev = [x for x in ctx.get_devices() if x.get_driver() == "betterlife"][0]
dev.open_sync()
key, blob = next(iter(d.items()))
p = FPrint.Print.deserialize(bytes(blob))
print("print", key, flush=True)
print("--- VERIFY: touch the enrolled finger NOW", flush=True)
match, _ = dev.verify_sync(p)
print("VERIFY RESULT", "MATCH" if match else "NO MATCH", flush=True)
if "--delete" in sys.argv:
    dev.delete_print_sync(p)
    print("DELETE OK", flush=True)
dev.close_sync()
