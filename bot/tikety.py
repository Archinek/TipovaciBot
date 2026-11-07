"""Skládání tiketů z nabídky VŠECH sportů: denní tiket na kurz ~2.00 a Pyramida (tiket pro každé z 10 kol).

Společná úloha: z nezávislých sázek (max. jedna na zápas) vybrat kombinaci, jejíž celkový kurz je aspoň `cil`
a jejíž pravděpodobnost výhry je co nejvyšší. Bez nezávislého modelu je p jen férová pravděpodobnost trhu bez marže
(očekávaný výnos je pak záporný o marži, u kombinací se násobí), s modelem (fotbal, tenis) je p mix model+trh a může být hrana.
Proto se u každého tiketu uvádí hrana a upozornění, když je záporná. Žádný tiket nezaručuje výhru.

Bot nezná kurzy Tipsportu: u tiketu je proto uvedený minimální celkový kurz na Tipsportu (aspoň práh kola, s rezervou)
a u každé sázky "sázej od" = kurz, pod který se kombinace dostane pod požadovaný celkový kurz.
"""
import datetime
import itertools
import math

from . import engine

PRAHY_PYRAMIDY = [1.1, 2.0, 3.0, 4.0, 5.0, 6.0, 7.0, 8.0, 9.0, 10.0]


def _stack(zapasy, fort, cfg, ted):
    """Všechny použitelné sázky (dvou/třícestné trhy + kandidáti s modelem) v časovém okně."""
    t = (cfg.get("tikety") or {})
    od, do = ted + datetime.timedelta(minutes=int(t.get("min_do_startu_min", 20))), ted + datetime.timedelta(hours=float(t.get("okno_h", 20)))
    max_marze = float(t.get("max_marze", 0.10))
    kmin, kmax = float(t.get("min_kurz_noha", 1.05)), float(t.get("max_kurz_noha", 4.0))
    out = []

    def v_okne(iso):
        try:
            s = datetime.datetime.fromisoformat(iso)
        except (TypeError, ValueError):
            return False
        return od <= s <= do

    for z in zapasy:
        if not v_okne(z.get("start")):
            continue
        for tr in z.get("dvou") or []:
            kurzy = [k for _, k in tr["o"]]
            marze = sum(1 / k for k in kurzy) - 1
            if not (0 <= marze <= max_marze):
                continue
            ps = engine.no_vig_power(kurzy)
            for (jm, k), pi in zip(tr["o"], ps):
                if kmin <= k <= kmax and pi >= 0.2:
                    out.append({"sport": z.get("sport"), "zapas": z.get("nazev"), "start": z.get("start"), "liga": z.get("turnaj"),
                                "trh": tr["n"], "vyber": jm, "kurz": k, "p": float(pi), "zdroj": "trh", "duvera": 6})
    from . import tipsteri
    for f in fort or []:
        if v_okne(f.get("start")) and kmin <= f["kurz_fortuna"] <= kmax:
            try:
                d = tipsteri.duvera_10(f, cfg)
            except Exception:
                d = 6
            out.append({"sport": f.get("sport") or "fotbal", "zapas": f["zapas"], "start": f.get("start"), "liga": f.get("liga"),
                        "trh": f["trh"], "vyber": "", "kurz": f["kurz_fortuna"], "p": float(f["p"]), "zdroj": "model", "duvera": d})
    return out


def _vyber_noh(noh, n=45):
    """Zúží zásobu na n sázek rozložených přes pásma kurzu (aby šly poskládat všechny cíle)."""
    pasma = [(1.05, 1.3), (1.3, 1.6), (1.6, 2.0), (2.0, 2.6), (2.6, 4.01)]
    out, videno = [], set()
    for lo, hi in pasma:
        cast = sorted((x for x in noh if lo <= x["kurz"] < hi), key=lambda x: -x["p"] * x["kurz"])
        poc = 0
        for x in cast:
            k = (x["zapas"], x["trh"], x["vyber"])
            if k in videno:
                continue
            videno.add(k)
            out.append(x)
            poc += 1
            if poc >= n // len(pasma):
                break
    return out


def nejlepsi_tiket(noh, cil, rezerva=0.0, vyloucit=(), max_noh=None):
    """Kombinace z různých zápasů s celkovým kurzem >= cil*(1+rezerva) a nejvyšší pravděpodobností výhry."""
    noh = [x for x in noh if x["zapas"] not in vyloucit]
    zasoba = _vyber_noh(noh)
    prah = cil * (1 + rezerva)
    max_noh = max_noh or (3 if cil <= 4 else 4 if cil <= 8 else 5)
    nejlepsi, nej_p = None, 0.0
    for n in range(1, max_noh + 1):
        for comb in itertools.combinations(zasoba, n):
            if len({c["zapas"] for c in comb}) < n:
                continue
            k = math.prod(c["kurz"] for c in comb)
            if k < prah:
                continue
            p = math.prod(c["p"] for c in comb)
            if p > nej_p + 1e-12 or (abs(p - nej_p) <= 1e-12 and nejlepsi and k < nejlepsi["kurz"]):
                nejlepsi, nej_p = {"noze": list(comb), "kurz": k, "p": p}, p
    if not nejlepsi:
        return None
    t = nejlepsi
    t["cil"] = cil
    t["hrana"] = t["p"] * t["kurz"] - 1
    t["duvera"] = max(1, min(10, round(sum(c["duvera"] for c in t["noze"]) / len(t["noze"]) - 0.5 * (len(t["noze"]) - 1))))
    for c in t["noze"]:                                     # sázej od: kurz sázky, pod který celek padne pod cíl
        ostatni = t["kurz"] / c["kurz"]
        c["sazej_od"] = round(max(1.01, cil / ostatni), 2)
    t["min_celkovy_kurz"] = round(cil, 2)
    t["jen_trh"] = all(c["zdroj"] == "trh" for c in t["noze"])
    return t


def sestav(zapasy, fort, cfg, ted):
    """-> {'denni': tiket|None, 'denni_alt': tiket|None, 'pyramida': [{'kolo', 'prah', 'tiket', 'alt'}]}"""
    t = (cfg.get("tikety") or {})
    noh = _stack(zapasy, fort, cfg, ted)
    rez = float(t.get("rezerva", 0.03))
    cil = float(t.get("denni_cil", 2.0))
    d1 = nejlepsi_tiket(noh, cil, rez)
    d2 = nejlepsi_tiket(noh, cil, rez, vyloucit={c["zapas"] for c in d1["noze"]}) if d1 else None
    if d1 and d2 and d2["p"] > d1["p"]:
        d1, d2 = d2, d1
    pyr = []
    for kolo, prah in enumerate(PRAHY_PYRAMIDY, start=1):
        t1 = nejlepsi_tiket(noh, prah, rez)
        t2 = nejlepsi_tiket(noh, prah, rez, vyloucit={c["zapas"] for c in t1["noze"]}) if t1 else None
        if t1 and t2 and t2["p"] > t1["p"]:
            t1, t2 = t2, t1
        pyr.append({"kolo": kolo, "prah": prah, "tiket": t1, "alt": t2})
    return {"denni": d1, "denni_alt": d2, "pyramida": pyr, "pocet_noh": len(noh)}


def radek(t, zona=None):
    from zoneinfo import ZoneInfo
    def cas(iso):
        try:
            return datetime.datetime.fromisoformat(iso).astimezone(ZoneInfo(zona or "Europe/Prague")).strftime("%H:%M")
        except Exception:
            return ""
    return " + ".join(f"{c['zapas']} – {c['vyber'] or c['trh']} @{c['kurz']}" for c in t["noze"])
