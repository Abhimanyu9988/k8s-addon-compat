"""Tests run against real copies of each project's docs (tests/fixtures).
When a project changes its doc format, these tests show exactly what broke."""
import pathlib
import unittest

from kcompat import docs_parsers as dp

FIX = pathlib.Path(__file__).parent / "fixtures"


def load(name):
    return (FIX / f"{name}.md").read_text()


class CertManager(unittest.TestCase):
    rows = dp.parse_cert_manager(load("cert-manager"))

    def test_current_release_has_both_claim_types(self):
        r = dp.match_row(self.rows, "v1.21.3")
        self.assertIsNotNone(r)
        types = [c.claim_type for c in r.claims]
        self.assertEqual(types, [dp.DECLARED, dp.TESTED])
        self.assertTrue(r.claims[0].k8s.covers((1, 36)))
        self.assertFalse(r.claims[0].k8s.covers((1, 32)))

    def test_eol_release(self):
        r = dp.match_row(self.rows, "1.19.0")
        self.assertEqual(r.extra["status"], "eol")
        self.assertEqual(r.claims[0].k8s.lowest(), (1, 31))

    def test_lts_suffix(self):
        self.assertIsNotNone(dp.match_row(self.rows, "1.12.5"))

    def test_upcoming_tbd_not_stated(self):
        r = dp.match_row(self.rows, "1.22.0")
        self.assertEqual(r.extra["status"], "upcoming")
        self.assertTrue(all(c.claim_type == dp.NOT_STATED for c in r.claims))


class OtelOperator(unittest.TestCase):
    rows = dp.parse_otel_operator(load("opentelemetry-operator"))

    def test_exact_version(self):
        r = dp.match_row(self.rows, "v0.159.0")
        self.assertEqual(r.claims[0].claim_type, dp.DECLARED)
        self.assertEqual(r.claims[0].k8s.highest(), (1, 36))

    def test_no_line_fallback_for_exact_tables(self):
        self.assertIsNone(dp.match_row(self.rows, "0.159.1"))


class IngressNginx(unittest.TestCase):
    md = load("ingress-nginx")
    rows = dp.parse_ingress_nginx(md)

    def test_tested_with_chart_version(self):
        r = dp.match_row(self.rows, "controller-v1.15.1".split("-v")[1])
        self.assertEqual(r.claims[0].claim_type, dp.TESTED)
        self.assertTrue(r.claims[0].k8s.covers((1, 35)))
        self.assertEqual(r.extra["docs_chart_version"], "4.15.1")

    def test_retirement_detected(self):
        self.assertIn("Retirement", dp.detect_retirement(self.md))


class MetricsServer(unittest.TestCase):
    rows = dp.parse_metrics_server(load("metrics-server"))

    def test_open_ended_line(self):
        r = dp.match_row(self.rows, "v0.8.1")
        self.assertEqual(r.claims[0].k8s.open_from, (1, 31))
        self.assertTrue(r.claims[0].k8s.covers((1, 36)))

    def test_closed_old_range(self):
        r = dp.match_row(self.rows, "0.3.7")
        self.assertFalse(r.claims[0].k8s.covers((1, 22)))

    def test_no_retirement(self):
        self.assertIsNone(dp.detect_retirement(load("metrics-server")))


if __name__ == "__main__":
    unittest.main()
