"""Přehled učení bota pro report: včerejší sázky a jak dopadly, úspěšnost a ROI podle sportu / kategorie / pásma kurzu a postup k dalším metám.

Zdroje: data/nohy.csv (to, co bot ukazuje: výběry, nejjistější, tikety, Pyramida) a data/ucici/*.csv.gz (papírové sázky z celé nabídky na pozadí).
ROI je "flat": jako by se každá sázka hrála stejným vkladem. Při malém počtu sázek je to jen šum, proto se u řádků uvádí n.
"""
import datetime

from . import ucici, vyhodnoceni

# (unikátních vyhodnocených zápasů, dnů dat, co to odemkne). Sázky na stejný zápas jsou závislé, proto se počítají zápasy, ne sázky;
# dny jsou potřeba, aby vzorek nebyl jen z jednoho dne (jeden den = jedna sada výsledků, náhoda).
MILNIKY = [
    (200, 3, "ověřit, že se vyhodnocuje správně, a doplnit trhy, které bot nerozpoznal"),
    (600, 7, "první orientační kalibrace (úspěšnost vs. čekaná pravděpodobnost) u největších sportů"),
    (2000, 14, "smí se upravit pravděpodobnost podle kalibrace a ladit výběr sázek"),
    (6000, 30, "ladit prahy (min. pravděpodobnost, pásma kurzu) a váhy modelu"),
]
KATEGORIE = [("valuedrop", "💧", "1) Value drop"), ("fild", "🎯", "2) Fildův tip"), ("vyber", "🛡️", "3) Tipsport od kurzu 1.30"), ("jistota", "🔒", "4) Nejjistější dne")]
SKUPINY = {"valuedrop": "Value drop", "fild": "Fildův tip", "vyber": "Tipsport od 1.30", "jistota": "Nejjistější dne", "tiket": "Denní tiket", "pyramida": "Pyramida"}


def _stat(rows):
    h = [r for r in rows if r["vysledek"] in ("0", "1")]
    if not h:
        return {"n": 0}
    y = [int(r["vysledek"]) for r in h]
    p = [float(r["p"]) for r in h]
    k = [float(r["kurz"]) for r in h]
    n = len(h)
    return {"n": n, "vyslo": sum(y), "uspesnost": sum(y) / n, "cekano": sum(p) / n,
            "roi": sum((kk - 1) if yy else -1 for yy, kk in zip(y, k)) / n, "brier": sum((pp - yy) ** 2 for pp, yy in zip(p, y)) / n}


def _podle(rows, klic):
    out = {}
    for r in rows:
        out.setdefault(klic(r), []).append(r)
    return {k: _stat(v) for k, v in out.items() if _stat(v)["n"]}


def _pasmo(r):
    k = float(r["kurz"])
    return next((f"{lo:g}–{hi:g}" for lo, hi in ucici.PASMA if lo <= k < hi), "jiné")


def vypocti(datum, nohy=None, uc=None, cfg=None):
    """-> slovník pro report. datum = datum dnešního reportu (YYYY-MM-DD)."""
    nohy = nohy if nohy is not None else vyhodnoceni.nacti()
    uc = uc if uc is not None else ucici.vsechny_radky()
    videno = {r["id"] for r in nohy}
    vse = list(nohy) + [r for r in uc if r["id"] not in videno]
    vcera_d = (datetime.date.fromisoformat(datum) - datetime.timedelta(days=1)).isoformat()
    vcera = [r for r in nohy if r["datum"] == vcera_d]
    vc = {}
    for r in vcera:
        for s in r["skupina"].split("+"):
            vc.setdefault(s, []).append(r)
    vcera_skupiny = {SKUPINY.get(s, s): _stat(v) | {"celkem": len(v)} for s, v in vc.items()}
    chyby = sorted((r for r in vcera if r["vysledek"] == "0"), key=lambda r: -float(r["p"]))[:5]
    h = [r for r in vse if r["vysledek"] in ("0", "1")]
    sporty = _podle(vse, lambda r: r["sport"] or "?")
    dny = {r["datum"] for r in h}
    tempo = len(h) / max(1, len(dny)) if h else 0.0
    dnes = datetime.date.fromisoformat(datum)
    zapasy = {(r["zapas"], (r.get("start") or "")[:10]) for r in h}
    n_zap, n_dny = len(zapasy), len(dny)
    tempo_z = n_zap / max(1, n_dny)
    mety = []
    for cil, min_dny, co in MILNIKY:
        podil = min(1.0, n_zap / cil, n_dny / min_dny)
        eta = None
        if podil < 1 and tempo_z:
            za = max(int(max(0, cil - n_zap) / tempo_z) + 1, max(0, min_dny - n_dny))
            eta = (dnes + datetime.timedelta(days=za)).isoformat()
        mety.append({"cil": cil, "druh": "celkem", "stav": n_zap, "min_dny": min_dny, "dny": n_dny, "podil": podil, "eta": eta, "co": co, "sporty": {}})
    from . import overeni
    seg = overeni.vypocti(vse, cfg)
    return {"segmenty": seg, "segmenty_top": overeni.tabulka(seg), "datum": datum, "vcera_datum": vcera_d, "vcera": vcera_skupiny, "chyby": chyby, "celkem": _stat(vse), "sporty": sporty,
            "skupiny": _podle(nohy, lambda r: SKUPINY.get(r["skupina"].split("+")[0], r["skupina"])),
            "pasma": _podle(vse, _pasmo), "obdobi": obdobi(datum, vse), "vcera_kat": vcera_kategorie(datum, nohy), "dalsi_meta": dalsi_meta(mety), "zapsano": len(vse), "vyhodnoceno": len(h), "tempo_den": tempo, "zapasu": n_zap, "dnu": n_dny, "mety": mety}


