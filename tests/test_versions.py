import unittest

from kcompat.versions import ConstraintError, ConstraintSet, parse_k8s_expression


class DocExpressions(unittest.TestCase):
    def test_arrow_range_with_openshift(self):
        c = parse_k8s_expression("1.33 → 1.36 / 4.20 → 4.22")
        self.assertEqual(c.minors, [(1, 33), (1, 34), (1, 35), (1, 36)])
        self.assertTrue(c.covers((1, 36)))
        self.assertFalse(c.covers((1, 37)))

    def test_to_range(self):
        c = parse_k8s_expression("v1.25 to v1.36")
        self.assertEqual(c.lowest(), (1, 25))
        self.assertEqual(c.highest(), (1, 36))

    def test_dash_range(self):
        self.assertEqual(parse_k8s_expression("1.8-1.21").highest(), (1, 21))

    def test_list(self):
        c = parse_k8s_expression("1.35, 1.34, 1.33, 1.32, 1.31")
        self.assertEqual(c.lowest(), (1, 31))
        self.assertFalse(c.covers((1, 30)))

    def test_open_ended_is_not_capped(self):
        c = parse_k8s_expression("1.34+")
        self.assertTrue(c.covers((1, 40)))
        self.assertFalse(c.covers((1, 33)))

    def test_footnote_marker(self):
        self.assertEqual(parse_k8s_expression("*1.8+").open_from, (1, 8))

    def test_tbd_is_not_stated(self):
        self.assertFalse(parse_k8s_expression("TBD").stated)
        self.assertFalse(parse_k8s_expression("TBD").covers((1, 35)))

    def test_unrecognised_is_not_guessed(self):
        c = parse_k8s_expression("see upstream docs")
        self.assertFalse(c.stated)
        self.assertEqual(c.expression, "see upstream docs")


class HelmConstraints(unittest.TestCase):
    def test_open_upper_bound(self):
        c = ConstraintSet(">=1.30.0-0")
        self.assertTrue(c.allows_minor((1, 35)))
        self.assertFalse(c.allows_minor((1, 29)))

    def test_and_range(self):
        c = ConstraintSet(">= 1.22.0-0 < 1.36.0-0")
        self.assertTrue(c.allows_minor((1, 35)))
        self.assertFalse(c.allows_minor((1, 36)))

    def test_comma_and(self):
        self.assertFalse(ConstraintSet(">=1.25.0, <1.30.0").allows_minor((1, 30)))

    def test_or_and_caret_tilde(self):
        c = ConstraintSet("~1.25.0 || ^2.0.0")
        self.assertTrue(c.allows_minor((1, 25)))
        self.assertFalse(c.allows_minor((1, 26)))

    def test_bad_input_raises(self):
        with self.assertRaises(ConstraintError):
            ConstraintSet("1.x")
        with self.assertRaises(ConstraintError):
            ConstraintSet("banana")


if __name__ == "__main__":
    unittest.main()
