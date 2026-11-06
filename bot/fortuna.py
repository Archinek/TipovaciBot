"""Anonymní stažení veřejné nabídky Fortuny (JSON API, které používá jejich web).

Pravidla (aby se nic nezablokovalo): žádné cookies/přihlášení, poctivý User-Agent, pauza mezi požadavky,
při HTTP 403/429 se okamžitě končí a nic se neobchází.
Struktura odpovědí je převzatá z tvého test_api.py (tournaments -> matches -> markets);
neznámá pole se čtou obranně. `python -m bot.main fortuna_probe` uloží vzorek skutečných odpovědí.
"""
import datetime
import math
import re
import json
import time
import urllib.error
import urllib.request

from . import config

STRUKTURA = "https://api.ifortuna.cz/offer/structure/api/v1_0"
TRHY = "https://api.ifortuna.cz/offer/markets/api/v1_0"
UA = "tipovaci-bot/1.0"

# Trhy, které bot potřebuje (převzato z tvého skriptu). Ostatní se zahodí, ať je výstup malý.
TOP_LIGY = ["anglie - premier league", "německo - bundesliga", "španělsko - la liga", "španělsko - primera", "itálie - serie a", "francie - ligue 1", "nizozemsko - eredivisie", "portugalsko - primeira", "polsko - ekstraklasa", "česko - fortuna", "liga mistrů", "evropská liga", "konferenční liga", "anglie - championship"]
KATEGORIE = ["výsledek", "vítěz", "počet gólů", "počet bodů", "hráč dá", "kanadský bod", "touchdown",
             "yard", "střel na branku", "vyloučení", "roh", "kart", "žlut", "faul", "střídán", "asistence",
             "kombinace", "builder"]      # kmeny slov: roh/rohy/rohů, karty/karet, faul/faulů ...


class FortunaChyba(RuntimeError):
    pass


class FortunaBlok(FortunaChyba):
    """Web nás odmítl (403/429). Dál nepokračujeme."""


class Klient:
    def __init__(self, pauza=0.4, timeout=25):
        self.pauza, self.timeout, self._posledni, self.pocet = pauza, timeout, 0.0, 0

    def get(self, url):
        cekat = self.pauza - (time.time() - self._posledni)
        if cekat > 0:
            time.sleep(cekat)
        req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as r:
                data = json.load(r)
        except urllib.error.HTTPError as e:
            if e.code in (401, 403, 429):
                raise FortunaBlok(f"HTTP {e.code} u {url}. Web přístup odmítl, končím a nic neobcházím.") from None
            raise FortunaChyba(f"HTTP {e.code} u {url}") from None
        except (urllib.error.URLError, ValueError, TimeoutError) as e:
            raise FortunaChyba(f"{type(e).__name__} u {url}") from None
        finally:
            self._posledni = time.time()
            self.pocet += 1
        return data


def _seznam(data, *klice):
    if isinstance(data, list):
        return data
    if isinstance(data, dict):
        for k in klice:
            if isinstance(data.get(k), list):
                return data[k]
    return []


def turnaje(k, filtr):
    """Jen turnaje se zápasy (ne politika/RACES), které mají daný časový filtr (jinak endpoint vrací 404)."""
    vse = _seznam(k.get(f"{STRUKTURA}/tournaments?categories=true&timeFilter={filtr}"), "tournaments")
    return [t for t in vse if "MATCHES" in (t.get("features") or []) and filtr in (t.get("filters") or [filtr])]


def zapasy(k, tid, filtr):
    try:
        return _seznam(k.get(f"{STRUKTURA}/tournament/{tid}/matches?timeFilter={filtr}"), "fixtures")
    except FortunaChyba as e:
        if "HTTP 404" in str(e):
            return []
        raise


def trhy(k, fid):
    return _seznam(k.get(f"{TRHY}/fixture/{fid}/markets"), "markets")


def _prvni(d, *klice):
    for kl in klice:
        v = d.get(kl)
        if v not in (None, "", []):
            return v
    return None


def zajimave(trh):
    t = f"{trh.get('name', '')} {trh.get('marketTypeName', '')}".lower()
    return any(c in t for c in KATEGORIE)


def normalizuj_trhy(markets):
    out = []
    for m in markets:
        if not zajimave(m):
            continue
        out.append({"nazev": m.get("name", ""), "typ": m.get("marketTypeName", ""),
                    "vysledky": [{"nazev": o.get("longName") or o.get("name"), "kurz": o.get("odds")}
                                 for o in m.get("outcomes", []) if o.get("odds")]})
    return out


