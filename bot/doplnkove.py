"""Doplňkové trhy ve fotbale: góly, rohy, karty, fauly (celkové počty) + bet buildery.

Princip (odlišný od h2h): tady NENÍ ostrá referenční cena, takže pravděpodobnost počítá vlastní model:
  1. tým-specifické míry (produkce/obdržené) se smršťují k průměru ligy (shrinkage) a stárnou (poločas)
  2. rozhodčí upravuje karty a fauly (smrštěný faktor, jen když je rozhodčí znám)
  3. počet ~ negativní binomické rozdělení (disperze odhadnuta z reziduí)
  4. bet builder = společné rozdělení více trhů přes Gaussovu kopuli (korelace z reziduí historie)
Model NENÍ zaručeně lepší než trh. Proto: backtest proti naivnímu základu, kalibrační log
a vyšší práh hrany. Bez kurzů kanceláře bot dává "fér kurz" a "sázej od".
"""
import csv
import datetime
import json
import math
import os
from collections import defaultdict

import numpy as np

from . import config

PROMENNE = ("goly", "rohy", "karty", "fauly")
S_ROZHODCIM = {"karty", "fauly"}
NAZVY = {"goly": "Góly", "rohy": "Rohy", "karty": "Karty", "fauly": "Fauly"}
_erf = np.vectorize(math.erf)


# ------------------------------------------------------------ rozdělení
def pmf_nb(mu, r, ymax):
    mu = max(mu, 1e-9)
    out = []
    if r >= 1e5:                                   # prakticky Poisson
        for y in range(ymax + 1):
            out.append(math.exp(y * math.log(mu) - mu - math.lgamma(y + 1)))
    else:
        p = r / (r + mu)
        lp, lq = math.log(p), math.log1p(-p)
        for y in range(ymax + 1):
            out.append(math.exp(math.lgamma(y + r) - math.lgamma(r) - math.lgamma(y + 1)
                                + r * lp + y * lq))
    return np.array(out)


def cdf_tabulka(mu, r):
    var = mu + (mu * mu / r if r < 1e5 else 0.0)
    ymax = int(mu + 12 * math.sqrt(var) + 12)
    c = np.cumsum(pmf_nb(mu, r, ymax))
    c[-1] = 1.0
    return c


def p_over_linie(mu, r, linie):
    """{linie: P(počet > linie)} pro půlkové linie (x.5)."""
    c = cdf_tabulka(mu, r)
    return {L: float(1.0 - c[int(math.floor(L))]) if int(math.floor(L)) < len(c) else 0.0
            for L in linie}


# ------------------------------------------------------------ model
def eb_k(gruppy, lo, hi):
    """Empirické Bayes: kolik 'pseudo-zápasů' průměru přidat, aby se šum nehonil.
    k = rozptyl uvnitř skupiny / rozptyl mezi skupinami (po odečtení šumu). Žádný signál -> k = hi."""
    skupiny = {t: v for t, v in gruppy.items() if v}
    T = len(skupiny)
    n_tot = sum(len(v) for v in skupiny.values())
    if T < 3 or n_tot - T < 10:
        return hi
    mean_t = {t: sum(v) / len(v) for t, v in skupiny.items()}
    sw2 = sum(sum((x - mean_t[t]) ** 2 for x in v) for t, v in skupiny.items()) / (n_tot - T)
    sumum = sum(sw2 / len(v) for v in skupiny.values()) / T
    mu = sum(mean_t.values()) / T
    sb2 = sum((m - mu) ** 2 for m in mean_t.values()) / (T - 1)
    tau2 = sb2 - sumum
    if tau2 <= 1e-6:
        return hi
    return float(min(max(sw2 / tau2, lo), hi))


def predikuj(m, h, a, ref, v):
    """Očekávaný CELKOVÝ počet v zápase, nebo None (neznámý tým / málo dat)."""
    if h not in m["att"] or a not in m["att"]:
        return None
    if m["pocet"].get(h, 0) < m["min_tym"] or m["pocet"].get(a, 0) < m["min_tym"]:
        return None
    mu = (m["mh"] * m["att"][h] * m["def"][a] + m["ma"] * m["att"][a] * m["def"][h])
    if v in S_ROZHODCIM and ref and ref in m["ref"]:
        mu *= m["ref"][ref]
    return mu


def _psd(R):
    w, V = np.linalg.eigh(R)
    R2 = V @ np.diag(np.clip(w, 1e-6, None)) @ V.T
    d = np.sqrt(np.diag(R2))
    return R2 / np.outer(d, d)


