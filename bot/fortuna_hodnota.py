"""Porovnání dnešní anonymní nabídky Fortuny s vlastním modelem (góly, případně rohy/karty/fauly).

Postup pro každý fotbalový zápas z nabídky:
  1. spáruje týmy s historií football-data (jen přesná shoda názvu nebo velmi podobný název; raději nic než hádat)
  2. model dá pravděpodobnost každé nabízené linie (Over/Under, góly týmu, oba dají gól)
  3. pravděpodobnost se smíchá s férovou pravděpodobností samotného trhu (Fortuna bez marže): vaha_modelu
  4. hrana = kurz × p − 1; do výstupu jdou jen hrany nad prahem a modely, které se s trhem nerozcházejí o moc
Kurz Fortuny je jen orientační ceník: sázíš jinde, proto se uvádí "sázej od" (hranice, od které se vyplatí).
Model není prokázaně lepší než trh. Proto míchání s trhem a strop na rozchod. Výsledky se logují ke kalibraci.
"""
import math
from collections import defaultdict
from difflib import SequenceMatcher

from . import config, doplnkove as dp, engine, histdata
from .fortuna import klic_nohy, kod_ligy


def je_zena_ml(t):
    n = (t or "").lower()
    return any(x in n for x in ("ženy", "(u", "amat"))

_ALIASY = {}
NAZEV = {"goly": "Góly v zápase", "goly_dom": "Góly domácích", "goly_hos": "Góly hostů", "btts": "Oba dají gól",
         "rohy": "Rohy", "karty": "Karty", "fauly": "Fauly", "sot": "Střely na bránu", "sot_dom": "Střely na bránu domácích", "sot_hos": "Střely na bránu hostů",
         "esa": "Esa v zápase", "esa_hrac": "Esa hráče", "df": "Dvojchyby v zápase", "df_hrac": "Dvojchyby hráče"}


def nacti_aliasy():
    """data/aliasy_tymu.json: {"jméno týmu na Fortuně": "jméno ve football-data"}, např. {"Bayern Mnichov": "Bayern Munich"}.
    Fortuna píše česky, football-data anglicky; bez aliasu se tým nespáruje (raději nic než hádat)."""
    import json
    p = config.DATA / "aliasy_tymu.json"
    if not p.exists():
        return {}
    try:
        return {histdata._norm(k): v for k, v in json.loads(p.read_text(encoding="utf-8")).items() if isinstance(v, str)}
    except (ValueError, OSError):
        return {}


def _par(jmeno, tymy_norm, volne=False):
    """Přísnější párování než histdata.mapuj: shoda názvu, nebo podobnost >= 0.9 (žádné 'obsahuje').
    volne=True (liga je známá z názvu turnaje): podobnost >= 0.8, nebo jednoznačná shoda slov ('olympique lyon' ~ 'lyon')."""
    n = histdata._norm(jmeno or "")
    if not n:
        return None
    a = _ALIASY.get(n)
    if a:
        n = histdata._norm(a)
    best, sc = None, 0.0
    for orig, kn in tymy_norm.items():
        s = 1.0 if kn == n else SequenceMatcher(None, n, kn).ratio()
        if s > sc:
            best, sc = orig, s
    if sc >= (0.8 if volne else 0.9):
        return best
    if volne:
        slova = set(n.split())
        shody = [orig for orig, kn in tymy_norm.items() if kn and set(kn.split()) <= slova]
        if len(shody) == 1:
            return shody[0]
    return None


def _poisson_nad(mu, L):
    """P(X > L) pro půlkovou linii, Poisson (góly týmu)."""
    k = int(math.floor(L))
    c = sum(math.exp(i * math.log(max(mu, 1e-9)) - mu - math.lgamma(i + 1)) for i in range(k + 1))
    return 1.0 - c


