"""Log sázek (data/bety.csv) a metriky. CSV = přehledné diffy v gitu."""
import csv
import json
import os
from collections import defaultdict

from . import config

POLE = ["id", "datum", "sport", "sport_key", "tier", "rezim", "event_id", "zapas", "vyber",
        "start", "fair_p", "fair_zdroj", "fair_kurz", "min_kurz", "best_kurz", "best_kniha",
        "n_soft", "moje_kurz", "edge", "riziko", "stake_pct", "veto", "veto_duvod",
        "kurz_vzat", "closing_fair_p", "vysledek", "zisk_paper", "zisk_real"]


def _cesta():
    return config.DATA / "bety.csv"


def nacti():
    if not _cesta().exists():
        return []
    with open(_cesta(), encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))


def uloz(rows):
    config.DATA.mkdir(parents=True, exist_ok=True)
    tmp = str(_cesta()) + ".tmp"
    with open(tmp, "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=POLE, extrasaction="ignore")
        w.writeheader()
        for r in rows:
            w.writerow({k: r.get(k, "") for k in POLE})
    os.replace(tmp, _cesta())


def pridej(nove):
    """Přidá řádky, které ještě nejsou (podle id). Vrací počet přidaných."""
    rows = nacti()
    mam = {r["id"] for r in rows}
    pridano = [n for n in nove if n["id"] not in mam]
    uloz(rows + pridano)
    return len(pridano)


def _f(x):
    try:
        return float(x)
    except (TypeError, ValueError):
        return None


def metriky(rows):
    """Metriky nad vyhodnocenými řádky (VETO a nevyhodnocené se nepočítají)."""
    r = [x for x in rows if x.get("vysledek") in ("win", "loss") and x.get("veto") != "VETO"]
    n = len(r)
    if not n:
        return {"n": 0}
    wins = sum(x["vysledek"] == "win" for x in r)
    zisk = sum(_f(x["zisk_paper"]) or 0 for x in r)
    clv = [_f(x["best_kurz"]) * _f(x["closing_fair_p"]) - 1
           for x in r if _f(x["closing_fair_p"]) and _f(x["best_kurz"])]
    posun = [_f(x["closing_fair_p"]) / _f(x["fair_p"]) - 1
             for x in r if _f(x["closing_fair_p"]) and _f(x["fair_p"])]
    real = [x for x in r if _f(x["kurz_vzat"]) and _f(x["zisk_real"]) is not None]
    return {
        "n": n,
        "winrate": round(wins / n, 3),
        "ocekavany_winrate": round(sum(_f(x["fair_p"]) for x in r) / n, 3),
        "roi_paper": round(zisk / n, 4),
        "avg_clv": round(sum(clv) / len(clv), 4) if clv else None,
        "n_clv": len(clv),
        "avg_posun_cary": round(sum(posun) / len(posun), 4) if posun else None,
        "n_real": len(real),
        "roi_real": round(sum(_f(x["zisk_real"]) for x in real) / len(real), 4) if real else None,
    }


def metriky_podle(rows, klic):
    skupiny = defaultdict(list)
    for r in rows:
        skupiny[r.get(klic) or "?"].append(r)
    return {k: metriky(v) for k, v in sorted(skupiny.items())}


def doporuceny_rezim(m, auto):
    """Doporučí režim sportu podle CLV. None = zatím málo dat / beze změny."""
    if not m or m.get("n", 0) < auto["min_bets_hodnoceni"] or m.get("avg_clv") is None:
        return None
    if m["avg_clv"] >= auto["povys_live_pokud_avg_clv_nad"]:
        return "live"
    if m["avg_clv"] <= auto["vypni_pokud_avg_clv_pod"]:
        return "off"
    return "paper"


def nacti_rezimy():
    p = config.DATA / "rezimy.json"
    if p.exists():
        try:
            return json.loads(p.read_text(encoding="utf-8"))
        except ValueError:
            return {}
    return {}


def uloz_rezimy(d):
    (config.DATA / "rezimy.json").write_text(
        json.dumps(d, ensure_ascii=False, indent=2), encoding="utf-8")
