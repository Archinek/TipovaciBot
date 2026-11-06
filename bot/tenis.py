"""Tenis: model počtu es (celkem v zápase i jednotlivého hráče) z volných dat Jeffa Sackmanna.

Proč esa: největší tipér v žebříčku (borunja, ROI ~15 %) hraje hlavně "Počet es v zápasu" a "Počet es hráče".
Esa jsou čistě statistický trh: záleží na hráčově podání, na tom, jak soupeř returnuje, na povrchu
a na délce zápasu (best of 3/5). Bookmaker to ceňuje hrubě a hráč, který posílá esa, se často ocení pozdě.

Model (záměrně jednoduchý a vysvětlitelný):
  očekávaná esa A = počet podání A × ligová míra es na povrchu × síla podání A × odolnost returnu B
  síla podání a odolnost returnu se učí střídavě (jako attack/defence), s empirickým smrštěním k průměru
  a časovým útlumem (poločas 1 rok). Počet es je negativně binomický (rozptyl z reziduí).
Zdroj dat: https://github.com/JeffSackmann/tennis_atp a tennis_wta (CSV, w_ace/l_ace/w_svpt/l_svpt, povrch).
"""
import csv
import datetime
import io
import math
import re
import time
import unicodedata
import urllib.error
import urllib.request
from collections import defaultdict

from . import config

ZDROJE = [
    "https://raw.githubusercontent.com/JeffSackmann/tennis_atp/master/atp_matches_{rok}.csv",
    "https://raw.githubusercontent.com/JeffSackmann/tennis_atp/master/atp_matches_qual_chall_{rok}.csv",
    "https://raw.githubusercontent.com/JeffSackmann/tennis_wta/master/wta_matches_{rok}.csv",
]


# ------------------------------------------------------------ načtení dat
def _cislo(x):
    try:
        v = float(x)
        return v if v >= 0 else None
    except (TypeError, ValueError):
        return None


def parsuj(text):
    """CSV text -> zápasy se statistikou podání. Zápasy bez w_ace/l_ace/svpt se zahazují."""
    out = []
    for r in csv.DictReader(io.StringIO(text)):
        try:
            d = datetime.datetime.strptime(r["tourney_date"], "%Y%m%d").replace(tzinfo=datetime.timezone.utc)
        except (KeyError, ValueError, TypeError):
            continue
        aw, al, sw, sl = (_cislo(r.get(k)) for k in ("w_ace", "l_ace", "w_svpt", "l_svpt"))
        if None in (aw, al, sw, sl) or sw < 20 or sl < 20:
            continue                       # retirement a chybějící statistiky
        out.append({"datum": d, "turnaj": (r.get("tourney_name") or "").strip(), "povrch": (r.get("surface") or "").strip().lower(),
                    "bo": int(_cislo(r.get("best_of")) or 3), "w": (r.get("winner_name") or "").strip(),
                    "l": (r.get("loser_name") or "").strip(), "ace_w": aw, "ace_l": al, "sv_w": sw, "sv_l": sl,
                    "df_w": _cislo(r.get("w_df")), "df_l": _cislo(r.get("l_df"))})
    return out


def stahni(url, max_stari_h=72):
    """CSV s cache v data/tenis/. Při chybě sítě použije cache, jinak None (soubor pro letošní rok nemusí existovat)."""
    cesta = config.DATA / "tenis" / url.rsplit("/", 1)[-1]
    if cesta.exists() and (time.time() - cesta.stat().st_mtime) < max_stari_h * 3600:
        return cesta.read_bytes().decode("utf-8-sig", errors="replace")
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "tipovaci-bot/1.0"})
        with urllib.request.urlopen(req, timeout=40) as r:
            raw = r.read()
        cesta.parent.mkdir(parents=True, exist_ok=True)
        cesta.write_bytes(raw)
        return raw.decode("utf-8-sig", errors="replace")
    except (urllib.error.URLError, OSError):
        return cesta.read_bytes().decode("utf-8-sig", errors="replace") if cesta.exists() else None


