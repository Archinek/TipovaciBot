"""Historická data zápasů z football-data.co.uk (volně dostupné CSV).

Sloupce, které používáme: Date, HomeTeam, AwayTeam, FTHG/FTAG (góly), HC/AC (rohy),
HF/AF (fauly), HY/AY + HR/AR (karty), Referee. Pokrytí: hlavní evropské ligy
(české ligy tu nejsou).
"""
import csv
import datetime
import io
import os
import re
import time
import unicodedata
import urllib.error
import urllib.request
from difflib import SequenceMatcher

from . import config

# klíč Odds API -> kód ligy ve football-data (klíče si ověř příkazem `sports`)
LIGY = {
    "soccer_epl": "E0", "soccer_efl_champ": "E1",
    "soccer_germany_bundesliga": "D1", "soccer_germany_bundesliga2": "D2",
    "soccer_spain_la_liga": "SP1", "soccer_spain_segunda_division": "SP2",
    "soccer_italy_serie_a": "I1", "soccer_italy_serie_b": "I2",
    "soccer_france_ligue_one": "F1", "soccer_france_ligue_two": "F2",
    "soccer_netherlands_eredivisie": "N1", "soccer_belgium_first_div": "B1",
    "soccer_portugal_primeira_liga": "P1", "soccer_turkey_super_league": "T1",
    "soccer_greece_super_league": "G1", "soccer_spl": "SC0",
}
URL = "https://www.football-data.co.uk/mmz4281/{sezona}/{kod}.csv"

ALIASY = {
    "man united": "manchester united", "man utd": "manchester united", "man u": "manchester united", "man city": "manchester city",
    "nott m forest": "nottingham forest", "ath madrid": "atletico madrid",
    "ath bilbao": "athletic bilbao", "m gladbach": "borussia monchengladbach",
    "sp lisbon": "sporting lisbon", "sociedad": "real sociedad", "betis": "real betis",
    "leverkusen": "bayer leverkusen", "dortmund": "borussia dortmund",
    "ein frankfurt": "eintracht frankfurt", "inter": "inter milan",
    "paris sg": "paris saint germain", "st etienne": "saint etienne",
    "wolves": "wolverhampton wanderers", "spurs": "tottenham hotspur",
    "newcastle": "newcastle united", "west ham": "west ham united",
    "brighton": "brighton and hove albion", "leeds": "leeds united",
}
_STOP = {"fc", "cf", "ac", "sc", "afc", "1", "04", "05", "bsc", "rcd", "ud", "sv", "fk"}


def sezona_kod(d):
    z = d.year if d.month >= 7 else d.year - 1
    return f"{z % 100:02d}{(z + 1) % 100:02d}"


def _norm(n):
    s = unicodedata.normalize("NFKD", n).encode("ascii", "ignore").decode().lower()
    s = re.sub(r"[^a-z0-9 ]", " ", s)
    s = " ".join(t for t in s.split() if t not in _STOP)
    return ALIASY.get(s, s)


def mapuj(jmeno, kandidati, min_sim=0.78):
    """Přiřadí jméno z Odds API ke jménu ve football-data. None = nespárováno (raději nic než hádat)."""
    n = _norm(jmeno)
    best, sc = None, 0.0
    for k in kandidati:
        kn = _norm(k)
        s = 1.0 if kn == n else max(SequenceMatcher(None, n, kn).ratio(),
                                    0.9 if (n in kn or kn in n) and min(len(n), len(kn)) >= 5 else 0)
        if s > sc:
            best, sc = k, s
    return best if sc >= min_sim else None


def _datum(t):
    for f in ("%d/%m/%Y", "%d/%m/%y", "%Y-%m-%d"):
        try:
            return datetime.datetime.strptime(t.strip(), f).replace(tzinfo=datetime.timezone.utc)
        except ValueError:
            pass
    raise ValueError(t)


def _int(x):
    return int(float(x))


def parsuj(text, cervena=1):
    """CSV text -> seznam zápasů {datum, home, away, ref, y: {promenna: (domaci, hoste)}}."""
    out = []
    for r in csv.DictReader(io.StringIO(text)):
        try:
            d = _datum(r["Date"])
            h, a = r["HomeTeam"].strip(), r["AwayTeam"].strip()
            y = {"goly": (_int(r["FTHG"]), _int(r["FTAG"]))}
        except (KeyError, ValueError, TypeError, AttributeError):
            continue
        for v, (c1, c2) in {"rohy": ("HC", "AC"), "fauly": ("HF", "AF"), "sot": ("HST", "AST")}.items():
            try:
                y[v] = (_int(r[c1]), _int(r[c2]))
            except (KeyError, ValueError, TypeError):
                pass
        try:
            y["karty"] = (_int(r["HY"]) + cervena * _int(r["HR"]),
                          _int(r["AY"]) + cervena * _int(r["AR"]))
        except (KeyError, ValueError, TypeError):
            pass
        out.append({"datum": d, "home": h, "away": a,
                    "ref": (r.get("Referee") or "").strip(), "y": y})
    return sorted(out, key=lambda x: x["datum"])


def stahni(kod, sezona, max_stari_h=10):
    """Stáhne CSV (s cache v data/hist/). Při chybě sítě použije cache, jinak None."""
    cesta = config.DATA / "hist" / f"{kod}_{sezona}.csv"
    if cesta.exists() and (time.time() - cesta.stat().st_mtime) < max_stari_h * 3600:
        return cesta.read_bytes().decode("utf-8-sig", errors="replace")
    try:
        req = urllib.request.Request(URL.format(sezona=sezona, kod=kod),
                                     headers={"User-Agent": "tipovaci-bot/1.0"})
        with urllib.request.urlopen(req, timeout=30) as r:
            raw = r.read()
        cesta.parent.mkdir(parents=True, exist_ok=True)
        cesta.write_bytes(raw)
        return raw.decode("utf-8-sig", errors="replace")
    except (urllib.error.URLError, OSError):
        if cesta.exists():
            return cesta.read_bytes().decode("utf-8-sig", errors="replace")
        return None


def nacti_ligu(kod, ted, sezon=2, cervena=1):
    """Zápasy poslední `sezon` sezón (včetně rozehrané), jen před `ted`."""
    rows = []
    z = ted.year if ted.month >= 7 else ted.year - 1
    for i in range(sezon):
        zz = z - i
        text = stahni(kod, f"{zz % 100:02d}{(zz + 1) % 100:02d}")
        if text:
            rows += parsuj(text, cervena)
    return sorted((r for r in rows if r["datum"] < ted), key=lambda x: x["datum"])
