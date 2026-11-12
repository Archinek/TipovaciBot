"""Výsledky ze stejného veřejného API Fortuny, ze kterého se bere nabídka (stránka Výsledky na ifortuna.cz).

Odpověď: sports?date= -> sport/<id>/tournaments?date= -> tournament/<id>/matches?date=&overviewMarkets=true.
U zápasu je skóre a u každého přehledového trhu a možnosti `result`: WINNING / LOSING / VOIDED. Fortuna tedy vyhodnocuje sama,
bot jen čte. Trhy, které v přehledu nejsou (rohy, střely, karty...), zůstávají na starší cestě (skóre z jiných zdrojů) nebo nevyhodnocené.
Pravidla slušnosti stejná jako u nabídky: poctivý User-Agent, pauzy, při 403/429 se končí a nic neobchází.
"""
import datetime
import re
import unicodedata
from zoneinfo import ZoneInfo

from . import fortuna

ZAKLAD = "https://api.ifortuna.cz/offer/result/api/v1_0"
_CACHE = {}          # (datum, id sportu) -> [zápasy]; jen po dobu jednoho běhu
VYSLEDKY = {"WINNING": "1", "LOSING": "0", "VOIDED": "V"}


def _n(t):
    t = unicodedata.normalize("NFKD", t or "").encode("ascii", "ignore").decode().lower()
    return re.sub(r"[^a-z0-9.+\-]+", " ", t).strip()


def _sport_klic(t):
    return _n(t).replace("-", " ")


def _trhy(markets):
    """Seznam trhů z API -> {název trhu: {možnost: '1'|'0'|'V'}}; rozehrané/neznámé výsledky se přeskočí."""
    trhy = {}
    for m in markets or []:
        vyst = {}
        for o in m.get("outcomes") or []:
            res = VYSLEDKY.get(o.get("result"))
            if res is None:
                continue
            for jm in (o.get("name"), o.get("longName")):
                if jm:
                    vyst[_n(jm)] = res
        if vyst:
            trhy[_n(m.get("name"))] = vyst
    return trhy


def _najdi_trhy(data):
    """Z detailu zápasu (tvar nevíme jistě) vytáhne seznam trhů: první seznam 'markets' nebo seznam objektů s 'outcomes'."""
    if isinstance(data, dict):
        if isinstance(data.get("markets"), list):
            return data["markets"]
        for v in data.values():
            r = _najdi_trhy(v)
            if r:
                return r
    elif isinstance(data, list) and data and isinstance(data[0], dict) and "outcomes" in data[0]:
        return data
    return []


def _skore(data):
    if isinstance(data, dict):
        if isinstance(data.get("score"), dict):
            return data["score"]
        for v in data.values():
            r = _skore(v)
            if r:
                return r
    return None


def doplnit_detail(zapasy, log=print, klient=None, max_zapasu=300):
    """U zápasů, které Fortuna ukazuje jen přehledově, stáhne detail se VŠEMI trhy (hráči, over/under, rohy...): fixture/<id>?date=&markets=true."""
    k = klient or fortuna.Klient(pauza=0.3)
    ok = 0
    try:
        for z in [x for x in zapasy if x.get("id") and not x.get("detail")][:max_zapasu]:
            d = datetime.datetime.fromtimestamp((z.get("start_ms") or 0) / 1000, ZoneInfo("Europe/Prague")).date().isoformat()
            try:
                data = k.get(f"{ZAKLAD}/fixture/{z['id']}?date={d}&markets=true")
            except fortuna.FortunaBlok:
                raise
            except fortuna.FortunaChyba as e:
                log(f"   ⚠️ Detail zápasu {z['name']}: {e}")
                z["detail"] = True
                continue
            z["trhy"].update(_trhy(_najdi_trhy(data)))
            sk = _skore(data) or {}
            if z.get("h") is None and sk:
                z["h"], z["a"] = sk.get("homeScore"), sk.get("awayScore")
            z["detail"] = True
            ok += 1
    except fortuna.FortunaBlok as e:
        log(f"   ⛔ {e}")
    return ok


