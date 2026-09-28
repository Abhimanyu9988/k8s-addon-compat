"""Build evidence-backed compatibility data for every add-on in addons.yaml.

    python -m kcompat.collect                      # live sources -> data/
    python -m kcompat.collect --fixtures DIR --out OUT   # offline test run

Output files contain no fetch timestamps, so a file only changes when the
evidence changes. That keeps the daily PR empty on quiet days.
"""
from __future__ import annotations

import argparse
import pathlib
import re
import sys
from typing import Optional

import yaml

from . import docs_parsers as dp
from .sources import FixtureSources, Sources
from .versions import ConstraintError, ConstraintSet, Minor, minor_str

ROOT = pathlib.Path(__file__).resolve().parent.parent
VIEW_WIDTH = 5  # Kubernetes minors shown in the version view


def _semver_key(v: str) -> tuple[int, ...]:
    return tuple(int(x) for x in re.findall(r"\d+", v)[:3])


# ---------------------------------------------------------------------------
# Helm index
# ---------------------------------------------------------------------------

def charts_by_app_version(index: dict, chart: str) -> dict[str, dict]:
    """Map normalised appVersion -> newest chart entry carrying it."""
    out: dict[str, dict] = {}
    for e in index.get("entries", {}).get(chart, []):
        app = str(e.get("appVersion", "")).lstrip("v")
        if not app or "-" in str(e.get("version", "")):
            continue  # skip pre-release charts
        cur = out.get(app)
        if cur is None or _semver_key(str(e["version"])) > _semver_key(str(cur["version"])):
            out[app] = e
    return out


def chart_versions_for_app(index: dict, chart: str, app: str) -> list[str]:
    return sorted(
        {str(e["version"]) for e in index.get("entries", {}).get(chart, [])
         if str(e.get("appVersion", "")).lstrip("v") == app},
        key=_semver_key,
    )


# ---------------------------------------------------------------------------
# Discrepancies
# ---------------------------------------------------------------------------

def check_release(claims: list[dp.DocClaim], constraint: Optional[ConstraintSet],
                  constraint_raw: Optional[str], chart_version: Optional[str],
                  view_top: Minor) -> tuple[list[dict], list[dict]]:
    """Return (discrepancies, notes).

    Discrepancy (hard): docs claim a Kubernetes version, but the chart's
    kubeVersion constraint blocks installing on it.
    Note (soft): the chart allows installing below the documented minimum.
    """
    hard, soft = [], []
    if constraint is None:
        return hard, soft
    lowest_claimed: Optional[Minor] = None
    for c in claims:
        if c.claim_type == dp.NOT_STATED:
            continue
        minors = list(c.k8s.minors)
        if c.k8s.open_from:
            start = c.k8s.open_from
            minors += [(start[0], n) for n in range(start[1], view_top[1] + 1)] if start[0] == view_top[0] else []
        blocked = sorted({m for m in minors if not constraint.allows_minor(m)})
        if blocked:
            hard.append({
                "kind": "chart-blocks-claimed-version",
                "claim_type": c.claim_type,
                "kubernetes": [minor_str(m) for m in blocked],
                "detail": (f"Docs say {c.claim_type} for {', '.join(minor_str(m) for m in blocked)}, "
                           f"but chart {chart_version} kubeVersion '{constraint_raw}' blocks install there."),
            })
        low = c.k8s.lowest()
        if low and (lowest_claimed is None or low < lowest_claimed):
            lowest_claimed = low
    if lowest_claimed and lowest_claimed[1] > 0:
        below = (lowest_claimed[0], lowest_claimed[1] - 1)
        if constraint.allows_minor(below):
            soft.append({
                "kind": "chart-allows-below-documented-minimum",
                "constraint": constraint_raw,
                "documented_minimum": minor_str(lowest_claimed),
                "allows": minor_str(below),
                "detail": (f"Chart {chart_version} kubeVersion '{constraint_raw}' allows install on "
                           f"{minor_str(below)}, below the documented minimum {minor_str(lowest_claimed)}."),
            })
    return hard, soft


# ---------------------------------------------------------------------------
# Per add-on
# ---------------------------------------------------------------------------

