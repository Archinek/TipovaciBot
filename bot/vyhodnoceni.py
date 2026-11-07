"""Evidence a vyhodnocení sázek ze všech sportů (výběr celé nabídky a tikety) podle výsledků z internetu.

Každá doporučená sázka (univerzální výběr + nohy denního tiketu a Pyramidy) se zapíše do data/nohy.csv a další den se podle
skóre vyhodnotí (1 = vyšla, 0 = nevyšla). Trhy, kterým skórem nerozumíme (hráčské statistiky, kombinace...), zůstanou
nevyhodnocené a v souhrnu se vypíše, které to jsou, abychom je mohli doplnit. Souhrn: úspěšnost a kalibrace p po sportech.
"""
import csv
import datetime
import re
import unicodedata

from . import config, vysledky

POLE = ["id", "datum", "sport", "liga", "zapas", "start", "trh", "vyber", "kurz", "p", "zdroj", "skupina", "vysledek", "duvod"]


def _cesta():
    return config.DATA / "nohy.csv"


def nacti():
    f = _cesta()
    if not f.exists():
        return []
    with f.open(encoding="utf-8", newline="") as fh:
        return list(csv.DictReader(fh))


def uloz(rows):
    f = _cesta()
    f.parent.mkdir(parents=True, exist_ok=True)
    with f.open("w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=POLE, extrasaction="ignore")
        w.writeheader()
        w.writerows(rows)


def _id(datum, n):
    return f"{datum}|{n['zapas']}|{n['trh']}|{n['vyber']}"


def zaloguj(datum, univ, tik):
    """Zapíše nové sázky (univ + nohy tiketů); stejná sázka v tiketu i ve výběru se zapíše jednou, skupiny se spojí."""
    rows = nacti()
    mam = {r["id"]: r for r in rows}
    nove = 0

    def pridej(n, skupina):
        nonlocal nove
        i = _id(datum, n)
        if i in mam:
            if skupina not in mam[i]["skupina"].split("+"):
                mam[i]["skupina"] += "+" + skupina
            return
        r = {"id": i, "datum": datum, "sport": n.get("sport") or "", "liga": n.get("liga") or "", "zapas": n["zapas"], "start": n.get("start") or "",
             "trh": n["trh"], "vyber": n.get("vyber") or "", "kurz": n["kurz"], "p": round(float(n["p"]), 4), "zdroj": n.get("zdroj", "trh"),
             "skupina": skupina, "vysledek": "", "duvod": ""}
        rows.append(r)
        mam[i] = r
        nove += 1

    for n in univ or []:
        pridej(n, "vyber")
    if tik:
        for klic in ("denni", "denni_alt"):
            for n in ((tik.get(klic) or {}).get("noze") or []):
                pridej(n, "tiket")
        for k in tik.get("pyramida") or []:
            for kl in ("tiket", "alt"):
                for n in ((k.get(kl) or {}).get("noze") or []):
                    pridej(n, "pyramida")
    uloz(rows)
    return nove


def _bez(s):
    return re.sub(r"\s+", " ", unicodedata.normalize("NFKD", s or "").encode("ascii", "ignore").decode().lower()).strip()


def _linie(*texty):
    for t in texty:
        m = re.search(r"(\d+(?:[.,]\d+)?)", t or "")
        if m:
            return float(m.group(1).replace(",", "."))
    return None


def rozhodni(r, v):
    """(1|0|None, důvod). r = řádek sázky, v = výsledek zápasu. None = trhu skórem nerozumíme."""
    trh, vyb = _bez(r["trh"]), _bez(r["vyber"])
    sport = v["sport"]
    ex = v.get("extra") or {}
    cele = any(x in trh for x in ("prodlouz", "vcetne", "vc.", "vc "))
    h, a = (ex.get("reg_h"), ex.get("reg_a")) if (sport == "hokej" and not cele and ex.get("reg_h") is not None) else (v["h"], v["a"])
    if h is None or a is None:
        return None, "bez skóre"
    # součet v zápase (celý zápas, ne tým/poločas/set)
    soucet = re.search(r"(pocet )?(golu|gol|branek|bodu|body|goly|branky)", trh) and ("v zapase" in trh or "v zapasu" in trh)
    if soucet and not any(x in trh for x in ("domaci", "hoste", "tym", "polocas", "tretina", "ctvrtina", "set")):
        line = _linie(trh, vyb)
        over = vyb.startswith("+") or any(x in vyb for x in ("vice", "over"))
        under = vyb.startswith("-") or any(x in vyb for x in ("mene", "under"))
        if line is not None and (over or under) and abs(line * 2 - round(line * 2)) < 1e-9 and line != int(line):
            return int((h + a) > line) if over else int((h + a) < line), f"{h}:{a}"
        return None, "linie"
    # střely na branku v hokeji (pouze bez prodloužení, kde jsou sog z celého zápasu shodné se základní dobou)
    if sport == "hokej" and "strel" in trh and ("v zapase" in trh or "v zapasu" in trh) and not any(x in trh for x in ("tym", "domaci", "hoste")) and ex.get("sog_h") is not None:
        if ex.get("prodlouzeni"):
            return None, "střely: prodloužení"
        line = _linie(trh, vyb)
        over = vyb.startswith("+") or "vice" in vyb
        if line is not None:
            s = ex["sog_h"] + ex["sog_a"]
            return int(s > line) if over else int(s < line), f"střely {s}"
    # vítěz zápasu
    if trh in ("zapas", "vitez zapasu", "vysledek zapasu", "zapas vcetne prodlouzeni", "vitez", "1x2") or trh.startswith(("zapas (", "vitez zapasu (")):
        dom, hos = [x.strip() for x in r["zapas"].split(" - ", 1)]
        if vyb in ("1",) or vysledky.shoda_tymu(vyb, dom) and not vysledky.shoda_tymu(vyb, hos):
            return int(h > a), f"{h}:{a}"
        if vyb in ("2",) or vysledky.shoda_tymu(vyb, hos) and not vysledky.shoda_tymu(vyb, dom):
            return int(a > h), f"{h}:{a}"
        if vyb in ("x", "remiza", "stejne"):
            return int(h == a), f"{h}:{a}"
    return None, "trh nerozpoznán"


def vyhodnot(ted, log=print):
    """Vyhodnotí sázky, jejichž zápas už skončil (start + 5 h < ted). Výsledky se stahují po dnech (data/vysledky/ cache)."""
    rows = nacti()
    cek = []
    for r in rows:
        if r["vysledek"] != "":
            continue
        try:
            s = datetime.datetime.fromisoformat(r["start"])
        except ValueError:
            continue
        if s + datetime.timedelta(hours=5) < ted:
            cek.append((r, s))
    if not cek:
        return 0
    dny = set()
    for _, s in cek:
        for dd in (-1, 0):
            dny.add((s.date() + datetime.timedelta(days=dd)).isoformat())
    vse = []
    for d in sorted(dny):
        vse += vysledky.ziskej(d, log=log)
    hotovo = 0
    for r, s in cek:
        v = vysledky.najdi([x for x in vse if x.get("final")], r["zapas"], sport=r["sport"] if r["sport"] in {x["sport"] for x in vse} else None)
        if not v:
            r["duvod"] = "výsledek nenalezen"
            continue
        y, duvod = rozhodni(r, v)
        r["duvod"] = duvod
        if y is not None:
            r["vysledek"] = str(y)
            hotovo += 1
    uloz(rows)
    log(f"   vyhodnoceno {hotovo} z {len(cek)} čekajících sázek (ostatní: výsledek nenalezen / trh nerozpoznán)")
    return hotovo


def souhrn(rows=None):
    rows = rows if rows is not None else nacti()
    h = [r for r in rows if r["vysledek"] in ("0", "1")]
    out = {"celkem": len(rows), "vyhodnoceno": len(h), "sporty": {}, "nerozpoznane": {}}
    for r in h:
        s = out["sporty"].setdefault(r["sport"] or "?", {"n": 0, "vyslo": 0, "p": 0.0, "brier": 0.0, "kurz_zisk": 0.0})
        y, p = int(r["vysledek"]), float(r["p"])
        s["n"] += 1
        s["vyslo"] += y
        s["p"] += p
        s["brier"] += (p - y) ** 2
        s["kurz_zisk"] += (float(r["kurz"]) - 1) if y else -1
    for r in rows:
        if r["vysledek"] == "" and r["duvod"] == "trh nerozpoznán":
            k = r["trh"][:45]
            out["nerozpoznane"][k] = out["nerozpoznane"].get(k, 0) + 1
    return out


def souhrn_text(s=None):
    s = s or souhrn()
    if not s["vyhodnoceno"]:
        return "Sázky z celé nabídky: zatím žádný vyhodnocený výsledek."
    cast = []
    for sp, v in sorted(s["sporty"].items(), key=lambda x: -x[1]["n"]):
        cast.append(f"{sp} {v['vyslo']}/{v['n']} ({v['vyslo'] / v['n']:.0%}, čekáno {v['p'] / v['n']:.0%}, flat {v['kurz_zisk'] / v['n']:+.0%})")
    return "Sázky z celé nabídky (vyhodnoceno " + str(s["vyhodnoceno"]) + "): " + "; ".join(cast)
