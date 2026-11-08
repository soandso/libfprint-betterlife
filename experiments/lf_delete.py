"""Delete the print stored by the libfprint enroll example (experiments/lf-test) through the
libfprint driver in libfprint/build. Run with GI_TYPELIB_PATH/LD_LIBRARY_PATH set to that build."""
import sys
import gi
gi.require_version("FPrint", "2.0")
from gi.repository import FPrint, GLib

data = open(sys.argv[1], "rb").read()
d = GLib.Variant.new_from_bytes(GLib.VariantType("a{sv}"), GLib.Bytes.new(data), False).unpack()
ctx = FPrint.Context()
dev = [x for x in ctx.get_devices() if x.get_driver() == "betterlife"][0]
print("device:", dev.get_name(), "features storage:", dev.has_feature(FPrint.DeviceFeature.STORAGE))
dev.open_sync()
for key, blob in d.items():
    print("print", key)
    p = FPrint.Print.deserialize(bytes(blob))
    try:
        dev.delete_print_sync(p)
        print("  deleted OK")
    except GLib.Error as e:
        print("  delete failed:", e.message)
try:
    dev.clear_storage_sync()
except GLib.Error as e:
    print("clear_storage refused as intended:", e.message)
dev.close_sync()