def build_addon(addon: dict, src, keep: int) -> tuple[dict, list[str]]:
    warnings: list[str] = []
    docs_md = src.text(addon["docs"]["raw"])
    rows = dp.PARSERS[addon["docs"]["parser"]](docs_md)
    if not rows:
        warnings.append(f"{addon['id']}: docs parser returned no rows; format may have changed")

    status = {"state": "active"}
    if addon.get("status_from_readme"):
        readme = docs_md if addon["status_from_readme"] == addon["docs"]["raw"] else src.text(addon["status_from_readme"])
        note = dp.detect_retirement(readme)
        if note:
            status = {"state": "retired", "note": note, "source": addon.get("status_url", addon["status_from_readme"])}

    pattern = re.compile(addon["tag_pattern"])
    releases = []
    for r in src.releases(addon["github"]):
        if r.get("draft") or r.get("prerelease"):
            continue
        m = pattern.match(r.get("tag_name", ""))
        if m:
            releases.append((m.group(1), r))
    releases.sort(key=lambda x: _semver_key(x[0]), reverse=True)
    releases = releases[:keep]
    if not releases:
        warnings.append(f"{addon['id']}: no releases matched tag_pattern {addon['tag_pattern']}")

    index = src.helm_index(addon["helm"]["index"])
    by_app = charts_by_app_version(index, addon["helm"]["chart"])

    out_releases = []
    for version, rel in releases:
        row = dp.match_row(rows, version)
        claims = row.claims if row else [dp.DocClaim(dp.NOT_STATED, dp.parse_k8s_expression(""))]
        chart = by_app.get(version)
        constraint = None
        constraint_raw = str(chart.get("kubeVersion")).strip() if chart and chart.get("kubeVersion") else None
        if constraint_raw:
            try:
                constraint = ConstraintSet(constraint_raw)
            except ConstraintError:
                warnings.append(f"{addon['id']} {version}: could not parse kubeVersion {constraint_raw!r}")

        rec = {
            "version": version,
            "tag": rel["tag_name"],
            "published": (rel.get("published_at") or "")[:10],
            "release_notes": rel.get("html_url"),
            "chart": None,
            "kubernetes": {
                "install_constraint": {
                    "value": constraint_raw,
                    "parsed": constraint is not None,
                    "source": addon["helm"]["index"],
                } if chart else None,
                "claims": [
                    {
                        "claim_type": c.claim_type,
                        "expression": c.k8s.expression or None,
                        "versions": [minor_str(m) for m in c.k8s.minors],
                        "open_from": minor_str(c.k8s.open_from) if c.k8s.open_from else None,
                        "source": addon["docs"]["url"],
                    }
                    for c in claims
                ],
                "docs_row": row.release_key if row else None,
                "docs_extra": row.extra if row and row.extra else None,
            },
            "discrepancies": [],
            "notes": [],
        }
        if chart:
            rec["chart"] = {"name": addon["helm"]["chart"], "version": str(chart["version"]),
                            "app_version": str(chart.get("appVersion"))}
        else:
            rec["notes"].append({"kind": "no-chart-for-app-version",
                                 "detail": f"No chart in {addon['helm']['index']} has appVersion {version}."})

        # ingress-nginx lists the chart version in its docs; cross-check it.
        docs_chart = row.extra.get("docs_chart_version") if row else None
        if docs_chart:
            known = chart_versions_for_app(index, addon["helm"]["chart"], version)
            if known and docs_chart not in known:
                rec["notes"].append({
                    "kind": "docs-chart-version-mismatch",
                    "detail": f"Docs pair {version} with chart {docs_chart}; the chart index pairs it with {', '.join(known)}.",
                })

        rec["_claims"] = claims  # internal, removed before writing
        rec["_constraint"] = constraint
        out_releases.append(rec)

    return {
        "id": addon["id"],
        "name": addon["name"],
        "github": f"https://github.com/{addon['github']}",
        "status": status,
        "docs": addon["docs"]["url"],
        "upgrade_notes": addon.get("upgrade_notes"),
        "releases": out_releases,
    }, warnings


