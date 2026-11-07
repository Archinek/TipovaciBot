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


def pages_reports_url():
    """Základ adresy reportů. Pages běží z kořene repozitáře, reporty jsou v docs/reports -> .../docs/reports/<datum>.html.
    Když přepneš Pages na složku /docs, nastav proměnnou repozitáře PAGES_PREFIX na prázdnou hodnotu ("-" = prázdné)."""
    pref = env("PAGES_PREFIX", "/docs")
    pref = "" if pref in ("-", "") else pref.rstrip("/")
    u = pages_url()
    return f"{u}{pref}" if u else ""


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


def s_limitem(fn, sekund):
    """Zavolá fn() a po `sekund` vyhodí TimeoutError (volání na síť bez timeoutu by jinak zablokovalo celý běh).
    Vlákno je daemon: po timeoutu dál dobíhá v pozadí, ale proces skončí normálně."""
    import threading
    vysl = {}

    def _run():
        try:
            vysl["v"] = fn()
        except BaseException as e:      # noqa: BLE001 - předáme volajícímu
            vysl["e"] = e
    t = threading.Thread(target=_run, daemon=True)
    t.start()
    t.join(sekund)
    if t.is_alive():
        raise TimeoutError(f"volání neodpovědělo do {sekund} s")
    if "e" in vysl:
        raise vysl["e"]
    return vysl.get("v")


def gemini_modely():
    """Modely Gemini v pořadí pokusů. GEMINI_MODEL (proměnná repozitáře) má přednost; názvy se u Google mění,
    starší 2.5 modely už pro nové účty vrací 404 (hláška doporučila 3.1-pro-preview a 3.8-flash)."""
    vlastni = env("GEMINI_MODEL", "")
    out = [m for m in (vlastni, "gemini-3.8-flash") if m]
    return list(dict.fromkeys(out))
