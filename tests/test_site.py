import pathlib
import sys
import tempfile
import unittest

from kcompat import collect

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent / "site"))
import build_site  # noqa: E402

OFFLINE = pathlib.Path(__file__).parent / "fixtures" / "offline"


class Site(unittest.TestCase):
    def test_renders_view_findings_and_retired_status(self):
        with tempfile.TemporaryDirectory() as d:
            collect.main(["--fixtures", str(OFFLINE), "--out", d])
            page = build_site.render(pathlib.Path(d))
        self.assertIn("By Kubernetes version", page)
        self.assertIn("chart blocks", page)
        self.assertIn("Retired:", page)
        self.assertIn("(OpenShift 4.20 → 4.22)", page)
        self.assertIn("1 hard discrepancy", page)
        # notes are grouped by identical inputs, and every affected release is listed
        self.assertIn("below the documented minimum 1.33: 1.21.3, 1.21.2", page)
        self.assertIn("below the documented minimum 1.31: 1.15.1, 1.15.0", page)


if __name__ == "__main__":
    unittest.main()
