"""Static check of the C driver: its btl_allowed[] table must stay a subset of the Python
allowlist, and no blocked command may appear anywhere as a BTL_CMD_* definition."""
import os
import re
import sys
import unittest

ROOT = os.path.join(os.path.dirname(__file__), "..")
sys.path.insert(0, ROOT)
from safety import ALLOWED, BLOCKED  # noqa: E402


def load(name):
    with open(os.path.join(ROOT, "driver", name)) as f:
        return f.read()


class CAllowlist(unittest.TestCase):
    def setUp(self):
        self.h = load("betterlife.h")
        self.c = load("betterlife.c")
        self.defs = {k: int(v, 16) for k, v in re.findall(r"#define\s+(BTL_\w+)\s+0x([0-9A-Fa-f]+)", self.h)}
        self.defs.update({k: int(v) for k, v in re.findall(r"#define\s+(BTL_\w+)\s+(\d+)\b", self.h)})

    def entries(self):
        table = re.search(r"btl_allowed\[\]\s*=\s*\{(.*?)\n\};", self.c, re.S).group(1)
        for cmd, p1, enc, ln in re.findall(r"\{\s*(\w+),\s*(\w+),\s*(TRUE|FALSE),\s*(\w+)\s*\}", table):
            val = lambda t: self.defs[t] if t in self.defs else int(t, 0)
            yield val(cmd), val(p1), enc == "TRUE", val(ln)

    def test_table_found(self):
        self.assertGreaterEqual(len(list(self.entries())), 10)

    def test_subset_of_python_allowlist(self):
        for cmd, p1, enc, ln in self.entries():
            self.assertIn((cmd, p1), ALLOWED, f"C allows {cmd:02X}/{p1} which Python does not")
            must_enc, lens = ALLOWED[(cmd, p1)]
            self.assertEqual(enc, must_enc, f"{cmd:02X}/{p1} encryption mismatch")
            self.assertIn(ln, lens, f"{cmd:02X}/{p1} length {ln} not allowed")

    def test_no_blocked_command_defined(self):
        for name, v in self.defs.items():
            if name.startswith("BTL_CMD_"):
                self.assertNotIn(v, BLOCKED, f"{name}=0x{v:02X} is a blocked command")

    def test_send_path_checks_allowlist(self):
        fn = re.search(r"\nbtl_cmd \(FpiDeviceBetterlife.*?\n\}", self.c, re.S).group(0)
        self.assertIn("btl_cmd_allowed (cmd, p1, encrypt, len)", fn)
        # only one place submits to the OUT endpoint
        self.assertEqual(self.c.count("BTL_EP_OUT"), 1)


if __name__ == "__main__":
    unittest.main()
