"""Render data/*.yaml into a single static page: site/dist/index.html.

    python site/build_site.py [--data DIR] [--out DIR]
"""
from __future__ import annotations

import argparse
import datetime as dt
import html
import pathlib

import yaml

ROOT = pathlib.Path(__file__).resolve().parent.parent
LABEL = {"tested": "tested", "declared-supported": "declared", "not-stated": "not stated"}


def e(x) -> str:
    return html.escape("" if x is None else str(x))


def badge(kind: str) -> str:
    return f'<span class="b b-{e(kind)}">{e(LABEL.get(kind, kind))}</span>'


def view_table(view: dict) -> str:
    ks = view["kubernetes_versions"]
    head = "".join(f"<th>{e(k)}</th>" for k in ks)
    rows = []
    for a in view["addons"]:
        name = e(a["name"]) + (' <span class="b b-retired">retired</span>' if a["status"] == "retired" else "")
        cells = []
        for k in ks:
            c = a["by_kubernetes"][k]
            if "version" not in c:
                cells.append(f'<td class="none">{badge("not-stated")}</td>')
                continue
            flags = ""
            if c.get("discrepancy"):
                flags += ' <span class="warn" title="Chart constraint blocks a version the docs claim">⚠ chart blocks</span>'
            elif c.get("chart_allows_install") is False:
                flags += ' <span class="warn">chart blocks</span>'
            cells.append(
                f'<td><a href="{e(c["source"])}">{e(c["version"])}</a><br>'
                + " ".join(badge(t) for t in c["claim_types"]) + flags + "</td>")
        rows.append(f'<tr><th scope="row"><a href="#{e(a["id"])}">{name}</a></th>{"".join(cells)}</tr>')
    return (f'<div class="scroll"><table class="view"><thead><tr><th>Add-on</th>{head}</tr></thead>'
            f'<tbody>{"".join(rows)}</tbody></table></div>')


def claims_cell(r: dict) -> str:
    out = []
    for c in r["kubernetes"]["claims"]:
        if c["claim_type"] == "not-stated":
            out.append(badge("not-stated"))
        else:
            k8s, _, openshift = (c["expression"] or "").partition("/")
            extra = f' <span class="muted">(OpenShift {e(openshift.strip())})</span>' if openshift.strip() else ""
            out.append(f'{badge(c["claim_type"])} <a href="{e(c["source"])}" title="{e(c["expression"])}">'
                       f'{e(k8s.strip())}</a>{extra}')
    return "<br>".join(out)


def addon_section(a: dict) -> str:
    st = a["status"]
    status = ""
    if st["state"] == "retired":
        status = (f'<p class="retired-note">Retired: <a href="{e(st["source"])}">{e(st["note"])}</a>. '
                  "Listed because many clusters still run it.</p>")
    links = [f'<a href="{e(a["github"])}">GitHub</a>', f'<a href="{e(a["docs"])}">compatibility docs</a>']
    if a.get("upgrade_notes"):
        links.append(f'<a href="{e(a["upgrade_notes"])}">upgrade notes</a>')
    rows = []
    for i, r in enumerate(a["releases"]):
        ic = r["kubernetes"]["install_constraint"]
        # "Chart allows install below the documented minimum" is true for most charts;
        # show it once (newest release) instead of on every row. The data keeps all of them.
        notes = [n for n in r["notes"] if i == 0 or n["kind"] != "chart-allows-below-documented-minimum"]
        chart = r["chart"]["version"] if r["chart"] else "—"
        constraint = f'<code>{e(ic["value"])}</code>' if ic and ic["value"] else '<span class="muted">none set</span>'
        issues = "".join(f'<div class="disc">⚠ {e(d["detail"])}</div>' for d in r["discrepancies"])
        issues += "".join(f'<div class="note">{e(n["detail"])}</div>' for n in notes)
        rows.append(
            f'<tr><td><a href="{e(r["release_notes"])}">{e(r["version"])}</a></td><td>{e(r["published"])}</td>'
            f'<td>{e(chart)}</td><td>{constraint}</td><td>{claims_cell(r)}</td><td>{issues}</td></tr>')
    return (f'<section id="{e(a["id"])}"><h3>{e(a["name"])}</h3>{status}<p class="links">{" · ".join(links)}</p>'
            '<div class="scroll"><table><thead><tr><th>Release</th><th>Published</th><th>Chart</th>'
            '<th>Chart <code>kubeVersion</code></th><th>Docs claims</th><th>Findings</th></tr></thead>'
            f'<tbody>{"".join(rows)}</tbody></table></div></section>')