# ------------------------------------------------------------ strukturovaný parser trhů
# Ověřeno na skutečném vzorku (zápasy nižších lig): výsledek, góly celkem / týmu / 1. poločas, oba dají gól,
# dvojtip, bez remízy. Rohy/karty/fauly: názvy zatím NEOVĚŘENÉ (ve vzorku nebyly) -> hledá se podle klíčových slov.
_LINIE = re.compile(r"(Více|Méně)\s+než\s+(\d+(?:[.,]\d+)?)", re.I)
_CELKEM = {"rohy": "rohov", "karty": "žlutých karet", "fauly": "faul"}   # názvy ověřeny na top zápase: "Počet rohových kopů v zápasu 9.5", "Počet faulů v zápasu 26.5", "Počet žlutých karet v zápasu"


def _kurz(o):
    try:
        k = float(o.get("odds"))
        return k if k > 1.0 else None
    except (TypeError, ValueError):
        return None


def je_virtualni(z):
    t = f"{z.get('turnaj', '')} {z.get('kategorie', '')}".lower()
    return any(x in t for x in ("esport", "efotbal", "e-fotbal", "cyber", "2x4 min", "2x5 min", "virtual"))


def parsuj_trh(m):
    """Jeden trh Fortuny -> seznam nohou {trh, linie, strana, kurz}. Neznámé trhy vrací []."""
    typ = (m.get("marketTypeName") or "").strip()
    tl = typ.lower()
    klic = m.get("syntheticGroupKey") or ""
    popis = (m.get("marketTypeDesc") or "").lower()
    vysl = [(o, _kurz(o)) for o in m.get("outcomes") or []]
    vysl = [(o, k) for o, k in vysl if k]
    if len(vysl) < 2:
        return []
    out = []

    def ou(trh):
        for o, k in vysl:
            r = _LINIE.search(o.get("longName") or o.get("name") or "")
            if not r:
                continue
            L = float(r.group(2).replace(",", "."))
            if abs(L - math.floor(L) - 0.5) > 1e-9:
                continue                      # celočíselné/čtvrtkové linie mají vrácení vkladu -> neřešíme
            out.append({"trh": trh, "linie": L, "strana": "over" if r.group(1).lower().startswith("v") else "under", "kurz": k})

    def mapa(trh, povolene):
        for o, k in vysl:
            n = (o.get("name") or "").strip().lower()
            if n in povolene:
                out.append({"trh": trh, "linie": None, "strana": povolene[n], "kurz": k})

    if klic == "match":
        mapa("1x2", {"1": "1", "0": "0", "2": "2"})
    elif klic == "draw_no_bet":
        mapa("dnb", {"1": "1", "2": "2"})
    elif klic == "match_-_double_chance":
        mapa("dc", {"10": "10", "02": "02", "12": "12"})
    elif klic == "both_teams_to_score":
        mapa("btts", {"ano": "ano", "ne": "ne"})
    elif tl in ("vítěz zápasu", "vítěz utkání"):      # dvoucestný vítěz (tenis, esporty, volejbal...): výstupy "1" / "2"
        mapa("h2h2", {"1": "1", "2": "2"})
    elif tl == "počet gólů v zápasu":
        ou("goly")
    elif tl == "počet gólů v 1. poločasu":
        ou("goly_1p")
    elif tl.endswith(" počet gólů v zápasu") and not tl.startswith("1.poločas") and "poločas" not in tl:
        if "1. týmu" in popis:
            ou("goly_dom")
        elif "2. týmu" in popis:
            ou("goly_hos")
    elif "počet es" in tl and not re.search(r"\bset", tl):
        # tenis; NÁZVY NEOVĚŘENÉ (podle Tipsportu: "Počet es v zápasu", "Počet es <hráč> v zápasu"). fortuna_probe uloží skutečné.
        ostatek = re.sub(r"\s+", " ", tl.replace("počet es", "").replace("v zápasu", "")).strip(" :-")
        n0 = len(out)
        hrac = bool(ostatek) or "hráče" in popis or "týmu" in popis
        ou("esa_hrac" if hrac else "esa")
        for x in out[n0:]:
            if hrac:
                if "1." in popis:
                    x["pozice"] = "1"
                elif "2." in popis:
                    x["pozice"] = "2"
                if ostatek:
                    x["hrac"] = ostatek
    elif "dvojchyb" in tl and not re.search(r"\bset", tl):
        # tenis (Marty37); NÁZVY NEOVĚŘENÉ. "Počet dvojchyb [hráč] v zápasu" a "Kdo zahraje více dvojchyb v zápasu (bez remízy)"
        if tl.startswith("kdo") and "více" in tl:
            for o, k in vysl:
                nm = (o.get("longName") or o.get("name") or "").strip()
                if nm and nm.lower() not in ("remíza", "remiza", "x", "0"):
                    out.append({"trh": "df_kdo", "linie": None, "strana": nm.lower(), "hrac": nm, "kurz": k})
        else:
            ostatek = re.sub(r"\s+", " ", tl.replace("počet dvojchyb", "").replace("v zápasu", "")).strip(" :-")
            n0 = len(out)
            hrac = bool(ostatek) or "hráče" in popis or "týmu" in popis
            ou("df_hrac" if hrac else "df")
            for x in out[n0:]:
                if hrac:
                    if "1." in popis:
                        x["pozice"] = "1"
                    elif "2." in popis:
                        x["pozice"] = "2"
                    if ostatek:
                        x["hrac"] = ostatek
    elif tl.startswith("počet střel") and ("bránu" in tl or "branku" in tl) and "hráč" not in tl and "poločas" not in tl:
        # fotbal; NÁZVY NEOVĚŘENÉ. Celkem jen když mezi "počet střel" a "na bránu" nic není, jinak týmová podle popisu.
        if "1. týmu" in popis:
            ou("sot_dom")
        elif "2. týmu" in popis:
            ou("sot_hos")
        elif tl.startswith("počet střel na"):
            ou("sot")
    else:
        for trh, kw in _CELKEM.items():
            if tl.startswith("počet") and kw in tl and "poločas" not in tl:       # jen celkový počet, ne týmový ("Cracovia počet ...")
                ou(trh)
                break
    return out