def fit(rows, ted, nast):
    """Naučí model ze zápasů před `ted`. -> {"var": {...}, "vars": [...], "R": matice}"""
    lo, hi, pul = nast["shrinkage_min"], nast["shrinkage_max"], nast["pulcas_dny"]
    model, zs = {}, {}
    for v in PROMENNE:
        data = [r for r in rows if v in r["y"] and r["datum"] < ted]
        if len(data) < nast["min_zapasu_historie"]:
            continue
        w = [0.5 ** (max((ted - r["datum"]).days, 0) / pul) for r in data]
        sw = sum(w)
        mh = sum(wi * r["y"][v][0] for wi, r in zip(w, data)) / sw
        ma = sum(wi * r["y"][v][1] for wi, r in zip(w, data)) / sw
        if mh <= 0 or ma <= 0:
            continue
        prod, conc, ws, cnt = (defaultdict(float) for _ in range(4))
        sk_prod, sk_conc = defaultdict(list), defaultdict(list)
        for wi, r in zip(w, data):
            yh, ya = r["y"][v]
            h, a = r["home"], r["away"]
            prod[h] += wi * yh / mh; conc[h] += wi * ya / ma; ws[h] += wi; cnt[h] += 1
            prod[a] += wi * ya / ma; conc[a] += wi * yh / mh; ws[a] += wi; cnt[a] += 1
            sk_prod[h].append(yh / mh); sk_conc[h].append(ya / ma)
            sk_prod[a].append(ya / ma); sk_conc[a].append(yh / mh)
        k_att, k_def = eb_k(sk_prod, lo, hi), eb_k(sk_conc, lo, hi)
        m = {"mh": mh, "ma": ma, "mu_liga": mh + ma, "ref": {}, "ref_n": {},
             "att": {t: (prod[t] + k_att) / (ws[t] + k_att) for t in ws},
             "def": {t: (conc[t] + k_def) / (ws[t] + k_def) for t in ws},
             "k_att": round(k_att, 1), "k_def": round(k_def, 1),
             "pocet": dict(cnt), "min_tym": nast["min_zapasu_tym"], "r": 1e6}
        if v in S_ROZHODCIM:
            sr, wr, sk_ref = defaultdict(float), defaultdict(float), defaultdict(list)
            for wi, r in zip(w, data):
                if not r.get("ref"):
                    continue
                e = (mh * m["att"][r["home"]] * m["def"][r["away"]]
                     + ma * m["att"][r["away"]] * m["def"][r["home"]])
                if e > 0:
                    sr[r["ref"]] += wi * sum(r["y"][v]) / e
                    wr[r["ref"]] += wi
                    sk_ref[r["ref"]].append(sum(r["y"][v]) / e)
            kr = eb_k(sk_ref, lo, hi)
            m["k_ref"] = round(kr, 1)
            m["ref"] = {x: (sr[x] + kr) / (wr[x] + kr) for x in wr}     # smrštěno k 1.0
            m["ref_n"] = dict(wr)
        # disperze z reziduí (metoda momentů): Var = mu + mu^2/r
        mus = [predikuj({**m, "min_tym": 0}, r["home"], r["away"], r.get("ref"), v) for r in data]
        ys = [sum(r["y"][v]) for r in data]
        num = sum(mu * mu for mu in mus)
        den = sum((y - mu) ** 2 - mu for y, mu in zip(ys, mus))
        m["r"] = float(min(max(num / den, 2.0), 1e6)) if den > 0 else 1e6
        zs[v] = {(r["datum"], r["home"], r["away"]): (y - mu) / math.sqrt(mu + mu * mu / m["r"])
                 for r, y, mu in zip(data, ys, mus)}
        model[v] = m
    vars_ = [v for v in PROMENNE if v in model]
    R = np.eye(len(vars_))
    if len(vars_) >= 2:
        spolecne = set.intersection(*(set(zs[v]) for v in vars_))
        if len(spolecne) >= 50:
            M = np.array([[zs[v][key] for key in spolecne] for v in vars_])
            R = _psd(np.corrcoef(M))
    return {"var": model, "vars": vars_, "R": R}


# ------------------------------------------------------------ simulace a builder
def simuluj(model, mus, n, seed=12345):
    """Společná simulace trhů přes Gaussovu kopuli -> {var: pole počtů}."""
    vars_ = [v for v in model["vars"] if v in mus]
    idx = [model["vars"].index(v) for v in vars_]
    R = model["R"][np.ix_(idx, idx)]
    rng = np.random.default_rng(seed)
    z = rng.standard_normal((n, len(vars_))) @ np.linalg.cholesky(R).T
    u = 0.5 * (1.0 + _erf(z / math.sqrt(2.0)))
    out = {}
    for j, v in enumerate(vars_):
        c = cdf_tabulka(mus[v], model["var"][v]["r"])
        out[v] = np.minimum(np.searchsorted(c, u[:, j], side="left"), len(c) - 1)
    return out


