"""Načtení konfigurace a proměnných prostředí."""
import os
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
DOCS = ROOT / "docs"


def nacti_cfg():
    with open(ROOT / "sporty.yaml", encoding="utf-8") as f:
        return yaml.safe_load(f)


def env(nazev, default=""):
    return os.environ.get(nazev) or default


def pages_url():
    """URL GitHub Pages: z PAGES_URL, jinak odvozeno z GITHUB_REPOSITORY (owner/repo)."""
    u = env("PAGES_URL")
    if u:
        return u.rstrip("/")
    repo = env("GITHUB_REPOSITORY")
    if "/" in repo:
        owner, name = repo.split("/", 1)
        return f"https://{owner}.github.io/{name}"
    return ""