def _zapas(fx, trhy_podle, tur, sport):
    sk = fx.get("score") or {}
    trhy = _trhy(trhy_podle.get(fx.get("id"), []))
    return {"id": fx.get("id"), "name": fx.get("name") or "", "start_ms": fx.get("startDatetime"), "sport": sport, "turnaj": tur,
            "h": sk.get("homeScore"), "a": sk.get("awayScore"), "trhy": trhy}


def stahni(dny, sporty, log=print, klient=None):
    """Zápasy s výsledky pro dané dny (YYYY-MM-DD, pražský den začátku) a sporty (názvy jako v nabídce). -> [zápas]."""
    k = klient or fortuna.Klient(pauza=0.3)
    chci = {_sport_klic(s) for s in sporty if s}
    out = []
    try:
        for d in sorted(dny):
            sporty_f = k.get(f"{ZAKLAD}/sports?date={d}")
            sporty_f = sporty_f if isinstance(sporty_f, list) else (sporty_f or {}).get("sports") or []
            for sp in sporty_f:
                if chci and _sport_klic(sp.get("name")) not in chci:
                    continue
                klic = (d, sp.get("id"))
                if klic not in _CACHE:
                    zap = []
                    try:
                        tt = k.get(f"{ZAKLAD}/sport/{sp['id']}/tournaments?date={d}").get("tournaments") or []
                    except fortuna.FortunaBlok:
                        raise
                    except fortuna.FortunaChyba as e:
                        log(f"   ⚠️ Výsledky Fortuny {d} {sp.get('name')}: {e}")
                        continue
                    for t in tt:
                        try:
                            data = k.get(f"{ZAKLAD}/tournament/{t['id']}/matches?date={d}&overviewMarkets=true")
                        except fortuna.FortunaBlok:
                            raise
                        except fortuna.FortunaChyba as e:
                            log(f"   ⚠️ Výsledky Fortuny {d} {t.get('name')}: {e}")
                            continue
                        podle = {}
                        for m in data.get("markets") or []:
                            podle.setdefault(m.get("fixtureId"), []).append(m)
                        zap += [_zapas(fx, podle, t.get("name"), sp.get("name")) for fx in data.get("fixtures") or []]
                    _CACHE[klic] = zap
                out += _CACHE[klic]
    except fortuna.FortunaBlok as e:
        log(f"   ⛔ {e}")
    except Exception as e:
        log(f"   ⚠️ Výsledky Fortuny selhaly: {type(e).__name__}: {e}")
    return out


def index(zapasy):
    i = {}
    for z in zapasy:
        i.setdefault(_n(z["name"]), []).append(z)
    return i


def najdi(idx, zapas, start_iso):
    """Zápas podle názvu a času začátku (do 36 h rozdílu)."""
    kand = idx.get(_n(zapas)) or []
    try:
        s0 = datetime.datetime.fromisoformat(start_iso)
        s = (s0 if s0.tzinfo else s0.replace(tzinfo=datetime.timezone.utc)).timestamp() * 1000
    except (TypeError, ValueError):
        return kand[0] if len(kand) == 1 else None
    kand = [z for z in kand if z.get("start_ms") and abs(z["start_ms"] - s) <= 36 * 3600 * 1000]
    return min(kand, key=lambda z: abs(z["start_ms"] - s)) if kand else None


def rozhodni(trh, vyber, z):
    """('1'|'0'|'V'|None, důvod): výsledek, který Fortuna u dané možnosti uvedla. None = trh nebo možnost v přehledu není."""
    t = z["trhy"].get(_n(trh))
    if t is None:
        return None, "trh není ve výsledcích Fortuny"
    r = t.get(_n(vyber))
    if r is None:
        return None, "možnost není ve výsledcích Fortuny"
    return r, ("zrušeno (VOIDED)" if r == "V" else f"Fortuna: {z['h']}:{z['a']}")


def pražský_den(iso):
    s = datetime.datetime.fromisoformat(iso)
    return (s if s.tzinfo else s.replace(tzinfo=datetime.timezone.utc)).astimezone(ZoneInfo("Europe/Prague")).date().isoformat()