def p_nohy(model, h, a, noha):
    """Pravděpodobnost nohy {trh, linie, strana} podle modelu, nebo None."""
    trh, L, st = noha["trh"], noha.get("linie"), noha["strana"]
    var = model["var"]
    if trh in ("goly", "rohy", "karty", "fauly", "sot"):
        v = trh
        if v not in var:
            return None
        mu = dp.predikuj(var[v], h, a, None, v)
        if mu is None:
            return None
        p = dp.p_over_linie(mu, var[v]["r"], [L])[L]
        return p if st == "over" else 1.0 - p
    if trh in ("sot_dom", "sot_hos"):                 # střely na bránu jednoho týmu (JirAdam: "Počet střel Ipswich na bránu")
        if "sot" not in var:
            return None
        mt = dp.mu_tymu(var["sot"], h, a, "sot")
        if mt is None:
            return None
        p = dp.p_over_linie(mt[0] if trh == "sot_dom" else mt[1], var["sot"]["r"], [L])[L]
        return p if st == "over" else 1.0 - p
    if "goly" not in var:
        return None
    mm = dp.mu_tymu(var["goly"], h, a, "goly")
    if mm is None:
        return None
    if trh in ("goly_dom", "goly_hos"):
        p = _poisson_nad(mm[0] if trh == "goly_dom" else mm[1], L)
        return p if st == "over" else 1.0 - p
    if trh == "btts":
        p = (1 - math.exp(-mm[0])) * (1 - math.exp(-mm[1]))
        return p if st == "ano" else 1.0 - p
    return None


def fortuna_top(z):
    from .fortuna import jetop
    return jetop({"name": z.get("turnaj")})


def _uloz_nesparovane(seznam, log):
    """TOP ligové zápasy, u kterých se nepodařilo spárovat týmy: data/fortuna_nesparovane.json (doplň aliasy do aliasy_tymu.json)."""
    import json
    try:
        config.DATA.mkdir(parents=True, exist_ok=True)
        (config.DATA / "fortuna_nesparovane.json").write_text(json.dumps(seznam, ensure_ascii=False, indent=1), encoding="utf-8")
    except OSError:
        return
    if seznam:
        log(f"ℹ️ Nespárováno {len(seznam)} TOP ligových zápasů (např. {seznam[0]['home']} - {seznam[0]['away']}). Seznam: data/fortuna_nesparovane.json, aliasy: data/aliasy_tymu.json.")


def pasmo(fh, trh, kmin, kmax):
    """Kurzové pásmo pro daný typ trhu (sporty.yaml: fortuna.pasma), jinak obecné."""
    b = (fh.get("pasma") or {}).get(trh)
    return (float(b[0]), float(b[1])) if b else (kmin, kmax)


def _protistrana(n):
    return {"over": "under", "under": "over", "ano": "ne", "ne": "ano"}.get(n)


def _text(n, z=None):
    if n["trh"] == "df_kdo":
        return f"Více dvojchyb zahraje: {n.get('hrac')}"
    if n["trh"] in ("esa_hrac", "df_hrac"):
        kdo = n.get("hrac")
        if not kdo and z and n.get("pozice") in ("1", "2"):
            kdo = z["home"] if n["pozice"] == "1" else z["away"]
        return f"{'Esa' if n['trh'] == 'esa_hrac' else 'Dvojchyby'} hráče {kdo or '?'}: {'více než' if n['strana'] == 'over' else 'méně než'} {n['linie']}"
    if n["trh"] == "btts":
        return f"Oba dají gól: {'ANO' if n['strana'] == 'ano' else 'NE'}"
    return f"{NAZEV.get(n['trh'], n['trh'])}: {'více než' if n['strana'] == 'over' else 'méně než'} {n['linie']}"