def noha(sim, v, linie, strana):
    return sim[v] > linie if strana == "over" else sim[v] < linie


def cena_builderu(sim, nohy):
    """nohy = [(var, linie, strana)] -> (spolecna_p, soucin_marginalu)"""
    vec = None
    soucin = 1.0
    for v, L, s in nohy:
        x = noha(sim, v, L, s)
        soucin *= float(x.mean())
        vec = x if vec is None else (vec & x)
    return float(vec.mean()), soucin


# ------------------------------------------------------------ analýza zápasu
def analyzuj_zapas(model, h, a, ref, nast, seed=12345):
    mus = {}
    for v in model["vars"]:
        mu = predikuj(model["var"][v], h, a, ref, v)
        if mu is None:
            return None
        mus[v] = mu
    if not mus:
        return None
    me = nast["min_edge"]
    linie = []
    for v, mu in mus.items():
        po = p_over_linie(mu, model["var"][v]["r"], nast["linie"][v])
        for L, p_o in po.items():
            for strana, p in (("over", p_o), ("under", 1.0 - p_o)):
                if p <= 0.05:
                    continue
                fair = 1.0 / p
                mk = round(fair * (1 + me), 2)
                if nast["min_kurz"] <= mk <= nast["max_kurz"]:
                    linie.append({"var": v, "linie": L, "strana": strana, "p": round(p, 4),
                                  "fair": round(fair, 2), "min_kurz": mk})
    sim = simuluj(model, mus, nast["simulace"], seed)
    nohy = []
    for v in mus:
        for L in nast["linie"][v]:
            for strana in ("over", "under"):
                p = float(noha(sim, v, L, strana).mean())
                if nast["builder_leg_min_p"] <= p <= nast["builder_leg_max_p"]:
                    nohy.append((v, L, strana, p))
    kombinace = []
    for i in range(len(nohy)):
        for j in range(i + 1, len(nohy)):
            (v1, L1, s1, p1), (v2, L2, s2, p2) = nohy[i], nohy[j]
            if v1 == v2:
                continue
            joint, soucin = cena_builderu(sim, [(v1, L1, s1), (v2, L2, s2)])
            if joint < nast["builder_min_p"]:
                continue
            fair = 1.0 / joint
            if nast["builder_min_kurz"] <= fair <= nast["builder_max_kurz"]:
                kombinace.append({"nohy": [(v1, L1, s1), (v2, L2, s2)], "p": round(joint, 4),
                                  "fair": round(fair, 2), "min_kurz": round(fair * (1 + me), 2),
                                  "korelace": round(joint / soucin, 3) if soucin else 1.0})
    kombinace.sort(key=lambda c: -c["korelace"])
    signal = max(abs(mus[v] / model["var"][v]["mu_liga"] - 1) for v in mus)
    ref_zn = bool(ref) and any(ref in model["var"][v]["ref"] for v in S_ROZHODCIM if v in model["var"])
    return {"mu": {v: round(x, 2) for v, x in mus.items()},
            "liga_prumer": {v: round(model["var"][v]["mu_liga"], 2) for v in mus},
            "linie": sorted(linie, key=lambda x: (x["var"], x["linie"], x["strana"])),
            "builder": kombinace[:nast["builder_max_kandidatu"]],
            "signal": round(signal, 3), "rozhodci": ref if ref_zn else ""}


# ------------------------------------------------------------ backtest
def backtest(rows, nast, od, obnov_dny=7):
    """Walk-forward: pro každý zápas po `od` model naučený jen z minulosti vs. naivní průměr ligy.
    Výsledek: {promenna: {n, logloss_model, logloss_zaklad, zlepseni_pct}}; kladné zlepšení = model je lepší."""
    acc = defaultdict(lambda: [0, 0.0, 0.0])
    model, kdy = None, None
    for r in (x for x in rows if x["datum"] >= od):
        if model is None or (r["datum"] - kdy).days >= obnov_dny:
            model, kdy = fit(rows, r["datum"], nast), r["datum"]
        for v in model["vars"]:
            if v not in r["y"]:
                continue
            m = model["var"][v]
            mu = predikuj(m, r["home"], r["away"], r.get("ref"), v)
            if mu is None:
                continue
            y = sum(r["y"][v])
            pm = p_over_linie(mu, m["r"], nast["linie"][v])
            pb = p_over_linie(m["mu_liga"], m["r"], nast["linie"][v])
            for L in nast["linie"][v]:
                hit = y > L
                for p, idx in ((pm[L], 1), (pb[L], 2)):
                    p = min(max(p, 1e-4), 1 - 1e-4)
                    acc[v][idx] += -math.log(p if hit else 1 - p)
                acc[v][0] += 1
    out = {}
    for v, (n, lm, lb) in acc.items():
        out[v] = {"n": n, "logloss_model": round(lm / n, 4), "logloss_zaklad": round(lb / n, 4),
                  "zlepseni_pct": round(100 * (lb - lm) / lb, 2)}
    return out