def _radek(r):
    return {"zapas": r["zapas"], "sport": r.get("sport") or "", "trh": r["trh"], "vyber": r.get("vyber") or "", "kurz": float(r["kurz"]), "p": float(r["p"]),
            "sazej_od": r.get("sazej_od") or "", "duvera": r.get("duvera") or "", "vysledek": r.get("vysledek") or "", "duvod": (r.get("duvod") or "").replace("Fortuna: ", "")}


def _souhrn_kat(radky):
    h = [x for x in radky if x["vysledek"] in ("0", "1")]
    if not h:
        return {"n": 0, "vyslo": 0, "uspesnost": None, "roi": None, "celkem": len(radky)}
    y = [int(x["vysledek"]) for x in h]
    return {"n": len(h), "vyslo": sum(y), "uspesnost": sum(y) / len(h), "celkem": len(radky),
            "roi": sum((x["kurz"] - 1) if yy else -1 for x, yy in zip(h, y)) / len(h)}


def vcera_kategorie(datum, nohy):
    """Včerejší sázky po kategoriích (tabulky v reportu) + tikety (denní, Pyramida) složené z výsledků jejich nohou."""
    vcera_d = (datetime.date.fromisoformat(datum) - datetime.timedelta(days=1)).isoformat()
    radky = [r for r in nohy if r["datum"] == vcera_d]
    kat = []
    for klic, ikona, nazev in KATEGORIE:
        rr = [_radek(r) for r in radky if klic in r["skupina"].split("+")]
        rr.sort(key=lambda x: -x["p"])
        if rr:
            kat.append({"klic": klic, "ikona": ikona, "nazev": nazev, "radky": rr, "souhrn": _souhrn_kat(rr)})
    podle_id = {r["id"]: r for r in radky}
    tikety = []
    for t in vyhodnoceni.nacti_tikety():
        if t.get("datum") != vcera_d:
            continue
        noze = [_radek(podle_id[i]) for i in t["noze"] if i in podle_id]
        if len(noze) != len(t["noze"]):
            continue
        vys = [x["vysledek"] for x in noze if x["vysledek"] != "V"]
        v = "0" if "0" in vys else "1" if vys and all(x == "1" for x in vys) else ""
        tikety.append({"klic": t["klic"], "nazev": t["nazev"], "kurz": t.get("kurz"), "p": t.get("p"), "noze": noze, "vysledek": v})
    return {"datum": vcera_d, "kategorie": kat, "tikety": tikety}


def obdobi(datum, vse):
    """Úspěšnost, ROI a sporty za včera / 7 dní / 30 dní / celkem (flat ROI). Počítá se z řádků do včerejška včetně."""
    d = datetime.date.fromisoformat(datum)
    hranice = {"vcera": 1, "7": 7, "30": 30, "vse": None}
    out = {}
    for k, dnu in hranice.items():
        od = None if dnu is None else (d - datetime.timedelta(days=dnu)).isoformat()
        rr = [r for r in vse if r["datum"] < datum and (od is None or r["datum"] >= od)]
        out[k] = {"stat": _stat(rr) or {"n": 0}, "sporty": _podle(rr, lambda r: r["sport"] or "?"), "zapsano": len(rr)}
    return out


def dalsi_meta(mety):
    """Nejbližší nesplněná meta (pro koláč): podíl hotovo, počet zápasů a dní, odhad."""
    for m in mety:
        if m["podil"] < 1:
            return dict(m)
    return dict(mety[-1], podil=1.0, co="všechny mety splněny") if mety else {"podil": 0.0, "cil": 0, "druh": "celkem", "stav": 0, "dny": 0, "min_dny": 0, "eta": None, "co": "", "sporty": {}}
