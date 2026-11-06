"""Matematické jádro: no-vig, hledání value, Kelly. Žádné LLM, žádná síť."""
import datetime
import statistics
from collections import Counter


def no_vig_power(kurzy):
    """Férové pravděpodobnosti: najde k, aby sum((1/o)^k) = 1.
    Lépe než prosté dělení marží zvládá favorite-longshot bias."""
    inv = [1 / o for o in kurzy]
    s = sum(inv)
    if s <= 1.0:
        return [x / s for x in inv]
    lo, hi = 1.0, 10.0
    for _ in range(100):
        mid = (lo + hi) / 2
        if sum(p ** mid for p in inv) > 1:
            lo = mid
        else:
            hi = mid
    k = (lo + hi) / 2
    return [p ** k for p in inv]


def kelly_pct(p, odds, frakce, cap):
    """Doporučený podíl bankrollu (zlomek Kellyho, se stropem)."""
    if odds <= 1:
        return 0.0
    f = (p * odds - 1) / (odds - 1)
    return max(0.0, min(f * frakce, cap))


def min_kurz(p, min_edge):
    return round((1 + min_edge) / p, 2)


def cas(iso):
    return datetime.datetime.fromisoformat(iso.replace("Z", "+00:00"))


def h2h_ceny(event):
    """{kancelář: {výsledek: kurz}} jen z kompletních h2h trhů se stejnou sadou výsledků."""
    out = {}
    for b in event.get("bookmakers", []):
        for m in b.get("markets", []):
            if m.get("key") != "h2h":
                continue
            c = {o["name"]: float(o["price"]) for o in m.get("outcomes", [])
                 if o.get("price") and float(o["price"]) > 1.0}
            if len(c) >= 2:
                out[b["key"]] = c
    if not out:
        return {}
    sada = Counter(frozenset(c) for c in out.values()).most_common(1)[0][0]
    return {b: c for b, c in out.items() if frozenset(c) == sada}


def fair_z_knih(ceny, knihy):
    """Průměr no-vig pravděpodobností přes zadané kanceláře, nebo None."""
    sady = []
    for b in knihy:
        c = ceny.get(b)
        if c:
            vyj = list(c)
            sady.append(dict(zip(vyj, no_vig_power([c[v] for v in vyj]))))
    if not sady:
        return None
    return {v: sum(s[v] for s in sady) / len(sady) for v in sady[0]}


def najdi_kandidaty(event, sport_nazev, scfg, cfg, ted):
    nast = cfg["nastaveni"]
    min_edge = scfg.get("min_edge", nast["min_edge"])
    ceny = h2h_ceny(event)
    if len(ceny) < 2:
        return []
    start = cas(event["commence_time"])
    if start <= ted or start > ted + datetime.timedelta(hours=nast["max_hodin_dopredu"]):
        return []

    sharp_klice = cfg["sharp_kancelare"]
    vyloucene = set(cfg.get("vyloucene_kancelare", [])) | set(sharp_klice)
    soft = {b: c for b, c in ceny.items() if b not in vyloucene}
    moje_cfg = cfg.get("moje_kancelare") or []
    moje = [b for b in moje_cfg if b in ceny]
    # Kanceláře, které Odds API nezná (Tipsport, Fortuna...), se doplňují ručně přes data/moje_kurzy.csv
    # (bot/mojekurzy.py). Dřív se tu zahodil každý zápas, proto vycházelo 0 tipů.

    ref = scfg.get("ref", "pinnacle")
    fair_ref, zdroj_ref = None, ""
    if ref == "pinnacle":
        sharp = [b for b in sharp_klice if b in ceny]
        if not sharp:
            return []
        zdroj_ref = "pinnacle" if "pinnacle" in sharp else sharp[0]
        fair_ref = fair_z_knih(ceny, [zdroj_ref])

    out = []
    for vyber in next(iter(ceny.values())):
        ceny_v = {b: c[vyber] for b, c in soft.items() if vyber in c}
        if len(ceny_v) < nast["min_soft_kancelare"]:
            continue
        best_kniha, best = max(ceny_v.items(), key=lambda kv: kv[1])

        if ref == "pinnacle":
            fair, zdroj = fair_ref, zdroj_ref
        else:
            ostatni = [b for b in ceny if b != best_kniha]
            if len(ostatni) < nast["min_kancelare_konsenzus"]:
                continue
            fair, zdroj = fair_z_knih(ceny, ostatni), f"konsenzus({len(ostatni)})"
        if not fair or vyber not in fair:
            continue
        p = fair[vyber]
        fair_kurz = 1 / p
        if not (nast["min_fair_kurz"] <= fair_kurz <= nast["max_fair_kurz"]):
            continue

        moje_kurz = None
        if moje:
            mk = [ceny[b][vyber] for b in moje if vyber in ceny[b]]
            moje_kurz = max(mk) if mk else None
            if moje_kurz is None:
                continue
        sel = moje_kurz if moje_kurz else best
        edge = sel * p - 1
        if edge < min_edge:
            continue

        riziko = []
        if edge > nast["max_edge"]:
            riziko.append("edge nad limitem, možná chyba kurzu")
        sv = sorted(ceny_v.values())
        if len(sv) >= 3 and best / statistics.median(sv) > 1.10:
            riziko.append("osamocený nejvyšší kurz")

        out.append({
            "id": f"{event['id']}|{vyber}",
            "event_id": event["id"], "sport": sport_nazev,
            "sport_key": event["sport_key"], "tier": scfg.get("tier", ""),
            "zapas": f"{event['home_team']} vs {event['away_team']}",
            "vyber": vyber, "start": start.isoformat(),
            "fair_p": round(p, 4), "fair_kurz": round(fair_kurz, 2), "fair_zdroj": zdroj,
            "min_kurz": min_kurz(p, min_edge),
            "best_kurz": best, "best_kniha": best_kniha, "n_soft": len(ceny_v),
            "moje_kurz": moje_kurz or "", "edge": round(edge, 4),
            "riziko": "; ".join(riziko),
            "stake_pct": round(kelly_pct(p, sel, nast["kelly_frakce"], nast["stake_cap"]) * 100, 2),
        })
    return out


def vyber_top(kandidati, nast, extra=4):
    """Seřadí (čisté před rizikovými, pak podle edge), omezí počet na sport i celkem."""
    serazeno = sorted(kandidati, key=lambda k: (bool(k["riziko"]), -k["edge"]))
    pocty, out = Counter(), []
    for k in serazeno:
        if pocty[k["sport"]] >= nast["max_na_sport"]:
            continue
        pocty[k["sport"]] += 1
        out.append(k)
        if len(out) >= nast["max_tipu_denne"] + extra:
            break
    return out


def vitez(event):
    """Vítěz ze /scores (výsledek h2h): jméno týmu, 'Draw' nebo None když nejde určit."""
    if not event.get("completed") or not event.get("scores"):
        return None
    try:
        sk = {s["name"]: float(s["score"]) for s in event["scores"]}
        d, a = sk[event["home_team"]], sk[event["away_team"]]
    except (KeyError, TypeError, ValueError):
        return None
    if d == a:
        return "Draw"
    return event["home_team"] if d > a else event["away_team"]
