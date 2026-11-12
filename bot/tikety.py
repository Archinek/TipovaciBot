"""Skládání tiketů z nabídky VŠECH sportů: denní tiket na kurz ~2.00 a Pyramida (tiket pro každé z 10 kol).

Společná úloha: z nezávislých sázek (max. jedna na zápas) vybrat kombinaci, jejíž celkový kurz je aspoň `cil`
a jejíž pravděpodobnost výhry je co nejvyšší. Bez nezávislého modelu je p jen férová pravděpodobnost trhu bez marže
(očekávaný výnos je pak záporný o marži, u kombinací se násobí), s modelem (fotbal, tenis) je p mix model+trh a může být hrana.
Proto se u každého tiketu uvádí hrana a upozornění, když je záporná. Žádný tiket nezaručuje výhru.

Bot nezná kurzy Tipsportu: u tiketu je proto uvedený minimální celkový kurz na Tipsportu (aspoň práh kola, s rezervou)
a u každé sázky "sázej od" = kurz, pod který se kombinace dostane pod požadovaný celkový kurz.
"""
import datetime
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


def _tip_kurz(k, srazka):
    """Odhad kurzu Tipsportu z kurzu Fortuny: srazí se zisková část kurzu (1.06 -> ~1.05, 1.40 -> ~1.36)."""
    return 1.0 + (k - 1.0) * (1.0 - srazka)


