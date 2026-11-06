"""Žebříček z CELÉ nabídky Fortuny pro sporty a trhy, na které nemáme model (vodní pólo, šipky 180, americký fotbal, volejbal...).

Bez nezávislého modelu nelze poznat hranu: p je jen férová pravděpodobnost trhu (bez marže), takže očekávaný výnos
je zhruba minus marže. Žebříček tedy řadí podle ÚSPĚŠNOSTI (p) při nízkém kurzu, ne podle zisku.
Slouží k tomu, aby ses díval na nejpravděpodobnější výsledky z celé nabídky; stabilní zisk mohou dát jen trhy s modelem
(fotbal, tenis) a ověření v logu (Brier, CLV). Výsledky se proto hlásí odděleně a čestně označené.
"""
from . import engine


def nejpravdepodobnejsi(zapasy, cfg, n=None):
    u = (cfg.get("fortuna") or {}).get("univerzalni") or {}
    n = int(n if n is not None else u.get("tipu", 8))
    kmin, kmax = float(u.get("min_kurz", 1.30)), float(u.get("max_kurz", 2.00))
    min_p, max_marze = float(u.get("min_p", 0.60)), float(u.get("max_marze", 0.10))
    max_na_sport = int(u.get("max_na_sport", 3))
    kand = []
    for z in zapasy:
        for t in z.get("dvou") or []:
            kurzy = [k for _, k in t["o"]]
            marze = sum(1 / k for k in kurzy) - 1
            if not (0 <= marze <= max_marze):
                continue                                   # divný trh (půlené linie, chybějící strana) nebo drahá marže
            p = engine.no_vig_power(kurzy)
            for (jm, k), pi in zip(t["o"], p):
                if kmin <= k <= kmax and pi >= min_p:
                    kand.append({"sport": z.get("sport"), "zapas": z.get("nazev"), "start": z.get("start"), "liga": z.get("turnaj"),
                                 "trh": t["n"], "vyber": jm, "kurz": k, "p": round(pi, 4), "marze": round(marze, 4)})
    kand.sort(key=lambda c: (-c["p"], c["marze"]))
    out, zapasy_, sporty = [], set(), {}
    for c in kand:
        if len(out) >= n:
            break
        if c["zapas"] in zapasy_ or sporty.get(c["sport"], 0) >= max_na_sport:
            continue
        out.append(c)
        zapasy_.add(c["zapas"])
        sporty[c["sport"]] = sporty.get(c["sport"], 0) + 1
    return out


def text(univ):
    if not univ:
        return []
    t = ["", "📋 *Nejpravděpodobnější z celé nabídky* (bez modelu, jen férová p trhu; zisk nezaručuje)"]
    for c in univ:
        t.append(f"• {c['sport']}: {c['zapas']} – {c['vyber']} ({c['trh']}) kurz {c['kurz']}, p {c['p'] * 100:.0f} %")
    return t
