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
        # the "allows below minimum" note appears once per add-on, not on every release
        self.assertEqual(page.count("below the documented minimum"), 3)


if __name__ == "__main__":
    unittest.main()