def _zasoba(noh, srazka, shrink, n=60):
    """Zúží zásobu sázek: nejlepší poměr 'cena v pravděpodobnosti' / 'zisk v kurzu' + nejjistější sázky; max. jedna varianta na trh."""
    def cena(x):
        lk = math.log(max(1.0001, _tip_kurz(x["kurz"], srazka)))
        return -math.log(x["p"] * (1 - shrink)) / lk
    videno, out = set(), []
    for x in sorted(noh, key=cena)[:n] + sorted(noh, key=lambda x: -x["p"])[: n // 3]:
        k = (x["zapas"], x["trh"], x["vyber"])
        if k not in videno:
            videno.add(k)
            out.append(x)
    return out


def nejlepsi_tiket(noh, cil, rezerva=0.0, vyloucit=(), max_noh=None, srazka=0.0, shrink=0.0):
    """Kombinace z různých zápasů, jejíž ODHADNUTÝ kurz na Tipsportu je >= cil*(1+rezerva) a pravděpodobnost výhry nejvyšší.

    Přesné hledání (větvení s ořezáváním): p kombinace jen klesá s každou další nohou, takže se zahodí každá větev,
    která už nepřekoná dosavadní nejlepší, nebo která už nemůže dosáhnout kurzu. Sázky s kurzem blízko 1.0 se tím samy
    vyřadí (na Tipsportu by se jejich součin dostal pod práh); `shrink` je srážka z p za každou nohu (nejistota odhadu).
    """
    noh = [x for x in noh if x["zapas"] not in vyloucit]
    zasoba = _zasoba(noh, srazka, shrink)
    prah = cil * (1 + rezerva)
    max_noh = max_noh or (3 if cil <= 3 else 4 if cil <= 6 else 5)
    lt = math.log(prah)
    pol = [(math.log(x["p"] * (1 - shrink)), math.log(max(1.0001, _tip_kurz(x["kurz"], srazka))), x) for x in zasoba]
    pol.sort(key=lambda r: -r[0])                              # nejjistější první
    nejvyssi_lk = sorted((r[1] for r in pol), reverse=True)
    stav = {"lp": -1e18, "comb": None}

    def dfs(start, comb, lp, lk, zapasy):
        if lk >= lt - 1e-12:
            if lp > stav["lp"] + 1e-12:
                stav["lp"], stav["comb"] = lp, list(comb)
            return                                             # další noha by p jen snížila
        zbyva = max_noh - len(comb)
        if zbyva <= 0 or lk + sum(nejvyssi_lk[:zbyva]) < lt:
            return
        for i in range(start, len(pol)):
            l_p, l_k, x = pol[i]
            if lp + l_p <= stav["lp"] or x["zapas"] in zapasy:
                continue
            comb.append(x)
            zapasy.add(x["zapas"])
            dfs(i + 1, comb, lp + l_p, lk + l_k, zapasy)
            zapasy.discard(x["zapas"])
            comb.pop()

    dfs(0, [], 0.0, 0.0, set())
    if not stav["comb"]:
        return None
    comb = stav["comb"]
    t = {"noze": comb, "kurz": math.prod(c["kurz"] for c in comb), "p": math.prod(c["p"] for c in comb)}
    tip = [_tip_kurz(c["kurz"], srazka) for c in comb]
    t["kurz_tipsport_odhad"] = round(math.prod(tip), 3)
    t["cil"] = cil
    t["hrana"] = t["p"] * t["kurz"] - 1
    t["duvera"] = max(1, min(10, round(sum(c["duvera"] for c in comb) / len(comb) - 0.5 * (len(comb) - 1))))
    for c, tk in zip(comb, tip):                              # sázej od: nejnižší kurz na Tipsportu, při kterém celek ještě drží cíl
        ostatni = t["kurz_tipsport_odhad"] / tk
        c["sazej_od"] = round(max(1.01, math.ceil(cil / ostatni * 100) / 100), 2)
    t["min_celkovy_kurz"] = round(cil, 2)
    t["jen_trh"] = all(c["zdroj"] == "trh" for c in comb)
    return t


def jistoty(zapasy, fort, cfg, ted):
    """Nejjistější příležitosti dne napříč všemi sporty a kurzy: nejvyšší pravděpodobnost, max. jedna na zápas.
    Bez záruky: p je nejlepší odhad (trh bez marže, u fotbalu a tenisu smíchaný s modelem). Analýza (Gemini) pak vyřadí VETO."""
    r = (cfg.get("report") or {})
    t = dict(cfg.get("tikety") or {})
    t["min_kurz_noha"], t["max_kurz_noha"] = float(r.get("jistota_min_kurz", 1.05)), 100.0
    noh = _stack(zapasy, fort, {**cfg, "tikety": t}, ted)
    nej = {}
    for x in noh:
        if x["p"] >= float(r.get("jistota_min_p", 0.85)) and (x["zapas"] not in nej or x["p"] > nej[x["zapas"]]["p"]):
            nej[x["zapas"]] = x
    out = sorted(nej.values(), key=lambda x: -x["p"])[: int(r.get("jistota_max", 6))]
    return [{**{k: v for k, v in x.items() if k != "duvera"}, "sazej_od": math.ceil(1.02 / x["p"] * 100) / 100} for x in out]


def sestav(zapasy, fort, cfg, ted):
    """-> {'denni': tiket|None, 'denni_alt': tiket|None, 'pyramida': [{'kolo', 'prah', 'tiket', 'alt'}]}"""
    t = (cfg.get("tikety") or {})
    noh = _stack(zapasy, fort, cfg, ted)
    rez = float(t.get("rezerva", 0.03))
    cil = float(t.get("denni_cil", 2.0))
    sr, sh = float(t.get("tipsport_srazka", 0.12)), float(t.get("p_srazka_za_nohu", 0.01))
    d1 = nejlepsi_tiket(noh, cil, rez, srazka=sr, shrink=sh)
    d2 = nejlepsi_tiket(noh, cil, rez, vyloucit={c["zapas"] for c in d1["noze"]}, srazka=sr, shrink=sh) if d1 else None
    if d1 and d2 and d2["p"] > d1["p"]:
        d1, d2 = d2, d1
    pyr = []
    for kolo, prah in enumerate(PRAHY_PYRAMIDY, start=1):
        t1 = nejlepsi_tiket(noh, prah, rez, srazka=sr, shrink=sh)
        t2 = nejlepsi_tiket(noh, prah, rez, vyloucit={c["zapas"] for c in t1["noze"]}, srazka=sr, shrink=sh) if t1 else None
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