# ------------------------------------------------------------ kalibrační log
POLE_LOG = ["id", "datum", "kod", "home_fd", "away_fd", "zapas", "var", "linie", "strana",
            "p", "fair", "min_kurz", "vysledek"]


def _cesta_log():
    return config.DATA / "doplnkove.csv"


def nacti_log():
    if not _cesta_log().exists():
        return []
    with open(_cesta_log(), encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))


def uloz_log(rows):
    config.DATA.mkdir(parents=True, exist_ok=True)
    tmp = str(_cesta_log()) + ".tmp"
    with open(tmp, "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=POLE_LOG, extrasaction="ignore")
        w.writeheader()
        for r in rows:
            w.writerow({k: r.get(k, "") for k in POLE_LOG})
    os.replace(tmp, _cesta_log())


def zaloguj_predikce(zapasy, datum):
    rows = nacti_log()
    mam = {r["id"] for r in rows}
    nove = []
    for z in zapasy:
        for l in z["linie"]:
            rid = f"{datum}|{z['home_fd']}|{z['away_fd']}|{l['var']}|{l['linie']}|{l['strana']}"
            if rid not in mam:
                nove.append({"id": rid, "datum": datum, "kod": z["kod"], "home_fd": z["home_fd"],
                             "away_fd": z["away_fd"], "zapas": z["zapas"], "var": l["var"],
                             "linie": l["linie"], "strana": l["strana"], "p": l["p"],
                             "fair": l["fair"], "min_kurz": l["min_kurz"], "vysledek": ""})
    uloz_log(rows + nove)
    return len(nove)


def vyhodnot_log(nacti_historii, ted):
    """Doplní skutečný výsledek (1 = sázka by vyšla). nacti_historii(kod) -> řádky zápasů."""
    rows = nacti_log()
    cekajici = [r for r in rows if r["vysledek"] == "" and r["datum"] < ted.strftime("%Y-%m-%d")]
    if not cekajici:
        return 0
    cache, hotovo = {}, 0
    for r in cekajici:
        if r["kod"] not in cache:
            cache[r["kod"]] = nacti_historii(r["kod"])
        d0 = datetime.datetime.strptime(r["datum"], "%Y-%m-%d").replace(tzinfo=datetime.timezone.utc)
        for z in cache[r["kod"]]:
            if (z["home"], z["away"]) == (r["home_fd"], r["away_fd"]) and abs((z["datum"] - d0).days) <= 1:
                if r["var"] in z["y"]:
                    y = sum(z["y"][r["var"]])
                    L = float(r["linie"])
                    r["vysledek"] = str(int((y > L) if r["strana"] == "over" else (y < L)))
                    hotovo += 1
                break
    uloz_log(rows)
    return hotovo


def kalibrace(rows):
    """Kalibrace předpovědí: v pásmu predikované p by měla skutečná frekvence sedět na p."""
    r = [x for x in rows if x["vysledek"] in ("0", "1")]
    if not r:
        return {"n": 0}
    pasma = [(0.5, 0.6), (0.6, 0.7), (0.7, 0.8), (0.8, 1.01)]
    out = {"n": len(r), "brier": round(sum((float(x["p"]) - int(x["vysledek"])) ** 2 for x in r) / len(r), 4),
           "pasma": []}
    for lo, hi in pasma:
        b = [x for x in r if lo <= float(x["p"]) < hi]
        if b:
            out["pasma"].append({"pasmo": f"{int(lo * 100)}-{min(int(hi * 100), 100)} %", "n": len(b),
                                 "predikovano": round(sum(float(x["p"]) for x in b) / len(b), 3),
                                 "skutecne": round(sum(int(x["vysledek"]) for x in b) / len(b), 3)})
    return out


# ------------------------------------------------------------ rozhodčí (ručně doplněná data)
def nacti_rozhodci():
    """data/rozhodci.json: {"RRRR-MM-DD|Domácí|Hosté": "Jméno rozhodčího"} (jména jako ve football-data)."""
    p = config.DATA / "rozhodci.json"
    if p.exists():
        try:
            return json.loads(p.read_text(encoding="utf-8"))
        except ValueError:
            return {}
    return {}
