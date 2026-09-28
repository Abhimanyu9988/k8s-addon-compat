"""Kubernetes version handling.

Two separate jobs, deliberately kept apart:

1. `parse_k8s_expression` reads what a project's *documentation* says
   ("1.33 → 1.36", "v1.25 to v1.36", "1.35, 1.34", "1.34+", "1.8-1.21").
2. `ConstraintSet` evaluates a Helm chart's `kubeVersion` *install constraint*
   (">=1.30.0-0", ">= 1.22.0-0 < 1.36.0-0", "^1.25.0 || ^2.0.0").

A docs expression is a support claim. A chart constraint only says whether Helm
will allow the install. They are never merged.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Optional

Minor = tuple[int, int]  # (1, 35) means Kubernetes 1.35

_MINOR = re.compile(r"v?(\d+)\.(\d+)")


def minor_str(m: Minor) -> str:
    return f"{m[0]}.{m[1]}"


def parse_minor(text: str) -> Optional[Minor]:
    m = _MINOR.search(text)
    return (int(m.group(1)), int(m.group(2))) if m else None


@dataclass
class K8sClaim:
    """Kubernetes versions a document claims, in normalised form."""
    expression: str                       # exactly as written in the source
    minors: list[Minor] = field(default_factory=list)   # explicit versions
    open_from: Optional[Minor] = None     # "1.34+" -> (1, 34): everything from here up
    stated: bool = True                   # False for "TBD", "", "-"

    def covers(self, minor: Minor) -> bool:
        if not self.stated:
            return False
        if self.open_from is not None and minor >= self.open_from:
            return True
        return minor in self.minors

    def lowest(self) -> Optional[Minor]:
        cands = list(self.minors) + ([self.open_from] if self.open_from else [])
        return min(cands) if cands else None

    def highest(self) -> Optional[Minor]:
        return max(self.minors) if self.minors else self.open_from


def _expand(lo: Minor, hi: Minor) -> list[Minor]:
    if lo[0] != hi[0] or hi < lo:
        return [lo, hi]  # don't guess across majors; keep the endpoints only
    return [(lo[0], n) for n in range(lo[1], hi[1] + 1)]


def parse_k8s_expression(text: str) -> K8sClaim:
    """Parse a Kubernetes version expression from documentation.

    OpenShift parts after '/' are dropped: "1.33 → 1.36 / 4.20 → 4.22".
    Footnote markers like '*' are ignored.
    """
    raw = (text or "").strip()
    s = raw.split("/")[0]
    s = s.replace("*", "").replace("`", "").strip()
    if not s or s.upper() in {"TBD", "-", "N/A", "NA", "?"}:
        return K8sClaim(expression=raw, stated=False)

    # Open-ended: "1.34+"
    m = re.fullmatch(r"v?(\d+)\.(\d+)\s*\+", s)
    if m:
        return K8sClaim(expression=raw, open_from=(int(m.group(1)), int(m.group(2))))

    # Range: "1.33 → 1.36", "v1.25 to v1.36", "1.8-1.21", "1.8 – 1.21"
    m = re.fullmatch(r"v?(\d+)\.(\d+)\s*(?:→|->|to|–|—|-)\s*v?(\d+)\.(\d+)", s)
    if m:
        lo = (int(m.group(1)), int(m.group(2)))
        hi = (int(m.group(3)), int(m.group(4)))
        return K8sClaim(expression=raw, minors=_expand(lo, hi))

    # List: "1.35, 1.34, 1.33"
    parts = [p.strip() for p in re.split(r"[,;]", s) if p.strip()]
    minors = [parse_minor(p) for p in parts]
    if minors and all(minors) and all(re.fullmatch(r"v?\d+\.\d+", p) for p in parts):
        return K8sClaim(expression=raw, minors=sorted(set(minors)))  # type: ignore[arg-type]

    # Single version: "1.30"
    m = re.fullmatch(r"v?(\d+)\.(\d+)", s)
    if m:
        return K8sClaim(expression=raw, minors=[(int(m.group(1)), int(m.group(2)))])

    # Anything else is recorded verbatim but not interpreted.
    return K8sClaim(expression=raw, stated=False)


# ---------------------------------------------------------------------------
# Helm kubeVersion constraints (Masterminds semver subset)
# ---------------------------------------------------------------------------

Version = tuple[int, int, int]


def _parse_version(v: str) -> Version:
    v = v.strip().lstrip("v").split("-")[0].split("+")[0]
    nums = [int(x) if x.isdigit() else 0 for x in v.split(".")]
    while len(nums) < 3:
        nums.append(0)
    return nums[0], nums[1], nums[2]


class ConstraintError(ValueError):
    pass


_TERM = re.compile(r"(>=|<=|!=|>|<|=|~|\^)?\s*(v?\d+(?:\.\d+){0,2}(?:-[0-9A-Za-z.\-]+)?)")


class ConstraintSet:
    """A parsed kubeVersion constraint. OR-groups of AND-terms."""

    def __init__(self, raw: str):
        self.raw = raw.strip()
        if not self.raw:
            raise ConstraintError("empty constraint")
        self.groups: list[list[tuple[str, Version]]] = []
        for group in self.raw.split("||"):
            terms: list[tuple[str, Version]] = []
            text = group.replace(",", " ").strip()
            pos = 0
            while pos < len(text):
                if text[pos].isspace():
                    pos += 1
                    continue
                m = _TERM.match(text, pos)
                if not m:
                    raise ConstraintError(f"cannot parse {self.raw!r}")
                op, ver = m.group(1) or "=", m.group(2)
                if re.search(r"[xX*]", ver):
                    raise ConstraintError(f"wildcards not supported: {self.raw!r}")
                terms.extend(self._expand_term(op, ver))
                pos = m.end()
            if not terms:
                raise ConstraintError(f"cannot parse {self.raw!r}")
            self.groups.append(terms)

    @staticmethod
    def _expand_term(op: str, ver: str) -> list[tuple[str, Version]]:
        v = _parse_version(ver)
        if op == "~":   # ~1.2.3 -> >=1.2.3 <1.3.0
            return [(">=", v), ("<", (v[0], v[1] + 1, 0))]
        if op == "^":   # ^1.2.3 -> >=1.2.3 <2.0.0
            return [(">=", v), ("<", (v[0] + 1, 0, 0))]
        return [(op, v)]

    @staticmethod
    def _check(op: str, have: Version, want: Version) -> bool:
        return {
            ">=": have >= want, ">": have > want, "<=": have <= want,
            "<": have < want, "=": have == want, "!=": have != want,
        }[op]

    def allows_version(self, v: Version) -> bool:
        return any(all(self._check(op, v, want) for op, want in g) for g in self.groups)

    def allows_minor(self, minor: Minor) -> bool:
        """True if Helm would install on *some* patch release of this minor."""
        probes = [(minor[0], minor[1], p) for p in (0, 1, 999)]
        return any(self.allows_version(p) for p in probes)