def nacti(ted, roky=2):
    rows = []
    for i in range(roky):
        for u in ZDROJE:
            t = stahni(u.format(rok=ted.year - i))
            if t:
                rows += parsuj(t)
    return sorted((r for r in rows if r["datum"] < ted), key=lambda x: x["datum"])


# ------------------------------------------------------------ jména
def _tokeny(jmeno):
    s = unicodedata.normalize("NFKD", jmeno or "").encode("ascii", "ignore").decode().lower()
    return [t for t in re.sub(r"[^a-z ]", " ", s.replace("-", " ")).split() if t]


def najdi_hrace(jmeno, hraci):
    """Přiřadí jméno z Fortuny ('Pieri Samuele', 'Samuele Pieri', 'S. Pieri') ke jménu v datech. None = nejednoznačné."""
    tok = _tokeny(jmeno)
    if not tok:
        return None
    mnoz = set(tok)
    shody = [h for h, hs in hraci.items() if hs == mnoz]
    if len(shody) == 1:
        return shody[0]
    if len(shody) > 1:
        return None
    # iniciála: poslední/první token jednopísmenný -> příjmení se musí shodovat a jméno začínat na iniciálu
    ini = [t for t in tok if len(t) == 1]
    prij = set(t for t in tok if len(t) > 1)
    if ini and prij:
        kand = [h for h, hs in hraci.items() if prij <= hs and any(t.startswith(ini[0]) for t in hs - prij)]
        if len(kand) == 1:
            return kand[0]
    return None


# ------------------------------------------------------------ model
def _nb_nad(mu, k, L):
    """P(X > L) pro negativně binomické rozdělení se střední hodnotou mu a parametrem k (rozptyl = mu + mu²/k)."""
    mu = max(mu, 1e-6)
    p = k / (k + mu)
    lp, lq = math.log(p), math.log1p(-p)
    c = 0.0
    for y in range(int(math.floor(L)) + 1):
        c += math.exp(math.lgamma(y + k) - math.lgamma(k) - math.lgamma(y + 1) + k * lp + y * lq)
    return max(0.0, min(1.0, 1.0 - c))


