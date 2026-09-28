"""Fetching raw evidence: GitHub releases, Helm repo index.yaml, doc files.

`Sources` talks to the network. `FixtureSources` reads the same things from a
local folder, so the whole pipeline can be tested without network access.
"""
from __future__ import annotations

import json
import os
import pathlib
import subprocess
import urllib.request

import yaml


def _token() -> str | None:
    tok = os.environ.get("GITHUB_TOKEN")
    if tok:
        return tok
    try:
        return subprocess.check_output(["gh", "auth", "token"], text=True,
                                       stderr=subprocess.DEVNULL).strip() or None
    except Exception:
        return None


class Sources:
    def __init__(self):
        self.token = _token()

    def _get(self, url: str, accept: str | None = None) -> bytes:
        headers = {"User-Agent": "k8s-addon-compat"}
        if accept:
            headers["Accept"] = accept
        if self.token and url.startswith("https://api.github.com/"):
            headers["Authorization"] = f"Bearer {self.token}"
        req = urllib.request.Request(url, headers=headers)
        with urllib.request.urlopen(req, timeout=60) as r:
            return r.read()

    def releases(self, repo: str) -> list[dict]:
        url = f"https://api.github.com/repos/{repo}/releases?per_page=100"
        return json.loads(self._get(url, "application/vnd.github+json"))

    def helm_index(self, url: str) -> dict:
        return yaml.safe_load(self._get(url))

    def text(self, url: str) -> str:
        return self._get(url).decode("utf-8")


class FixtureSources:
    """Reads <dir>/<addon-id>/{releases.json,index.yaml,docs.md,readme.md}."""

    def __init__(self, root: str, addon_ids_by_url: dict[str, str]):
        self.root = pathlib.Path(root)
        self.by_url = addon_ids_by_url

    def _file(self, key: str, name: str) -> pathlib.Path:
        return self.root / self.by_url[key] / name

    def releases(self, repo: str) -> list[dict]:
        return json.loads(self._file(repo, "releases.json").read_text())

    def helm_index(self, url: str) -> dict:
        return yaml.safe_load(self._file(url, "index.yaml").read_text())

    def text(self, url: str) -> str:
        return self._file(url, "docs.md").read_text()