def klic_nohy(n):
    """Stabilní klíč nohy, podle kterého ji najdeme v pozdějším snímku nabídky (pohyb kurzu, CLV)."""
    return f"{n['trh']}|{n.get('linie')}|{n['strana']}|{n.get('hrac') or n.get('pozice') or ''}"


def nohy_zapasu(markets):
    out = []
    for m in markets:
        try:
            out += parsuj_trh(m)
        except (TypeError, ValueError, AttributeError):
            continue
    return out


def _iso(ms):
    try:
        return datetime.datetime.fromtimestamp(int(ms) / 1000, datetime.timezone.utc).isoformat()
    except (TypeError, ValueError, OSError):
        return None


def normalizuj_zapas(fx, turnaj):
    """Struktura ověřená na vzorku skutečné odpovědi: participants[type=HOME/AWAY], startDatetime v ms."""
    home = away = None
    for ucastnik in fx.get("participants") or []:
        if ucastnik.get("type") == "HOME":
            home = ucastnik.get("name")
        elif ucastnik.get("type") == "AWAY":
            away = ucastnik.get("name")
    nazev = fx.get("name") or ""
    if (not home or not away) and " - " in nazev:
        home, away = [x.strip() for x in nazev.split(" - ", 1)]
    return {"id": fx.get("id"), "nazev": nazev, "home": home, "away": away,
            "start": _iso(fx.get("startDatetime")), "live": fx.get("kind") == "LIVE",
            "aktivni": fx.get("status") == "ACTIVE", "ma_trhy": bool(fx.get("hasMarkets")),
            "sport": _prvni(fx, "sportSeoName") or turnaj.get("sportSeoName") or "",
            "turnaj": turnaj.get("name") or "", "turnaj_popis": turnaj.get("description") or "", "kategorie": fx.get("categorySeoName") or turnaj.get("categorySeoName") or "",
            "turnaj_id": turnaj.get("id")}


def nabidka(k=None, filtry=("today", "tomorrow"), max_zapasu=600, log=print):
    """Stáhne dnešní/zítřejší zápasy včetně vybraných trhů. -> seznam normalizovaných zápasů."""
    nast = (config.nacti_cfg().get("fortuna") or {})
    k = k or Klient(pauza=nast.get("pauza_s", 0.4))
    videno, zap = set(), []
    for f in filtry:
        for t in turnaje(k, f):
            for fx in zapasy(k, t.get("id"), f):
                if fx.get("id") and fx["id"] not in videno:
                    videno.add(fx["id"])
                    z = normalizuj_zapas(fx, t)
                    if z["live"] or not z["aktivni"] or not z["ma_trhy"]:
                        continue                      # živé a neaktivní zápasy bot nepotřebuje
                    zap.append(z)
    log(f"Fortuna: {len(zap)} zápasů v nabídce ({', '.join(filtry)}).")
    zap = zap[:max_zapasu]
    for i, z in enumerate(zap, 1):
        try:
            ms = trhy(k, z["id"])
            z["trhy"] = normalizuj_trhy(ms)
            z["nohy"] = nohy_zapasu(ms)
        except FortunaBlok:
            raise
        except FortunaChyba as e:
            log(f"⚠️ {e}")
            z["trhy"], z["nohy"] = [], []
        if i % 100 == 0:
            log(f"   {i}/{len(zap)} ...")
    return zap


def uloz_nabidku(zap, datum):
    p = config.DATA / f"fortuna_nabidka_{datum}.json"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(zap, ensure_ascii=False, indent=1), encoding="utf-8")
    return p


def jetop(t):
    n = (t.get("name") or "").lower()
    return any(x in n for x in TOP_LIGY) and not any(x in n for x in ("u21", "u19", "u23", "amat", "ženy", "esport"))