def vyhodnot(zapasy, cfg, ted, log=print, nacti_model=None):
    """zapasy = výstup fortuna.nabidka(). -> seznam kandidátů seřazený podle hrany."""
    nast = cfg.get("doplnkove") or {}
    fh = cfg.get("fortuna") or {}
    w = float(fh.get("vaha_modelu", 0.5))
    min_edge = float(fh.get("min_edge", 0.03))
    kmin0, kmax0 = float(fh.get("min_kurz", 1.50)), float(fh.get("max_kurz", 4.50))
    max_rozchod = float(fh.get("max_rozchod", 0.12))
    from .fortuna import je_virtualni
    fotbal = [z for z in zapasy if z.get("sport") == "fotbal" and z.get("nohy") and not je_virtualni(z)]
    if not fotbal:
        log("Fortuna: v nabídce není žádný fotbal s trhy.")
        return []

    global _ALIASY
    _ALIASY = nacti_aliasy()
    modely, radky = {}, {}
    nesparovane = []

    def model_ligy(kod):
        if kod not in modely:
            rows = histdata.nacti_ligu(kod, ted, 2, int(fh.get("cervena_karta_jako", 0))) if nacti_model is None else nacti_model(kod)   # Fortuna počítá jen žluté karty
            m = dp.fit(rows, ted, nast) if rows else None
            tymy = sorted({r["home"] for r in rows} | {r["away"] for r in rows}) if rows else []
            modely[kod] = (m if m and m["vars"] else None, {t: histdata._norm(t) for t in tymy})
            radky[kod] = rows
        return modely[kod]

    out, spar = [], 0
    for z in fotbal:
        nalezeno = None
        znama = kod_ligy(z.get("turnaj"))
        if znama is None and (je_zena_ml(z.get("turnaj")) or not fortuna_top(z)):
            continue                                       # ženy/mládež/nižší soutěže bez dat: nehádat v cizích ligách
        for kod in ([znama] if znama else sorted(set(histdata.LIGY.values()))):   # liga z názvu turnaje; poháry zkusí všechny
            m, tymy = model_ligy(kod)
            if not m:
                continue
            h, a = _par(z["home"], tymy, bool(znama)), _par(z["away"], tymy, bool(znama))
            if h and a and h != a:
                nalezeno = (kod, m, h, a)
                break
        if not nalezeno:
            if fortuna_top(z):
                nesparovane.append({"turnaj": z.get("turnaj"), "home": z["home"], "away": z["away"]})
            continue
        spar += 1
        kod, m, h, a = nalezeno
        podle = defaultdict(dict)
        for n in z["nohy"]:
            podle[(n["trh"], n.get("linie"))][n["strana"]] = n
        for (trh, L), strany in podle.items():
            for st, n in strany.items():
                kmin, kmax = pasmo(fh, n["trh"], kmin0, kmax0)
                if not (kmin <= n["kurz"] <= kmax):
                    continue
                pm = p_nohy(m, h, a, n)
                if pm is None:
                    continue
                opak = strany.get(_protistrana(st))
                if opak:                                   # férová p. samotného trhu (dvoucestný)
                    ptrh = engine.no_vig_power([n["kurz"], opak["kurz"]])[0]
                    if abs(pm - ptrh) > max_rozchod:
                        continue                           # model se s trhem rozchází příliš -> něco model neví
                    p = w * pm + (1 - w) * ptrh
                else:
                    continue                               # bez protistrany nelze odhadnout maržu -> přeskočit
                edge = n["kurz"] * p - 1
                if edge < min_edge:
                    continue
                out.append({"zapas": z["nazev"], "zapas_id": z.get("id"), "sport": "fotbal", "home_fd": h, "away_fd": a,
                            "noha_klic": klic_nohy(n), "home": z["home"], "away": z["away"], "start": z["start"],
                            "liga": z["turnaj"], "kod": kod, "trh": _text(n), "typ": n["trh"], "linie": L,
                            "strana": st, "kurz_fortuna": n["kurz"], "p_model": round(pm, 4),
                            "p_trh": round(ptrh, 4), "p": round(p, 4), "edge": round(edge, 4),
                            "sazej_od": math.ceil((1 + min_edge) / p * 100) / 100,
                            "fair": round(1 / p, 2), "mu": _mu(m, h, a),
                            "data": kontext_dat(radky.get(kod) or [], h, a, ted)})
    log(f"Fortuna: spárováno {spar}/{len(fotbal)} fotbalových zápasů s historií, kandidátů s hranou: {len(out)}.")
    _uloz_nesparovane(nesparovane, log)
    out.sort(key=lambda x: -x["edge"])
    return out[: int(fh.get("max_tipu", 10))]


def _mu(m, h, a):
    mm = dp.mu_tymu(m["var"]["goly"], h, a, "goly") if "goly" in m["var"] else None
    return [round(mm[0], 2), round(mm[1], 2)] if mm else None


def _prum(xs):
    return round(sum(xs) / len(xs), 2) if xs else None


def _tym(rows, t, n=10):
    """Průměry týmu z posledních n zápasů: góly, rohy, fauly, žluté (pro a proti) + poslední výsledky."""
    mine = [r for r in rows if t in (r["home"], r["away"])][-n:]
    out = {"zapasu": len(mine), "posledni": []}
    for v, nm in (("goly", "goly"), ("rohy", "rohy"), ("fauly", "fauly"), ("karty", "zlute")):
        pro, proti = [], []
        for r in mine:
            if v not in r["y"]:
                continue
            h, a = r["y"][v]
            pro.append(h if r["home"] == t else a)
            proti.append(a if r["home"] == t else h)
        out[nm + "_pro"], out[nm + "_proti"] = _prum(pro), _prum(proti)
    for r in mine[-5:]:
        dom = r["home"] == t
        g = r["y"]["goly"]
        out["posledni"].append(f"{r['datum']:%d.%m.} {'D' if dom else 'V'} {r['away'] if dom else r['home']} {g[0] if dom else g[1]}:{g[1] if dom else g[0]}")
    return out


