"""Učící sběr dat: bot si "natipuje" VŠECHNY vyhodnotitelné příležitosti z nabídky Fortuny (papírově, bez sázek) a další dny je vyhodnotí.

Cíl: rychle nasbírat tisíce vzorků po sportech, trzích a pásmech kurzu a z nich se naučit, kde se trh mýlí (např. přeceňovaní
favorité, podceňovaná 'under'), místo čekání na pár doporučených tipů denně. Loguje se jen to, co umíme vyhodnotit podle výsledků
z internetu (NHL, NFL, NBA, WNBA, MLB; vítěz zápasu, součet bodů/gólů, střely v hokeji). Soubor na den: data/ucici/<datum>.csv.gz
(drobný, ať repozitář nebobtná). Do reportu se nic nepíše; výsledkem je tabulka kalibrace data/kalibrace_trhu.json.
"""
import csv
import datetime
import gzip
import io
import json

from . import config, engine, vyhodnoceni

LIGY = {"NHL", "NFL", "NBA", "WNBA", "MLB"}
POLE = vyhodnoceni.POLE
PASMA = [(1.0, 1.3), (1.3, 1.6), (1.6, 2.0), (2.0, 2.6), (2.6, 4.01)]


def _adresar():
    return config.DATA / "ucici"


def _nacti(f):
    if not f.exists():
        return []
    with gzip.open(f, "rt", encoding="utf-8", newline="") as fh:
        return list(csv.DictReader(fh))


def _uloz(f, rows):
    f.parent.mkdir(parents=True, exist_ok=True)
    buf = io.StringIO()
    w = csv.DictWriter(buf, fieldnames=POLE, extrasaction="ignore")
    w.writeheader()
    w.writerows(rows)
    with gzip.open(f, "wt", encoding="utf-8", newline="") as fh:
        fh.write(buf.getvalue())


def _rozpoznan(trh, vyber, sport, zapas="A - B"):
    """Umíme tuhle sázku vyhodnotit? (zkouška na falešném výsledku)"""
    v = {"sport": sport, "h": 3, "a": 2, "extra": {"reg_h": 3, "reg_a": 2, "sog_h": 30, "sog_a": 28, "prodlouzeni": False}}
    y, duvod = vyhodnoceni.rozhodni({"zapas": zapas, "trh": trh, "vyber": vyber}, v)
    return duvod not in ("trh nerozpoznán", "linie")


def zaloguj(datum, zapasy, ted, okno_h=36, log=print, cfg=None):
    """Zapíše všechny vyhodnotitelné dvou/třícestné sázky zápasů začínajících v okně. Vrací počet nových řádků."""
    f = _adresar() / f"{datum}.csv.gz"
    rows = _nacti(f)
    mam = {r["id"] for r in rows}
    for dd in (1, 2):                                                   # sázky už zapsané dřívějším během se neopakují
        d = (datetime.date.fromisoformat(datum) - datetime.timedelta(days=dd)).isoformat()
        mam |= {r["id"] for r in _nacti(_adresar() / f"{d}.csv.gz")}
    u = (cfg or {}).get("ucici") or {}
    vse = bool(u.get("vse", False))                                     # všechny sporty a trhy (výsledky z API Fortuny)
    kmin, kmax, max_marze = float(u.get("min_kurz", 1.05)), float(u.get("max_kurz", 4.0 if not vse else 8.0)), float(u.get("max_marze", 0.12))
    okno_h = float(u.get("okno_h", okno_h))
    limit = int(u.get("max_radku_den", 20000))
    if ted.tzinfo:                                                      # porovnává se s časy zápasů v UTC bez zóny
        ted = ted.astimezone(datetime.timezone.utc).replace(tzinfo=None)
    od, do = ted + datetime.timedelta(minutes=15), ted + datetime.timedelta(hours=okno_h)
    nove = 0
    nerozp = {}
    for z in zapasy:
        if not vse and z.get("turnaj") not in LIGY:
            continue
        if len(rows) >= limit:
            break
        try:
            s = datetime.datetime.fromisoformat(z["start"])
        except (KeyError, TypeError, ValueError):
            continue
        if s.tzinfo:
            s = s.astimezone(datetime.timezone.utc).replace(tzinfo=None)
        if not (od <= s <= do):
            continue
        for t in z.get("dvou") or []:
            kurzy = [k for _, k in t["o"]]
            marze = sum(1 / k for k in kurzy) - 1
            if not (0 <= marze <= max_marze) or len(kurzy) < 2:
                continue
            ps = engine.no_vig_power(kurzy)
            for (jm, k), p in zip(t["o"], ps):
                if not (kmin <= k <= kmax):
                    continue
                if not vse and not _rozpoznan(t["n"], jm, z["sport"], z["nazev"]):
                    nerozp[t["n"][:60]] = nerozp.get(t["n"][:60], 0) + 1
                    continue
                i = f"{z['nazev']}|{t['n']}|{jm}|{z['start'][:10]}"
                if i in mam:
                    continue
                mam.add(i)
                rows.append({"id": i, "datum": datum, "sport": z["sport"], "liga": z.get("turnaj", ""), "zapas": z["nazev"], "start": s.isoformat(timespec="minutes"),
                             "trh": t["n"], "vyber": jm, "kurz": k, "p": round(float(p), 4), "zdroj": "trh", "skupina": "ucici", "vysledek": "", "duvod": ""})
                nove += 1
    if rows:
        _uloz(f, rows)
    if nerozp:                                                           # které trhy zatím neumíme vyhodnotit (pro doplnění pravidel)
        (config.DATA / "ucici_nerozpoznane.json").write_text(
            json.dumps(dict(sorted(nerozp.items(), key=lambda x: -x[1])[:120]), ensure_ascii=False, indent=1), encoding="utf-8")
    return nove


