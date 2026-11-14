"""Ověření segmentů: kde (sport × druh trhu × pásmo kurzu) se bot na vlastních vyhodnocených sázkách skutečně osvědčil.

Pravděpodobnost z trhu se nepovažuje za "model", dokud segment neprojde testem:
  1) dost unikátních zápasů a dní,
  2) zisk na "objevném" období (starší 2/3 dní) je statisticky kladný (jednostranně ~95 %),
  3) a znovu kladný na novějším období (1/3 dní), které se při objevu nepoužilo (ochrana proti náhodě; segmentů jsou stovky).
Stavy: málo dat / trh sedí / trh přeceňuje / kandidát (prošel jen 2) / ověřeno.
"""
import math
import re

from . import prehled, ucici

RODINY = [("handicap", r"handicap"), ("hráč: gól/bod", r"\b(dá gól|nedá gól|góly|body|asistenc)"), ("střely", r"střel"), ("tresty", r"trest"), ("rohy", r"roh"),
          ("karty", r"karet|karty"), ("sety/gamy", r"\b(set|game|gem)"), ("přesně/skóre", r"přesn|skóre|správn"), ("over/under", r"více než|méně než|počet|celkem|součet|\bover\b|\bunder\b"),
          ("vítěz", r"výsledek zápasu|vítěz|zápas:|1x2|neprohra|remíz")]


def rodina(trh, vyber=""):
    t = f"{trh or ''} {vyber or ''}".lower()
    for nazev, rx in RODINY:
        if re.search(rx, t):
            return nazev
    return "ostatní"


def _klic(r):
    return (r.get("sport") or "?", rodina(r.get("trh"), r.get("vyber")), prehled._pasmo(r))


def _stat(rows, z):
    n = len(rows)
    if not n:
        return None
    zisk = [(float(r["kurz"]) - 1) if r["vysledek"] == "1" else -1.0 for r in rows]
    roi = sum(zisk) / n
    zap = len({(r["zapas"], (r.get("start") or "")[:10]) for r in rows})
    sd = math.sqrt(sum((g - roi) ** 2 for g in zisk) / max(1, n - 1))
    se = sd / math.sqrt(max(1, zap))                              # konzervativně: sázky na stejný zápas se počítají jako jeden vzorek
    return {"n": n, "zapasu": zap, "roi": roi, "dolni": roi - z * se, "horni": roi + z * se,
            "uspesnost": sum(r["vysledek"] == "1" for r in rows) / n, "cekano": sum(float(r["p"]) for r in rows) / n}


def vypocti(rows, cfg=None):
    """-> {(sport, rodina, pasmo): {stav, objev, holdout, ...}}"""
    c = (cfg or {}).get("overeni") or {}
    min_zap, min_dnu, z, min_hold = int(c.get("min_zapasu", 150)), int(c.get("min_dnu", 7)), float(c.get("jistota_z", 1.64)), int(c.get("min_holdout", 40))
    h = [r for r in rows if r.get("vysledek") in ("0", "1")]
    dny = sorted({r["datum"] for r in h})
    hranice = dny[max(0, int(len(dny) * 2 / 3) - 1)] if len(dny) >= min_dnu else None
    seg = {}
    for r in h:
        seg.setdefault(_klic(r), []).append(r)
    out = {}
    for k, rr in seg.items():
        celek = _stat(rr, z)
        if celek["zapasu"] < min_zap or len(dny) < min_dnu:
            out[k] = {"stav": "málo dat", **celek}
            continue
        objev = _stat([r for r in rr if r["datum"] <= hranice], z)
        hold = _stat([r for r in rr if r["datum"] > hranice], z)
        if celek["horni"] < 0:
            stav = "trh přeceňuje"
        elif objev and objev["dolni"] > 0:
            stav = "ověřeno" if hold and hold["zapasu"] >= min_hold and hold["roi"] > 0 else "kandidát"
        else:
            stav = "trh sedí"
        out[k] = {"stav": stav, **celek, "objev": objev, "holdout": hold}
    return out


def oznac(radky, seg):
    """Ke každé kandidátní sázce doplní stav ověření jejího segmentu (klíč 'overeni')."""
    for x in radky or []:
        s = seg.get(_klic({"sport": x.get("sport") or "?", "trh": x.get("trh"), "vyber": x.get("vyber"), "kurz": x.get("kurz", x.get("kurz_fortuna"))}))
        x["overeni"] = s["stav"] if s else "málo dat"
    return radky


PORADI = {"ověřeno": 0, "kandidát": 1, "trh přeceňuje": 2, "trh sedí": 3, "málo dat": 4}


def tabulka(seg, max_radku=12):
    """Seznam segmentů pro report: nejdřív ověřené a kandidáti, pak ostatní s dost daty podle ROI."""
    r = [{"sport": k[0], "rodina": k[1], "pasmo": k[2], **v} for k, v in seg.items()]
    r.sort(key=lambda x: (PORADI[x["stav"]], -x["zapasu"]))
    return r[:max_radku]