def finalise(addons: list[dict]) -> Minor:
    """Pick the Kubernetes view window, run discrepancy checks, strip internals."""
    top: Optional[Minor] = None
    for a in addons:
        for r in a["releases"]:
            for c in r["_claims"]:
                h = c.k8s.highest() if c.claim_type != dp.NOT_STATED else None
                if h and (top is None or h > top):
                    top = h
    top = top or (1, 30)
    for a in addons:
        for r in a["releases"]:
            constraint = r.pop("_constraint")
            claims = r.pop("_claims")
            ic = r["kubernetes"]["install_constraint"]
            if ic and constraint:
                ic["allows"] = {minor_str((top[0], top[1] - i)): constraint.allows_minor((top[0], top[1] - i))
                                for i in range(VIEW_WIDTH)}
            hard, soft = check_release(claims, constraint, ic and ic["value"],
                                       r["chart"] and r["chart"]["version"], top)
            r["discrepancies"] += hard
            r["notes"] += soft
    return top


def kubernetes_view(addons: list[dict], top: Minor) -> dict:
    """For each Kubernetes minor: the newest tracked release of each add-on
    whose docs claim that version. Evidence only, no advice."""
    minors = [(top[0], top[1] - i) for i in range(VIEW_WIDTH)]
    view = {"kubernetes_versions": [minor_str(m) for m in minors], "addons": []}
    for a in addons:
        entry = {"id": a["id"], "name": a["name"], "status": a["status"]["state"], "by_kubernetes": {}}
        for m in minors:
            ms = minor_str(m)
            hit = None
            for r in a["releases"]:  # newest first
                types = []
                for c in r["kubernetes"]["claims"]:
                    if c["claim_type"] == dp.NOT_STATED:
                        continue
                    covered = ms in c["versions"] or (
                        c["open_from"] and _semver_key(ms) >= _semver_key(c["open_from"]))
                    if covered:
                        types.append(c["claim_type"])
                if types:
                    ic = r["kubernetes"]["install_constraint"]
                    hit = {
                        "version": r["version"],
                        "claim_types": sorted(set(types)),
                        "source": r["kubernetes"]["claims"][0]["source"],
                        "chart_allows_install": (ic or {}).get("allows", {}).get(ms),
                        "discrepancy": any(ms in d.get("kubernetes", []) for d in r["discrepancies"]),
                    }
                    break
            entry["by_kubernetes"][ms] = hit or {"claim_types": [dp.NOT_STATED]}
        view["addons"].append(entry)
    return view


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", default=str(ROOT / "addons.yaml"))
    ap.add_argument("--out", default=str(ROOT / "data"))
    ap.add_argument("--fixtures", help="offline mode: read sources from this folder")
    ap.add_argument("--strict", action="store_true",
                    help="exit non-zero on any warning (used by the daily job so format changes alert you)")
    args = ap.parse_args(argv)

    cfg = yaml.safe_load(pathlib.Path(args.config).read_text())
    if args.fixtures:
        by_url = {}
        for a in cfg["addons"]:
            for k in (a["github"], a["helm"]["index"], a["docs"]["raw"], a.get("status_from_readme")):
                if k:
                    by_url[k] = a["id"]
        src = FixtureSources(args.fixtures, by_url)
    else:
        src = Sources()

    built, warnings = [], []
    for addon in cfg["addons"]:
        try:
            data, w = build_addon(addon, src, cfg.get("releases_per_addon", 6))
            built.append(data)
            warnings += w
        except Exception as e:  # one broken source must not stop the others
            warnings.append(f"{addon['id']}: FAILED ({type(e).__name__}: {e})")

    top = finalise(built)
    out = pathlib.Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    for a in built:
        (out / f"{a['id']}.yaml").write_text(yaml.safe_dump(a, sort_keys=False, allow_unicode=True))
    (out / "kubernetes-view.yaml").write_text(
        yaml.safe_dump(kubernetes_view(built, top), sort_keys=False, allow_unicode=True))

    n_hard = sum(len(r["discrepancies"]) for a in built for r in a["releases"])
    print(f"Wrote {len(built)} add-ons to {out} (Kubernetes view up to {minor_str(top)}); "
          f"{n_hard} discrepancies.")
    for w in warnings:
        print(f"WARNING: {w}", file=sys.stderr)
    if args.strict and warnings:
        print(f"Strict mode: {len(warnings)} warning(s), failing the run.", file=sys.stderr)
        return 1
    return 1 if any("FAILED" in w for w in warnings) else 0


if __name__ == "__main__":
    sys.exit(main())