CSS = """
:root{--bg:#fbfbfa;--fg:#1d1d1b;--muted:#6b6b66;--line:#e3e2de;--card:#fff;--link:#1f5fbf;
--tested:#1e7a4c;--tested-bg:#e3f3ea;--declared:#1f5fbf;--declared-bg:#e4ecfa;--none:#6b6b66;--none-bg:#efeeea;
--warn:#a4400f;--warn-bg:#fbe9df}
@media (prefers-color-scheme:dark){:root:not([data-theme="light"]){--bg:#161615;--fg:#ecebe7;--muted:#a2a19b;
--line:#302f2c;--card:#1e1e1c;--link:#8ab4f8;--tested:#7fd4a4;--tested-bg:#173726;--declared:#9dbcf5;
--declared-bg:#1b2a45;--none:#a2a19b;--none-bg:#2a2a27;--warn:#f0a07a;--warn-bg:#3d2417}}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--fg);
font:15px/1.5 -apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,sans-serif}
main{max-width:1100px;margin:0 auto;padding:32px 16px 64px}
h1{font-size:28px;margin:0 0 4px}h2{font-size:20px;margin:40px 0 8px}h3{font-size:17px;margin:32px 0 4px}
a{color:var(--link)}p{margin:6px 0}.muted,.lede{color:var(--muted)}
.principle{border-left:3px solid var(--line);padding-left:12px;color:var(--muted);margin:16px 0}
.scroll{overflow-x:auto;border:1px solid var(--line);border-radius:8px;background:var(--card)}
table{border-collapse:collapse;width:100%;font-size:14px}
th,td{padding:8px 10px;border-bottom:1px solid var(--line);text-align:left;vertical-align:top}
tr:last-child td,tr:last-child th{border-bottom:0}thead th{font-size:12px;text-transform:uppercase;
letter-spacing:.04em;color:var(--muted);font-weight:600}
.view td{white-space:nowrap}.view tbody th{white-space:nowrap}
.b{display:inline-block;font-size:11px;font-weight:600;padding:1px 7px;border-radius:999px;margin:2px 2px 0 0}
.b-tested{color:var(--tested);background:var(--tested-bg)}.b-declared-supported{color:var(--declared);background:var(--declared-bg)}
.b-not-stated{color:var(--none);background:var(--none-bg)}.b-retired{color:var(--warn);background:var(--warn-bg)}
.warn{color:var(--warn);font-size:12px;font-weight:600}
.disc{color:var(--warn);background:var(--warn-bg);padding:4px 8px;border-radius:6px;margin-bottom:4px;font-size:13px}
.note{color:var(--muted);font-size:13px;margin-bottom:4px}
.retired-note{color:var(--warn)}.links{font-size:14px}
code{font-size:12.5px}footer{margin-top:48px;color:var(--muted);font-size:13px}
dl.legend{display:grid;grid-template-columns:max-content 1fr;gap:6px 12px;font-size:14px;margin:12px 0}
dl.legend dd{margin:0;color:var(--muted)}
"""


def render(data_dir: pathlib.Path) -> str:
    view = yaml.safe_load((data_dir / "kubernetes-view.yaml").read_text())
    addons = [yaml.safe_load((data_dir / f"{a['id']}.yaml").read_text()) for a in view["addons"]]
    n_disc = sum(len(r["discrepancies"]) for a in addons for r in a["releases"])
    built = dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    return f"""<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Kubernetes Add-on Compatibility</title><style>{CSS}</style></head><body><main>
<h1>Kubernetes Add-on Compatibility</h1>
<p class="lede">Can I upgrade my Kubernetes cluster without breaking the add-ons I run?</p>
<p class="principle">Automation discovers changes; humans approve compatibility claims. Every claim below links to the
project's own documentation or Helm chart. Nothing is inferred from silence.</p>

<h2>By Kubernetes version</h2>
<p class="muted">For each version: the newest tracked release whose docs make a claim about it.</p>
{view_table(view)}
<dl class="legend">
<dt>{badge("tested")}</dt><dd>the project says it tested this Kubernetes version</dd>
<dt>{badge("declared-supported")}</dt><dd>the project says it supports this version</dd>
<dt>{badge("not-stated")}</dt><dd>no statement found in tracked releases. This is not a claim of incompatibility.</dd>
<dt><span class="warn">⚠ chart blocks</span></dt><dd>the Helm chart's <code>kubeVersion</code> refuses to install on a version the docs claim</dd>
</dl>

<h2>By add-on</h2>
<p class="muted">{n_disc} discrepanc{'y' if n_disc == 1 else 'ies'} between docs and Helm charts in the tracked releases.
A chart's <code>kubeVersion</code> is an install gate, not a support claim, so it's shown separately.</p>
{"".join(addon_section(a) for a in addons)}

<footer>Page built {built}. Data is refreshed daily by a GitHub Action that opens a pull request for review.</footer>
</main></body></html>"""


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", default=str(ROOT / "data"))
    ap.add_argument("--out", default=str(ROOT / "site" / "dist"))
    args = ap.parse_args()
    out = pathlib.Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    (out / "index.html").write_text(render(pathlib.Path(args.data)))
    print(f"Wrote {out / 'index.html'}")


if __name__ == "__main__":
    main()