def kontext_dat(rows, h, a, ted):
    """Spočítaná fakta z historie (football-data): týmy, liga, rozhodčí v lize, vzájemné zápasy."""
    if not rows:
        return {}
    liga = {}
    for v in ("goly", "rohy", "fauly", "karty"):
        s = [sum(r["y"][v]) for r in rows if v in r["y"]]
        liga[v] = _prum(s)
    ref = defaultdict(lambda: defaultdict(list))
    for r in rows:
        if not r.get("ref"):
            continue
        for v in ("karty", "fauly", "rohy"):
            if v in r["y"]:
                ref[r["ref"]][v].append(sum(r["y"][v]))
    tab = sorted(({"jmeno": k, "zapasu": len(d["karty"] or d["fauly"]), "zlute": _prum(d["karty"]),
                   "fauly": _prum(d["fauly"]), "rohy": _prum(d["rohy"])}
                  for k, d in ref.items() if len(d["karty"] or d["fauly"]) >= 5), key=lambda x: -x["zapasu"])[:25]
    vz = [r for r in rows if {r["home"], r["away"]} == {h, a}][-5:]
    return {"liga_prumer_na_zapas": liga, "domaci": _tym(rows, h), "hoste": _tym(rows, a),
            "rozhodci_v_lize": tab,
            "vzajemne": [f"{r['datum']:%d.%m.%Y} {r['home']} {r['y']['goly'][0]}:{r['y']['goly'][1]}"
                         + (f", žluté {sum(r['y']['karty'])}" if "karty" in r["y"] else "")
                         + (f", fauly {sum(r['y']['fauly'])}" if "fauly" in r["y"] else "")
                         + (f", rohy {sum(r['y']['rohy'])}" if "rohy" in r["y"] else "") for r in vz]}


TENIS_TRHY = ("esa", "esa_hrac", "df", "df_hrac", "df_kdo")
_STAT = {"esa": "ace", "esa_hrac": "ace", "df": "df", "df_hrac": "df"}