def vyhodnot(ted, log=print, dni=4):
    """Vyhodnotí nevyhodnocené sázky ze souborů posledních `dni` dní (čas začátku zápasu je v řádku)."""
    celkem = 0
    for dd in range(0, dni + 1):
        d = (ted.date() - datetime.timedelta(days=dd)).isoformat()
        f = _adresar() / f"{d}.csv.gz"
        rows = _nacti(f)
        if not rows:
            continue
        n = vyhodnoceni.vyhodnot_radky(rows, ted, log=lambda *a: None)
        if n:
            _uloz(f, rows)
        celkem += n
    return celkem


def vsechny_radky():
    out = []
    if _adresar().exists():
        for f in sorted(_adresar().glob("*.csv.gz")):
            out += _nacti(f)
    return out


def kalibrace(rows=None, min_n=1):
    """Tabulka: sport x pásmo kurzu -> n, průměrné p trhu, skutečná úspěšnost, flat ROI. Slouží k nalezení systematických chyb trhu."""
    rows = rows if rows is not None else vsechny_radky()
    t = {}
    for r in rows:
        if r["vysledek"] not in ("0", "1"):
            continue
        k, y, p = float(r["kurz"]), int(r["vysledek"]), float(r["p"])
        pasmo = next((f"{lo}-{hi:g}" for lo, hi in PASMA if lo <= k < hi), "jiné")
        for klic in (f"{r['sport']}|{pasmo}", f"{r['sport']}|vše"):
            x = t.setdefault(klic, {"n": 0, "vyslo": 0, "p": 0.0, "roi": 0.0})
            x["n"] += 1
            x["vyslo"] += y
            x["p"] += p
            x["roi"] += (k - 1) if y else -1
    out = {}
    for klic, x in t.items():
        if x["n"] >= min_n:
            out[klic] = {"n": x["n"], "p_trhu": round(x["p"] / x["n"], 4), "uspesnost": round(x["vyslo"] / x["n"], 4), "roi": round(x["roi"] / x["n"], 4)}
    return out


def uloz_kalibraci(log=print):
    k = kalibrace()
    (config.DATA).mkdir(parents=True, exist_ok=True)
    (config.DATA / "kalibrace_trhu.json").write_text(json.dumps(k, ensure_ascii=False, indent=1, sort_keys=True), encoding="utf-8")
    n = sum(v["n"] for kk, v in k.items() if kk.endswith("|vše"))
    log(f"   kalibrace trhu: {n} vyhodnocených papírových sázek, {len(k)} řádků tabulky")
    return k
