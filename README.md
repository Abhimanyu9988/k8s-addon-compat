# Kubernetes Add-on Compatibility

**Can I upgrade my Kubernetes cluster without breaking the add-ons I run?**

This project answers that question for common add-ons with evidence, not opinion.
For every tracked release it records what the project's own documentation claims
about Kubernetes versions, what the Helm chart's `kubeVersion` allows, and where
the two disagree. Every claim links to its source.

> Automation discovers changes; humans approve compatibility claims.

## Tracked add-ons (v1)

| Add-on | Compatibility source | Claim type |
|---|---|---|
| cert-manager | [cert-manager.io/docs/releases](https://cert-manager.io/docs/releases/) | declared-supported and tested |
| OpenTelemetry Operator | [compatibility.md](https://github.com/open-telemetry/opentelemetry-operator/blob/main/docs/getting-started/compatibility.md) | declared-supported |
| ingress-nginx (retired) | [Supported Versions table](https://github.com/kubernetes/ingress-nginx#supported-versions-table) | tested |
| metrics-server | [Compatibility Matrix](https://github.com/kubernetes-sigs/metrics-server#compatibility-matrix) | declared-supported |

Chart metadata comes from each project's Helm repository `index.yaml`; releases
come from GitHub.

## How claims are recorded

Only three claim types exist:

| Claim type | Meaning |
|---|---|
| `tested` | The project says it tested this Kubernetes version. |
| `declared-supported` | The project says it supports this version. |
| `not-stated` | Nothing usable was stated. **Never read as "incompatible".** |

A chart's `kubeVersion` is kept separate as `install_constraint`. It says whether
Helm will install, not whether the maintainers support that version. An
open-ended constraint like `>=1.30.0-0` is not a support claim for 1.36.

Doc expressions are stored verbatim next to the parsed versions, so a reviewer
can always compare the two.

## Findings

- **Discrepancy:** the docs claim a Kubernetes version (tested or declared), but
  the chart's `kubeVersion` blocks installing on it. This is usually an upstream
  bug worth reporting.
- **Note:** the chart allows installing below the documented minimum, or the
  docs pair a release with a different chart version than the chart index does.
  Common and informational.

## Data flow

```
Scheduled GitHub Action (daily)
  → fetch releases, Helm index.yaml, compatibility docs
  → parse and normalise into data/*.yaml
  → compare with the repository
  → open a PR if the evidence changed
  → a human reviews sources and diff, then merges
  → GitHub Pages rebuilds
```

Data files contain no fetch timestamps, so quiet days produce no PR.

## Run it locally

```
python3 -m venv .venv && . .venv/bin/activate
pip install -r requirements.txt
python -m unittest discover -s tests -t .
python -m kcompat.collect          # writes data/
python site/build_site.py          # writes site/dist/index.html
open site/dist/index.html
```

A GitHub token raises API limits: set `GITHUB_TOKEN`, or log in with `gh auth login`.

## Adding an add-on

1. Add an entry to `addons.yaml` (GitHub repo, tag pattern, Helm index, docs source).
2. Add a parser in `kcompat/docs_parsers.py` for that project's compatibility table.
3. Save a copy of the real doc in `tests/fixtures/` and add a test. When upstream
   changes its format, that test shows exactly what broke.

## Out of scope for v1

Deprecated-API detection (see [Pluto](https://github.com/FairwindsOps/pluto)),
repository health metrics (see [LFX Insights](https://insights.linuxfoundation.org/)),
and upgrade recommendations. Nothing here is AI-generated.

## Related tools

- [Nova](https://github.com/FairwindsOps/nova) finds outdated Helm charts in a live cluster.
- [Pluto](https://github.com/FairwindsOps/pluto) finds deprecated Kubernetes APIs in manifests and releases.

This project differs by publishing a public, source-linked compatibility matrix
across add-ons, and by flagging where a project's chart and docs disagree.

## Repository setup (once)

- Settings → Pages → Source: **GitHub Actions**.
- Settings → Actions → General → Workflow permissions: allow **Read and write**, and
  tick **Allow GitHub Actions to create and approve pull requests** (needed for the daily PR).