def vyhodnot_tenis(zapasy, cfg, ted, log=print, nacti_data=None):
    """Tenis: esa a dvojchyby (v zápase / hráče / kdo jich zahraje víc). Model ze Sackmannových dat smíchaný s férovým trhem.
    nacti_data(ted) -> řádky zápasů (pro testy). Bez dat nebo bez protistrany linie se nic nevrací."""
    from . import tenis
    fh = cfg.get("fortuna") or {}
    w = float(fh.get("vaha_modelu", 0.5))
    min_edge = float(fh.get("min_edge", 0.03))
    kmin0, kmax0 = float(fh.get("min_kurz", 1.50)), float(fh.get("max_kurz", 4.50))
    max_rozchod = float(fh.get("max_rozchod", 0.12))
    from .fortuna import je_virtualni
    zap = [z for z in zapasy if z.get("sport") in ("tenis", "tennis") and z.get("nohy") and not je_virtualni(z)
           and any(n["trh"] in TENIS_TRHY for n in z["nohy"])]
    if not zap:
        log("Fortuna/tenis: v nabídce není žádný zápas s trhem es/dvojchyb (názvy trhů zkontroluj v fortuna_probe).")
        return []
    try:
        rows = (nacti_data or tenis.nacti)(ted)
    except Exception as e:                                                        # síť/formát dat nesmí shodit report
        log(f"⚠️ Tenisová data nejdou načíst: {type(e).__name__}: {e}")
        return []
    modely = {"ace": tenis.fit(rows, ted, stat="ace") if rows else None, "df": tenis.fit(rows, ted, stat="df") if rows else None}
    if not modely["ace"]:
        log("⚠️ Tenis: málo dat pro model.")
        return []
    ref = modely["ace"]
    out, spar = [], 0
    for z in zap:
        if not (z.get("home") and z.get("away")):
            continue
        a, b = tenis.najdi_hrace(z["home"], ref["hraci"]), tenis.najdi_hrace(z["away"], ref["hraci"])
        if not a or not b or a == b:
            continue
        povrch = tenis.povrch_z_turnaje(ref, f"{z.get('turnaj', '')} {z.get('turnaj_popis', '')}")
        bo = 5 if "grand slam" in f"{z.get('turnaj', '')}".lower() else 3
        spar += 1
        podle = defaultdict(dict)
        for n in z["nohy"]:
            if n["trh"] in _STAT:
                podle[(n["trh"], n.get("hrac") or n.get("pozice"), n["linie"])][n["strana"]] = n
        dvojice = []                                           # (noha, protistrana, p_model, mu, hrac_fd)
        for (trh, _k, L), strany in podle.items():
            m = modely[_STAT[trh]]
            if not m:
                continue
            for st, n in strany.items():
                opak = strany.get(_protistrana(st))
                r = tenis.p_nohy(m, n, z["home"], z["away"], povrch, bo) if opak else None
                if r:
                    dvojice.append((n, opak, r["p"], r["mu"], r.get("hrac_fd"), m))
        kdo = [n for n in z["nohy"] if n["trh"] == "df_kdo"]
        if len(kdo) == 2 and modely["df"]:                     # kdo zahraje víc dvojchyb (dvoucestný, bez remízy)
            r = tenis.p_kdo_vice(modely["df"], z["home"], z["away"], povrch, bo)
            if r:
                tie = kdo[0].get("remiza")
                for n, o in ((kdo[0], kdo[1]), (kdo[1], kdo[0])):
                    jm = tenis.najdi_hrace(n["hrac"], ref["hraci"]) or tenis._podle_prijmeni(n["hrac"], r["hraci"])
                    if jm in r["hraci"]:
                        dom = jm == r["hraci"][0]
                        if tie:                                # třícestný trh: remíza sázku prohrává -> absolutní p a férový trh ze 3 kurzů
                            dvojice.append((n, {**o, "_tie": tie}, r["p_home_abs"] if dom else r["p_away_abs"], r["mu"], jm, modely["df"]))
                        else:
                            dvojice.append((n, o, r["p_home"] if dom else r["p_away"], r["mu"], jm, modely["df"]))
        for n, opak, pm, mu_, hrac_fd, m in dvojice:
            kmin, kmax = pasmo(fh, "esa" if n["trh"].startswith("esa") else "df", kmin0, kmax0)
            if not (kmin <= n["kurz"] <= kmax):
                continue
            ptrh = engine.no_vig_power([n["kurz"], opak["kurz"]] + ([opak["_tie"]] if opak.get("_tie") else []))[0]
            if abs(pm - ptrh) > max_rozchod:
                continue
            p = w * pm + (1 - w) * ptrh
            edge = n["kurz"] * p - 1
            if edge < min_edge:
                continue
            out.append({"zapas": z["nazev"], "zapas_id": z.get("id"), "sport": "tenis", "home": z["home"], "away": z["away"],
                        "home_fd": a, "away_fd": b, "hrac_fd": hrac_fd, "noha_klic": klic_nohy(n), "start": z["start"], "liga": z["turnaj"],
                        "kod": "tenis", "trh": _text(n, z), "typ": n["trh"], "linie": n.get("linie"), "strana": n["strana"],
                        "kurz_fortuna": n["kurz"], "p_model": round(pm, 4), "p_trh": round(ptrh, 4), "p": round(p, 4),
                        "edge": round(edge, 4), "sazej_od": math.ceil((1 + min_edge) / p * 100) / 100,
                        "fair": round(1 / p, 2), "mu": mu_,
                        "data": {"model": f"{m['stat']}: síla podání × odolnost returnu × počet podání, negativní binomické rozdělení",
                                 "povrch": povrch or "neznámý", "bo": bo, "hraci_v_datech": [a, b],
                                 "zapasu_v_datech": [m["n"].get(a), m["n"].get(b)],
                                 "sila_podani": [round(m["s"].get(a, 1), 2), round(m["s"].get(b, 1), 2)],
                                 "odolnost_returnu": [round(m["r"].get(a, 1), 2), round(m["r"].get(b, 1), 2)],
                                 "poznamka": "povrch odhadnut z názvu turnaje; pokud je 'neznámý', model použil průměr všech povrchů"}})
    log(f"Fortuna/tenis: spárováno {spar}/{len(zap)} zápasů s daty, kandidátů s hranou: {len(out)}.")
    out.sort(key=lambda x: -x["edge"])
    return out[: int(fh.get("max_tipu", 10))]