def fit(rows, ted, poloc_dny=365, k_prior=15.0, iter_=4, stat="ace"):
    """-> model {"g": ligová míra es na podání podle povrchu, "s": síla podání, "r": odolnost returnu,
    "sv": průměr podání na zápas, "k_hrac", "k_celkem"}."""
    kw, kl = ("ace_w", "ace_l") if stat == "ace" else ("df_w", "df_l")     # stat: "ace" nebo "df" (dvojchyby)
    rows = [r for r in rows if r.get(kw) is not None and r.get(kl) is not None]
    if len(rows) < 200:
        return None
    # pozorování: (podávající, přijímající, esa, podání, povrch, váha, bo)
    obs = []
    for r in rows:
        w = 0.5 ** (max((ted - r["datum"]).days, 0) / poloc_dny)
        obs.append((r["w"], r["l"], r[kw], r["sv_w"], r["povrch"], w, r["bo"]))
        obs.append((r["l"], r["w"], r[kl], r["sv_l"], r["povrch"], w, r["bo"]))
    pov = defaultdict(lambda: [0.0, 0.0])
    for p, o, a, sv, s, w, bo in obs:
        pov[s][0] += w * a
        pov[s][1] += w * sv
    celk = sum(v[0] for v in pov.values()) / max(sum(v[1] for v in pov.values()), 1e-9)
    g = {s: (v[0] / v[1] if v[1] > 500 else celk) for s, v in pov.items()}
    g[""] = celk
    sila, odol = defaultdict(lambda: 1.0), defaultdict(lambda: 1.0)
    for _ in range(iter_):
        nc, nd = defaultdict(float), defaultdict(float)
        rc, rd = defaultdict(float), defaultdict(float)
        for p, o, a, sv, s, w, bo in obs:
            e = sv * g.get(s, celk)
            nc[p] += w * a; nd[p] += w * e * odol[o]
            rc[o] += w * a; rd[o] += w * e * sila[p]
        sila = defaultdict(lambda: 1.0, {h: (nc[h] + k_prior) / (nd[h] + k_prior) for h in nc})
        odol = defaultdict(lambda: 1.0, {h: (rc[h] + k_prior) / (rd[h] + k_prior) for h in rc})
    # globální kalibrace: součin síla × odolnost má volný měřítkový stupeň volnosti -> srovnat celkový součet es s predikcí
    pred = sum(w * sv * g.get(s_, celk) * sila[p] * odol[o] for p, o, a, sv, s_, w, bo in obs)
    skut = sum(w * a for p, o, a, sv, s_, w, bo in obs)
    if pred > 0:
        f = skut / pred
        g = {k: v * f for k, v in g.items()}
        celk *= f
    sv_h, w_h = defaultdict(float), defaultdict(float)
    bo_sv = defaultdict(lambda: [0.0, 0.0])
    for p, o, a, sv, s, w, bo in obs:
        sv_h[p] += w * sv; w_h[p] += w
        bo_sv[bo][0] += w * sv; bo_sv[bo][1] += w
    sv_bo = {bo: v[0] / v[1] for bo, v in bo_sv.items()}
    n_zap = defaultdict(int)
    for r in rows:
        n_zap[r["w"]] += 1; n_zap[r["l"]] += 1
    m = {"stat": stat, "g": dict(g), "celk": celk, "s": dict(sila), "r": dict(odol), "sv_bo": sv_bo,
         "sv": {h: sv_h[h] / w_h[h] for h in w_h}, "w_h": dict(w_h), "n": dict(n_zap),
         "hraci": {h: set(_tokeny(h)) for h in n_zap}, "povrchy": {r["turnaj"]: r["povrch"] for r in rows}}
    # rozptyl: momentová metoda z reziduí (celkem i na hráče), k = sum(mu²) / sum((y-mu)²-mu)
    sk_h = [0.0, 0.0]; sk_c = [0.0, 0.0]
    for r in rows[-4000:]:
        a_mu = _mu_hrace(m, r["w"], r["l"], r["povrch"], r["bo"], r["sv_w"], r["sv_l"])
        b_mu = _mu_hrace(m, r["l"], r["w"], r["povrch"], r["bo"], r["sv_l"], r["sv_w"])
        for mu, y in ((a_mu, r[kw]), (b_mu, r[kl])):
            sk_h[0] += mu * mu; sk_h[1] += (y - mu) ** 2 - mu
        sk_c[0] += (a_mu + b_mu) ** 2; sk_c[1] += (r[kw] + r[kl] - a_mu - b_mu) ** 2 - (a_mu + b_mu)
    m["k_hrac"] = min(max(sk_h[0] / sk_h[1], 3.0), 300.0) if sk_h[1] > 1e-6 else 300.0
    m["k_celkem"] = min(max(sk_c[0] / sk_c[1], 3.0), 300.0) if sk_c[1] > 1e-6 else 300.0
    return m


def _mu_hrace(m, p, o, povrch, bo, sv_p, sv_o):
    return sv_p * m["g"].get(povrch, m["celk"]) * m["s"].get(p, 1.0) * m["r"].get(o, 1.0)


def _podani(m, h, bo):
    """Očekávaný počet podání hráče v zápase: průměr jeho vlastní hodnoty a ligového průměru pro bo3/bo5."""
    liga = m["sv_bo"].get(bo) or (sum(m["sv_bo"].values()) / len(m["sv_bo"]))
    n = m["n"].get(h, 0)
    vlastni = m["sv"].get(h, liga)
    vaha = n / (n + 10.0)
    return vaha * vlastni + (1 - vaha) * liga


def predikuj(m, a, b, povrch="", bo=3):
    """Očekávaná esa A, B a celkem; a, b = jména HRÁČŮ v datech. None = málo dat o hráči."""
    if m is None or a not in m["n"] or b not in m["n"] or min(m["n"][a], m["n"][b]) < 8:
        return None
    sv = (_podani(m, a, bo) + _podani(m, b, bo)) / 2          # délku zápasu určují oba hráči
    mu_a = _mu_hrace(m, a, b, povrch, bo, sv, sv)
    mu_b = _mu_hrace(m, b, a, povrch, bo, sv, sv)
    return {"a": mu_a, "b": mu_b, "celkem": mu_a + mu_b}


