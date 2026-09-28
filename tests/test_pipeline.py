"""End-to-end run on SYNTHETIC fixtures (see tests/fixtures/offline/README.md)."""
import pathlib
import tempfile
import unittest

import yaml

from kcompat import collect

OFFLINE = pathlib.Path(__file__).parent / "fixtures" / "offline"


class Pipeline(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        collect.main(["--fixtures", str(OFFLINE), "--out", cls.tmp.name])
        cls.out = pathlib.Path(cls.tmp.name)

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def load(self, name):
        return yaml.safe_load((self.out / f"{name}.yaml").read_text())

    def test_known_discrepancy_is_found_and_only_that(self):
        otel = self.load("opentelemetry-operator")
        d = otel["releases"][0]["discrepancies"]
        self.assertEqual(len(d), 1)
        self.assertEqual(d[0]["kubernetes"], ["1.36"])
        total = sum(len(r["discrepancies"]) for n in
                    ("cert-manager", "opentelemetry-operator", "ingress-nginx", "metrics-server")
                    for r in self.load(n)["releases"])
        self.assertEqual(total, 1)

    def test_prereleases_and_chart_tags_excluded(self):
        versions = [r["version"] for r in self.load("ingress-nginx")["releases"]]
        self.assertEqual(versions, ["1.15.1", "1.15.0", "1.14.5"])

    def test_retired_status(self):
        self.assertEqual(self.load("ingress-nginx")["status"]["state"], "retired")
        self.assertEqual(self.load("metrics-server")["status"]["state"], "active")

    def test_soft_note_when_chart_allows_below_docs_minimum(self):
        notes = self.load("cert-manager")["releases"][0]["notes"]
        self.assertTrue(any(n["kind"] == "chart-allows-below-documented-minimum" for n in notes))

    def test_open_ended_claim_reaches_view_top(self):
        view = yaml.safe_load((self.out / "kubernetes-view.yaml").read_text())
        ms = next(a for a in view["addons"] if a["id"] == "metrics-server")
        self.assertEqual(ms["by_kubernetes"]["1.36"]["version"], "0.8.1")

    def test_no_timestamps_in_output(self):
        text = (self.out / "cert-manager.yaml").read_text()
        self.assertNotIn("fetched", text)
        self.assertNotIn("generated", text)


if __name__ == "__main__":
    unittest.main()
