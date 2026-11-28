"""Kalibrace férové pravděpodobnosti trhu (Meta 3 – úprava modelu).

Z vyhodnocených dvoucestných příležitostí (over/under, ano/ne…) se po sportech odhadne logistická oprava  p' = sigmoid(a + b·logit(p)).
Měření (11/2026): trh je mírně „příliš krajní" (b ≈ 0,95–0,97), tj. favorité vyhrávají o něco méně a outsideři o něco víc, než ukazuje p.
Oprava se použije jen tehdy, když se osvědčí na novějších dnech, které se při odhadu nepoužily (holdout), a je dost dat.
Soubor data/kalibrace_p.json se přepočítává při každém ranním běhu (ucici.uloz_kalibraci); bez něj nebo bez ověření se p nemění.
"""
import json
import math
from collections import defaultdict

from . import config

MIN_PARU = 5000        # dvoucestných zápasů-trhů ve sportu
HOLDOUT_PODIL = 0.3    # poslední část dnů slouží jen k ověření
MAX_POSUN = 0.03       # oprava nikdy nezmění p o víc než 3 procentní body


def _logit(p):
    p = min(max(p, 1e-6), 1 - 1e-6)
    return math.log(p / (1 - p))


def _sig(z):
    return 1 / (1 + math.exp(-z))


def _ll(data, a, b):
    s = 0.0
    for x, y in data:
        q = min(max(_sig(a + b * x), 1e-6), 1 - 1e-6)
        s -= y * math.log(q) + (1 - y) * math.log(1 - q)
    return s / len(data)


def _fit(data, iteraci=40):
    a, b = 0.0, 1.0
    for _ in range(iteraci):
        ga = gb = haa = hab = hbb = 0.0
        for x, y in data:
            q = _sig(a + b * x)
            w = q * (1 - q)
            ga += y - q
            gb += (y - q) * x
            haa += w
            hab += w * x
            hbb += w * x * x
        det = haa * hbb - hab * hab + 1e-12
        da, db = (hbb * ga - hab * gb) / det, (haa * gb - hab * ga) / det
        a, b = a + da, b + db
        if abs(da) + abs(db) < 1e-7:
            break
    return a, b


def pary(rows):
    """[(datum, sport, logit(p), vysledek)] pro dvoucestné trhy, kde jsou obě strany vyhodnocené (1/0)."""
    g = defaultdict(list)
    for r in rows:
        if r.get("vysledek") in ("0", "1") and r.get("p"):
            g[(r["datum"], r["zapas"], r["trh"])].append(r)
    out = []
    for (d, _z, _t), v in g.items():
        if len(v) == 2 and v[0]["vyber"] != v[1]["vyber"] and {v[0]["vysledek"], v[1]["vysledek"]} == {"0", "1"}:
            for r in v:
                out.append((d, r["sport"], _logit(float(r["p"])), int(r["vysledek"])))
    return out


def odhad(rows):
    """Slovník sport -> {a, b, n, ll_pred, ll_po, pouzit}; pouzit = oprava se v ostrém provozu používá."""
    data = pary(rows)
    dny = sorted({d for d, *_ in data})
    hrani = dny[int(len(dny) * (1 - HOLDOUT_PODIL))] if len(dny) >= 6 else None
    vys = {}
    for sport in sorted({s for _, s, *_ in data}):
        x = [(l, y) for d, s, l, y in data if s == sport]
        if len(x) < MIN_PARU * 2:
            continue
        tr = [(l, y) for d, s, l, y in data if s == sport and hrani and d < hrani]
        te = [(l, y) for d, s, l, y in data if s == sport and hrani and d >= hrani]
        zaznam = {"n": len(x) // 2, "pouzit": False}
        if len(tr) >= MIN_PARU and len(te) >= MIN_PARU // 2:
            a, b = _fit(tr)
            zaznam.update(ll_pred=round(_ll(te, 0, 1), 5), ll_po=round(_ll(te, a, b), 5))
            zaznam["pouzit"] = zaznam["ll_po"] < zaznam["ll_pred"]
        a, b = _fit(x)
        zaznam.update(a=round(a, 4), b=round(b, 4))
        vys[sport] = zaznam
    return vys


def uloz(rows, log=print):
    v = odhad(rows)
    (config.DATA / "kalibrace_p.json").write_text(json.dumps(v, ensure_ascii=False, indent=1, sort_keys=True), encoding="utf-8")
    for s, z in v.items():
        log(f"   kalibrace p ({s}): b={z['b']}, a={z['a']}, holdout {z.get('ll_pred')}→{z.get('ll_po')} → {'POUŽITA' if z['pouzit'] else 'nepoužita'}")
    return v


_CACHE = {}


def oprav(p, sport):
    """Opravená férová p trhu; bez ověřené kalibrace pro sport vrací p beze změny."""
    if "v" not in _CACHE:
        f = config.DATA / "kalibrace_p.json"
        try:
            _CACHE["v"] = json.loads(f.read_text(encoding="utf-8")) if f.exists() else {}
        except Exception:
            _CACHE["v"] = {}
    z = _CACHE["v"].get(sport)
    if not z or not z.get("pouzit") or not (0 < p < 1):
        return p
    q = _sig(z["a"] + z["b"] * _logit(p))
    return min(max(q, p - MAX_POSUN), p + MAX_POSUN)