def povrch_z_turnaje(m, nazev):
    """Povrch odhadnutý podle názvu turnaje (klíčová slova, pak shoda se jmény turnajů v datech). '' = nevím."""
    t = (nazev or "").lower()
    for kw, p in (("antuk", "clay"), ("clay", "clay"), ("trav", "grass"), ("grass", "grass"), ("hala", "hard"), ("indoor", "hard")):
        if kw in t:
            return p
    tok = set(_tokeny(nazev))
    for jm, p in (m.get("povrchy") or {}).items():
        jt = set(_tokeny(jm))
        if jt and len(jt) >= 1 and jt <= tok and p:
            return p
    return ""


def p_nohy(m, noha, home, away, povrch="", bo=3):
    """P(noha vyjde) pro trh 'esa' (celkem) nebo 'esa_hrac' (jeden hráč; noha['hrac'] = jméno nebo 'pozice' 1/2)."""
    a = najdi_hrace(home, m["hraci"])
    b = najdi_hrace(away, m["hraci"])
    if not a or not b or a == b:
        return None
    mu = predikuj(m, a, b, povrch, bo)
    if not mu:
        return None
    L, st = noha["linie"], noha["strana"]
    kdo_jmeno = None
    if noha["trh"] in ("esa", "df"):
        p, k, mm = _nb_nad(mu["celkem"], m["k_celkem"], L), m["k_celkem"], mu["celkem"]
    elif noha["trh"] in ("esa_hrac", "df_hrac"):
        kdo = None
        if noha.get("pozice") in ("1", "2"):
            kdo = "a" if noha["pozice"] == "1" else "b"
        elif noha.get("hrac"):
            h = najdi_hrace(noha["hrac"], m["hraci"]) or _podle_prijmeni(noha["hrac"], (a, b))
            kdo = "a" if h == a else "b" if h == b else None
        if not kdo:
            return None
        mm = mu[kdo]
        kdo_jmeno = a if kdo == "a" else b
        p, k = _nb_nad(mm, m["k_hrac"], L), m["k_hrac"]
    else:
        return None
    return {"p": p if st == "over" else 1.0 - p, "mu": round(mm, 2), "k": round(k, 1), "povrch": povrch or "neznámý",
            "hraci": (a, b), "hrac_fd": kdo_jmeno}


def _podle_prijmeni(text, dvojice):
    t = set(_tokeny(text))
    kand = [h for h in dvojice if t and t <= set(_tokeny(h))]
    return kand[0] if len(kand) == 1 else None


def _nb_pmf(mu, k, y):
    mu = max(mu, 1e-6)
    p = k / (k + mu)
    return math.exp(math.lgamma(y + k) - math.lgamma(k) - math.lgamma(y + 1) + k * math.log(p) + y * math.log1p(-p))


def p_kdo_vice(m, home, away, povrch="", bo=3):
    """'Kdo zahraje více dvojchyb (bez remízy)': -> {'p_home', 'p_away', 'hraci'} nebo None. Remíza se vyloučí (trh ji vrací)."""
    a, b = najdi_hrace(home, m["hraci"]), najdi_hrace(away, m["hraci"])
    if not a or not b or a == b:
        return None
    mu = predikuj(m, a, b, povrch, bo)
    if not mu:
        return None
    ymax = int(max(mu["a"], mu["b"]) * 3 + 25)
    pa = [_nb_pmf(mu["a"], m["k_hrac"], y) for y in range(ymax + 1)]
    pb = [_nb_pmf(mu["b"], m["k_hrac"], y) for y in range(ymax + 1)]
    a_vic = sum(pa[i] * sum(pb[:i]) for i in range(ymax + 1))
    b_vic = sum(pb[i] * sum(pa[:i]) for i in range(ymax + 1))
    if a_vic + b_vic <= 0:
        return None
    return {"p_home": a_vic / (a_vic + b_vic), "p_away": b_vic / (a_vic + b_vic), "mu": (round(mu["a"], 2), round(mu["b"], 2)), "hraci": (a, b)}
