"""Issue forms are YAML that GitHub validates only after push; catch mistakes here."""
import pathlib
import unittest

import yaml

FORMS = pathlib.Path(__file__).resolve().parent.parent / ".github" / "ISSUE_TEMPLATE"


class IssueForms(unittest.TestCase):
    def test_forms_are_valid_and_complete(self):
        for name in ("data-correction.yml", "addon-request.yml"):
            form = yaml.safe_load((FORMS / name).read_text())
            for key in ("name", "description", "body"):
                self.assertIn(key, form, f"{name} missing {key}")
            ids = [b["id"] for b in form["body"] if "id" in b]
            self.assertEqual(len(ids), len(set(ids)), f"{name} has duplicate ids")

    def test_correction_form_separates_claim_categories(self):
        form = yaml.safe_load((FORMS / "data-correction.yml").read_text())
        cat = next(b for b in form["body"] if b.get("id") == "category")
        opts = " ".join(cat["attributes"]["options"]).lower()
        for word in ("declared", "tested", "kubeversion", "chart", "lifecycle"):
            self.assertIn(word, opts)


if __name__ == "__main__":
    unittest.main()