def probe(k=None, log=print):
    """Uloží vzorek skutečných odpovědí do data/fortuna_vzorek/ (hlavně fotbal: karty, fauly, rohy)."""
    k = k or Klient()
    d = config.DATA / "fortuna_vzorek"
    d.mkdir(parents=True, exist_ok=True)
    shrnuti, nazvy, vzorek, videno_sport = [], {}, [], set()
    try:
        tur = turnaje(k, "today")
        shrnuti.append(f"turnajů dnes (se zápasy): {len(tur)}")
        fotbal = [t for t in tur if t.get("sportSeoName") == "fotbal" and not je_virtualni({"turnaj": t.get("name"), "kategorie": t.get("categorySeoName")})]
        fotbal.sort(key=lambda t: 0 if jetop(t) else 1)
        prio = {"tenis": 0, "hokej": 1, "basketbal": 2}                  # sporty, které hrají TOP tipéři
        ostatni = sorted((t for t in tur if t.get("sportSeoName") != "fotbal"), key=lambda t: prio.get(t.get("sportSeoName"), 9))
        shrnuti.append(f"z toho fotbalových: {len(fotbal)}")
        (d / "1_turnaje.json").write_text(json.dumps((fotbal[:2] + ostatni[:2]), ensure_ascii=False, indent=1), encoding="utf-8")
        for seznam, limit in ((fotbal, 8), (ostatni, 10)):
            nasel = 0
            for t in seznam[:40]:
                for fx in zapasy(k, t.get("id"), "today"):
                    z = normalizuj_zapas(fx, t)
                    if z["id"] and not z["live"] and z["aktivni"] and z["ma_trhy"]:
                        vzorek.append((fx, t))
                        nasel += 1
                        break
                if nasel >= limit:
                    break
        shrnuti.append(f"zápasů ve vzorku: {len(vzorek)}")
        (d / "2_zapasy_vzorek.json").write_text(
            json.dumps([{"turnaj": t.get("name"), "fixture": fx} for fx, t in vzorek[:3]], ensure_ascii=False, indent=1), encoding="utf-8")
        top = 0
        for i, (fx, t) in enumerate(vzorek):
            ms = trhy(k, fx["id"])
            if i < 2:
                (d / f"3_trhy_zapas_{i + 1}.json").write_text(json.dumps(ms[:40], ensure_ascii=False, indent=1), encoding="utf-8")
            if jetop(t) and top < 3:
                top += 1
                (d / f"5_top_liga_{top}.json").write_text(json.dumps({"zapas": fx.get("name"), "turnaj": t.get("name"), "trhy": ms}, ensure_ascii=False, indent=1), encoding="utf-8")
            sp = t.get("sportSeoName")
            if sp in ("tenis", "hokej") and sp not in videno_sport:           # plné trhy po jednom zápase tenisu a hokeje (es, střely, hráči)
                videno_sport.add(sp)
                (d / f"6_{sp}_trhy.json").write_text(json.dumps({"zapas": fx.get("name"), "turnaj": t.get("name"), "trhy": ms}, ensure_ascii=False, indent=1), encoding="utf-8")
            for m in ms:
                nazvy[(t.get("sportSeoName"), m.get("name", ""))] = m.get("marketTypeName", "")
        (d / "4_nazvy_trhu.txt").write_text(
            "\n".join(f"{sp}  |  {n}  |  {t}" for (sp, n), t in sorted(nazvy.items())), encoding="utf-8")
        shrnuti.append(f"různých názvů trhů: {len(nazvy)}")
        shrnuti.append(f"top-ligových zápasů uloženo (5_top_liga_*.json): {top}")
    except FortunaBlok as e:
        shrnuti.append(f"⛔ {e}")
    except FortunaChyba as e:
        shrnuti.append(f"⚠️ {e}")
    shrnuti.append(f"požadavků: {k.pocet}")
    (d / "0_shrnuti.txt").write_text("\n".join(shrnuti), encoding="utf-8")
    for s_ in shrnuti:
        log(s_)
    return shrnuti


def radky_pro_mojekurzy(zapasy):
    """Kurzy Fortuny na výsledek zápasu ve formátu, který zná mojekurzy.aplikuj (vyber = tým nebo Draw)."""
    out = []
    for z in zapasy:
        if not (z.get("home") and z.get("away")):
            continue
        for n in z.get("nohy") or []:
            if n["trh"] not in ("1x2", "h2h2"):
                continue
            v = {"1": z["home"], "2": z["away"], "0": "Draw"}.get(n["strana"])
            if v:
                out.append({"home": z["home"], "away": z["away"], "trh": "h2h", "vyber": v, "linie": "", "strana": "",
                            "kurz": n["kurz"], "kancelar": "Fortuna (orientačně)"})
    return out
