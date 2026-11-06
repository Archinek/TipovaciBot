"""Ručně dodané kurzy tvé kanceláře (Tipsport, Fortuna, ...) v data/moje_kurzy.csv.

Proč ručně: Odds API tyto kanceláře nezná a automatické stahování z jejich webů bot záměrně nedělá
(weby automatizaci blokují a podmínky ji zakazují). Kurz si opíšeš z aplikace a bot za tebe spočítá,
jestli se sázka při TVÉM kurzu vyplatí.

Formát (hlavička povinná, oddělovač čárka):
  home,away,trh,vyber,linie,strana,kurz,kancelar
  Arsenal,Chelsea,h2h,Arsenal,,,2.25,tipsport          # výsledek zápasu (vyber = tým nebo Draw)
  Arsenal,Chelsea,fauly,,22.5,over,1.85,tipsport        # doplňkové trhy: goly|rohy|karty|fauly
Jména týmů nemusí být přesná (Man Utd ~ Manchester United).
"""
import csv

from . import config, histdata

CESTA = "moje_kurzy.csv"


def nacti():
    p = config.DATA / CESTA
    if not p.exists():
        return []
    with open(p, encoding="utf-8-sig", newline="") as f:
        out = []
        for r in csv.DictReader(f, restkey="_extra"):
            if r.get("_extra"):          # např. desetinná čárka v kurzu (2,60) rozbije sloupce; raději řádek přeskočit
                print(f"⚠️ moje_kurzy.csv: řádek '{r.get('home')} vs {r.get('away')}' má navíc sloupce "
                      "(používej desetinnou TEČKU, 2.60), přeskakuji.")
                continue
            r = {k: (v.strip() if isinstance(v, str) else "") for k, v in r.items() if k}   # přebytečné sloupce pryč
            try:
                kurz = float(r.get("kurz", "").replace(",", "."))
            except ValueError:
                continue
            if kurz > 1.0:
                r["kurz"] = kurz
                out.append(r)
    return out


def _stejny(a, b):
    return histdata.mapuj(a, [b], min_sim=0.75) is not None


def _zapas(r, home, away):
    d, h = r.get("home", ""), r.get("away", "")
    return (_stejny(d, home) and _stejny(h, away)) or (_stejny(d, away) and _stejny(h, home))   # pořadí týmů se u kanceláří liší


def _info(kurz, fair_p, min_edge):
    edge = kurz * fair_p - 1
    ok = edge >= min_edge
    return edge, ok


def aplikuj(picks, dopl, cfg, extra=None):
    """Doplní kurz tvé kanceláře do tipů (h2h) a doplňkových linií. Vrací počet spárovaných kurzů.
    extra = další řádky stejného formátu (např. automaticky z nabídky Fortuny); ruční CSV má přednost."""
    rows = nacti() + list(extra or [])
    if not rows:
        return 0
    spar = 0
    for p in picks:
        home, _, away = p["zapas"].partition(" vs ")
        for r in rows:
            if r.get("trh", "h2h") != "h2h" or not _zapas(r, home, away):
                continue
            v = r.get("vyber", "")
            if v.lower() in ("draw", "remíza", "remiza", "x"):
                shoda = p["vyber"] == "Draw"
            else:
                shoda = _stejny(v, p["vyber"])
            if not shoda:
                continue
            edge, ok = _info(r["kurz"], float(p["fair_p"]), cfg["nastaveni"]["min_edge"])
            p["moje_kurz"] = r["kurz"]
            p["edge"] = round(edge, 4)
            p["moje_info"] = (f"{r.get('kancelar') or 'tvůj'} {r['kurz']}: edge {edge * 100:+.1f} % "
                              + ("✅ vyplatí se" if ok else f"❌ pod hranou (potřeba {p['min_kurz']})"))
            spar += 1
            break
    for z in dopl or []:
        for l in z["linie"]:
            for r in rows:
                if (r.get("trh") == l["var"] and _zapas(r, z["home_fd"], z["away_fd"])
                        and r.get("strana", "").lower() == l["strana"]
                        and abs(float(r.get("linie") or -1) - float(l["linie"])) < 1e-9):
                    edge, ok = _info(r["kurz"], l["p"], cfg["doplnkove"]["min_edge"])
                    l["moje_kurz"] = r["kurz"]
                    l["moje_edge"] = round(edge, 4)
                    l["moje_info"] = (f"{r['kurz']}: edge {edge * 100:+.1f} % " + ("✅" if ok else "❌"))
                    spar += 1
                    break
    return spar
