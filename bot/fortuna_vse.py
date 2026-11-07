"""Žebříček z CELÉ nabídky Fortuny pro sporty a trhy, na které nemáme model (vodní pólo, šipky 180, americký fotbal, volejbal...).

Bez nezávislého modelu nelze poznat hranu: p je jen férová pravděpodobnost trhu (bez marže), takže očekávaný výnos
je zhruba minus marže. Žebříček tedy řadí podle ÚSPĚŠNOSTI (p) při nízkém kurzu, ne podle zisku.
Slouží k tomu, aby ses díval na nejpravděpodobnější výsledky z celé nabídky; stabilní zisk mohou dát jen trhy s modelem
(fotbal, tenis) a ověření v logu (Brier, CLV). Výsledky se proto hlásí odděleně a čestně označené.
"""
from . import engine


def nejpravdepodobnejsi(zapasy, cfg, n=None):
    """Pro KAŽDÝ sport nejlepší kandidáti (ne jen celkový top, kde vyhrává fotbal): až `na_sport` na sport, max 1 na zápas.
    Sport bez kandidáta nad `min_p` dostane nejlepšího nad `min_p_slabsi` (aby byl vidět každý sport z nabídky)."""
    u = (cfg.get("fortuna") or {}).get("univerzalni") or {}
    na_sport = int(u.get("na_sport", 2))
    kmin, kmax = float(u.get("min_kurz", 1.30)), float(u.get("max_kurz", 2.00))
    min_p, min_p2, max_marze = float(u.get("min_p", 0.60)), float(u.get("min_p_slabsi", 0.54)), float(u.get("max_marze", 0.10))
    kand = []
    for z in zapasy:
        for t in z.get("dvou") or []:
            kurzy = [k for _, k in t["o"]]
            marze = sum(1 / k for k in kurzy) - 1
            if not (0 <= marze <= max_marze):
                continue                                   # divný trh (půlené linie, chybějící strana) nebo drahá marže
            p = engine.no_vig_power(kurzy)
            for (jm, k), pi in zip(t["o"], p):
                if kmin <= k <= kmax and pi >= min_p2:
                    kand.append({"sport": z.get("sport"), "zapas": z.get("nazev"), "start": z.get("start"), "liga": z.get("turnaj"),
                                 "trh": t["n"], "vyber": jm, "kurz": k, "p": round(pi, 4), "marze": round(marze, 4)})
    kand.sort(key=lambda c: (-c["p"], c["marze"]))
    podle = {}
    for c in kand:
        podle.setdefault(c["sport"], []).append(c)
    out = []
    for sp, lst in podle.items():
        silne = [c for c in lst if c["p"] >= min_p]
        vyb, zap = [], set()
        for c in (silne or lst[:1]):
            if len(vyb) >= na_sport:
                break
            if c["zapas"] not in zap:
                vyb.append(c)
                zap.add(c["zapas"])
        out += vyb
    out.sort(key=lambda c: (-c["p"], c["marze"]))
    return out if n is None else out[:int(n)]


def text(univ):
    """WhatsApp: nejlepší výběr z každého sportu (jeden řádek na sport), seřazeno podle pravděpodobnosti."""
    if not univ:
        return []
    videno, radky = set(), []
    for c in univ:
        if c["sport"] in videno:
            continue
        videno.add(c["sport"])
        radky.append(f"• {c['sport']}: {c['zapas']} – {c['vyber']} ({c['trh']}) kurz {c['kurz']}, p {c['p'] * 100:.0f} %")
    return ["", f"📋 *Nejpravděpodobnější podle sportů* ({len(radky)} sportů, bez modelu, jen férová p trhu)"] + radky
