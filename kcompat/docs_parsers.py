"""Parsers for each project's own compatibility documentation.

Each parser returns DocRow objects. A row says: "for this release (or release
line), the project's docs make these claims about Kubernetes versions".

Claim types (the only three used anywhere in this project):
  declared-supported  the project states it supports these versions
  tested              the project states it tested these versions
  not-stated          nothing usable was stated (never read as "incompatible")
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Callable, Optional

from .versions import K8sClaim, parse_k8s_expression

DECLARED = "declared-supported"
TESTED = "tested"
NOT_STATED = "not-stated"
CLAIM_TYPES = (DECLARED, TESTED, NOT_STATED)


@dataclass
class DocClaim:
    claim_type: str
    k8s: K8sClaim


@dataclass
class DocRow:
    release_key: str            # as normalised from the doc: "1.21", "0.9", "0.159.0"
    match: str                  # "exact" (full version) or "line" (major.minor line)
    claims: list[DocClaim]
    extra: dict = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Markdown tables
# ---------------------------------------------------------------------------

def _clean_cell(c: str) -> str:
    c = re.sub(r"\[([^\]]*)\]\[[^\]]*\]", r"\1", c)      # [1.21][]  -> 1.21
    c = re.sub(r"\[([^\]]*)\]\([^)]*\)", r"\1", c)       # [x](url)  -> x
    c = c.replace("**", "").replace("`", "")
    return c.strip()


def _split_row(line: str) -> list[str]:
    line = line.strip()
    if line.startswith("|"):
        line = line[1:]
    if line.endswith("|"):
        line = line[:-1]
    return [_clean_cell(c) for c in line.split("|")]


def _is_separator(line: str) -> bool:
    return bool(re.fullmatch(r"\s*\|?\s*:?-{3,}:?\s*(\|\s*:?-{3,}:?\s*)*\|?\s*", line))


def find_tables(markdown: str, header_must_contain: str) -> list[tuple[list[str], list[list[str]], str]]:
    """Return (header, rows, preceding_heading) for every table whose header
    contains `header_must_contain` (case-insensitive). Handles tables with or
    without outer pipes."""
    lines = markdown.splitlines()
    out = []
    heading = ""
    i = 0
    while i < len(lines):
        if lines[i].lstrip().startswith("#"):
            heading = lines[i].lstrip("# ").strip()
        if (
            i + 1 < len(lines)
            and "|" in lines[i]
            and _is_separator(lines[i + 1])
            and header_must_contain.lower() in lines[i].lower()
        ):
            header = _split_row(lines[i])
            rows = []
            j = i + 2
            while j < len(lines) and "|" in lines[j] and lines[j].strip():
                rows.append(_split_row(lines[j]))
                j += 1
            out.append((header, rows, heading))
            i = j
            continue
        i += 1
    return out


def _col(header: list[str], *needles: str) -> Optional[int]:
    for idx, h in enumerate(header):
        hl = h.lower()
        if all(n.lower() in hl for n in needles):
            return idx
    return None


def _claim(claim_type: str, text: str) -> DocClaim:
    k = parse_k8s_expression(text)
    return DocClaim(claim_type if k.stated else NOT_STATED, k)


def _norm_version(v: str) -> str:
    return v.strip().lstrip("v")


# ---------------------------------------------------------------------------
# Project parsers
# ---------------------------------------------------------------------------

def parse_cert_manager(md: str) -> list[DocRow]:
    """cert-manager.io/docs/releases: per release line, two claim columns
    (supported and tested) for current releases; one column for EOL releases."""
    rows: list[DocRow] = []
    for header, body, heading in find_tables(md, "Release"):
        sup = _col(header, "supported kubernetes")
        tst = _col(header, "tested kubernetes")
        compat = _col(header, "compatible kubernetes")
        if sup is None and compat is None:
            continue
        upcoming = "upcoming" in heading.lower()
        eol_col = _col(header, "end of life") if _col(header, "end of life") is not None else _col(header, "eol")
        for r in body:
            key = re.sub(r"\s*LTS\s*", "", r[0]).strip()
            if not re.fullmatch(r"\d+\.\d+", key):
                continue
            claims = []
            if sup is not None:
                claims.append(_claim(DECLARED, r[sup]))
            if tst is not None:
                claims.append(_claim(TESTED, r[tst]))
            if compat is not None:
                claims.append(_claim(DECLARED, r[compat]))
            extra = {"status": "upcoming" if upcoming else ("eol" if compat is not None else "supported")}
            if eol_col is not None:
                extra["end_of_life"] = r[eol_col]
            rows.append(DocRow(key, "line", claims, extra))
    return rows


def parse_otel_operator(md: str) -> list[DocRow]:
    """docs/getting-started/compatibility.md: one row per operator version."""
    rows: list[DocRow] = []
    for header, body, _ in find_tables(md, "OpenTelemetry Operator"):
        k = _col(header, "kubernetes")
        if k is None:
            continue
        for r in body:
            if not re.fullmatch(r"v?\d+\.\d+\.\d+", r[0]):
                continue
            rows.append(DocRow(_norm_version(r[0]), "exact", [_claim(DECLARED, r[k])]))
    return rows


def parse_ingress_nginx(md: str) -> list[DocRow]:
    """README 'Supported Versions table': E2E-tested Kubernetes versions per
    controller version, plus the matching Helm chart version."""
    rows: list[DocRow] = []
    for header, body, _ in find_tables(md, "Ingress-NGINX version"):
        v = _col(header, "ingress-nginx version")
        k = _col(header, "k8s")
        chart = _col(header, "helm chart")
        if v is None or k is None:
            continue
        for r in body:
            if not re.fullmatch(r"v?\d+\.\d+\.\d+", r[v]):
                continue
            extra = {"docs_chart_version": r[chart]} if chart is not None and r[chart] else {}
            rows.append(DocRow(_norm_version(r[v]), "exact", [_claim(TESTED, r[k])], extra))
    return rows


def parse_metrics_server(md: str) -> list[DocRow]:
    """README 'Compatibility Matrix': per minor line, often open-ended ('1.34+')."""
    rows: list[DocRow] = []
    for header, body, _ in find_tables(md, "Supported Kubernetes version"):
        k = _col(header, "supported kubernetes")
        if k is None:
            continue
        for r in body:
            m = re.fullmatch(r"v?(\d+\.\d+)\.x", r[0])
            if not m:
                continue
            rows.append(DocRow(m.group(1), "line", [_claim(DECLARED, r[k])]))
    return rows


PARSERS: dict[str, Callable[[str], list[DocRow]]] = {
    "cert-manager": parse_cert_manager,
    "otel-operator": parse_otel_operator,
    "ingress-nginx": parse_ingress_nginx,
    "metrics-server": parse_metrics_server,
}


def detect_retirement(md: str) -> Optional[str]:
    """Return the first retirement/deprecation line near the top of a README."""
    head = "\n".join(md.splitlines()[:30])
    m = re.search(r"^#+\s*(.*\b(retire|retirement|deprecated|archived)\b.*)$", head, re.I | re.M)
    return m.group(1).strip() if m else None


def match_row(rows: list[DocRow], version: str) -> Optional[DocRow]:
    """Find the doc row for an app version: exact match first, then its line."""
    v = _norm_version(version)
    for r in rows:
        if r.match == "exact" and r.release_key == v:
            return r
    line = ".".join(v.split(".")[:2])
    for r in rows:
        if r.match == "line" and r.release_key == line:
            return r
    return None
