"""Výsledky zápasů z internetu (pro učení bota): ESPN (CDN), NHL api-web (skóre i střely), nflverse (NFL).

Každý zdroj vrací jednotné záznamy: {sport, liga, home, away, h, a, final, start (ISO UTC), zdroj, extra}.
Teletext ČT a TheSportsDB z GitHub Actions vrací 403, proto se nepoužívají. Chyba zdroje nikdy nesmí shodit běh:
zdroj se přeskočí a vyhodnocení se zopakuje další den. Výsledky se ukládají do data/vysledky/<datum>.json (cache).
"""
import csv
import datetime
import io
import json
import urllib.request
from difflib import SequenceMatcher

from . import config, histdata

UA = {"User-Agent": "Mozilla/5.0 (compatible; TipovaciBot/1.0)", "Accept": "application/json,text/csv,*/*"}
ESPN = [("americky-fotbal", "NFL", "nfl"), ("basketbal", "NBA", "nba"), ("basketbal", "WNBA", "wnba"),
        ("baseball", "MLB", "mlb")]
NFL_TYMY = {"ARI": "arizona cardinals", "ATL": "atlanta falcons", "BAL": "baltimore ravens", "BUF": "buffalo bills", "CAR": "carolina panthers",
            "CHI": "chicago bears", "CIN": "cincinnati bengals", "CLE": "cleveland browns", "DAL": "dallas cowboys", "DEN": "denver broncos",
            "DET": "detroit lions", "GB": "green bay packers", "HOU": "houston texans", "IND": "indianapolis colts", "JAX": "jacksonville jaguars",
            "KC": "kansas city chiefs", "LV": "las vegas raiders", "LAC": "los angeles chargers", "LA": "los angeles rams", "MIA": "miami dolphins",
            "MIN": "minnesota vikings", "NE": "new england patriots", "NO": "new orleans saints", "NYG": "new york giants", "NYJ": "new york jets",
            "PHI": "philadelphia eagles", "PIT": "pittsburgh steelers", "SF": "san francisco 49ers", "SEA": "seattle seahawks", "TB": "tampa bay buccaneers",
            "TEN": "tennessee titans", "WAS": "washington commanders"}


def _get(url, timeout=30):
    with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=timeout) as r:
        return r.read().decode("utf-8", "replace")


def _najdi_events(o, out):
    """ESPN vrací seznam 'events' na proměnlivém místě JSONu: projde se rekurzivně."""
    if isinstance(o, dict):
        ev = o.get("events")
        if isinstance(ev, list) and ev and isinstance(ev[0], dict) and "competitions" in ev[0]:
            out.extend(ev)
        for v in o.values():
            if isinstance(v, (dict, list)):
                _najdi_events(v, out)
    elif isinstance(o, list):
        for v in o:
            _najdi_events(v, out)


def _cislo(x):
    try:
        return int(float(x))
    except (TypeError, ValueError):
        return None


def _espn_stahni(cesta, parametr, datum):
    js = json.loads(_get(f"https://cdn.espn.com/core/{cesta}/scoreboard?xhr=1&{parametr}={datum.replace('-', '')}"))
    ev = []
    _najdi_events(js, ev)
    return ev


def _datum_ev(e):
    return ((e.get("date") or (e.get("competitions") or [{}])[0].get("date") or "")[:10])


def espn(datum, log=print):
    """ESPN CDN scoreboard. Parametr data se u CDN verze nemusí brát v úvahu: zkusí se 'dates' a 'date'; zápasy se přesto ukládají
    s vlastním datem začátku, takže i program 'dnes' (vrácený místo požadovaného dne) se vyhodnotí správně."""
    out = []
    d0 = datetime.date.fromisoformat(datum)
    okno = {(d0 + datetime.timedelta(days=k)).isoformat() for k in (-1, 0, 1)}
    for sport, liga, cesta in ESPN:
        ev = []
        try:
            for par in ("dates", "date"):
                ev = _espn_stahni(cesta, par, datum)
                if any(_datum_ev(e) in okno for e in ev):
                    break
        except Exception as e:
            log(f"   ESPN {liga} {datum}: {type(e).__name__}: {e}")
            continue
        n = 0
        for e in ev:
            try:
                c = e["competitions"][0]
                kom = {x["homeAway"]: x for x in c["competitors"]}
                h, a = _cislo(kom["home"].get("score")), _cislo(kom["away"].get("score"))
                fin = bool((e.get("status") or c.get("status") or {}).get("type", {}).get("completed"))
                out.append({"sport": sport, "liga": liga, "home": kom["home"]["team"].get("displayName") or kom["home"]["team"].get("name"),
                            "away": kom["away"]["team"].get("displayName") or kom["away"]["team"].get("name"),
                            "h": h, "a": a, "final": fin and h is not None and a is not None,
                            "start": (e.get("date") or c.get("date") or "")[:16], "zdroj": "espn", "extra": {}})
                n += 1
            except (KeyError, IndexError, TypeError):
                continue
        dat = sorted({_datum_ev(e) for e in ev if _datum_ev(e)})
        log(f"   ESPN {liga} {datum}: {n} zápasů, z toho odehraných {sum(1 for x in out if x['liga'] == liga and x['final'])}"
            + (f", data {dat[0]}..{dat[-1]}" if dat else ""))
    return out


def nhl(datum, log=print):
    out = []
    try:
        js = json.loads(_get(f"https://api-web.nhle.com/v1/score/{datum}"))
    except Exception as e:
        log(f"   NHL {datum}: {type(e).__name__}: {e}")
        return out
    for g in js.get("games", []):
        if g.get("gameState") not in ("OFF", "FINAL"):
            continue
        ht, at = g.get("homeTeam", {}), g.get("awayTeam", {})
        pt = (g.get("gameOutcome") or {}).get("lastPeriodType", "REG")
        reg_h = reg_a = None
        goly = [x for x in g.get("goals", []) if (x.get("periodDescriptor") or {}).get("periodType") == "REG"]
        if pt == "REG":
            reg_h, reg_a = ht.get("score"), at.get("score")
        else:
            reg_h = goly[-1].get("homeScore") if goly else 0
            reg_a = goly[-1].get("awayScore") if goly else 0
        out.append({"sport": "hokej", "liga": "NHL", "home": (ht.get("placeName") or {}).get("default", "") + " " + (ht.get("name") or {}).get("default", ""),
                    "away": (at.get("placeName") or {}).get("default", "") + " " + (at.get("name") or {}).get("default", ""),
                    "h": ht.get("score"), "a": at.get("score"), "final": True, "start": (g.get("startTimeUTC") or "")[:16], "zdroj": "nhl",
                    "extra": {"reg_h": reg_h, "reg_a": reg_a, "prodlouzeni": pt != "REG", "sog_h": ht.get("sog"), "sog_a": at.get("sog")}})
    # score/{datum} nemá placeName: doplň z názvu týmu (stačí 'Panthers'; shoda je podle slov)
    for x in out:
        x["home"], x["away"] = x["home"].strip(), x["away"].strip()
    log(f"   NHL {datum}: {len(out)} odehraných zápasů")
    return out


def nfl_csv(datum, log=print):
    out = []
    try:
        txt = _get("https://raw.githubusercontent.com/nflverse/nfldata/master/data/games.csv", timeout=60)
    except Exception as e:
        log(f"   nflverse: {type(e).__name__}: {e}")
        return out
    dnes = datetime.date.fromisoformat(datum)
    for r in csv.DictReader(io.StringIO(txt)):
        try:
            d = datetime.date.fromisoformat(r["gameday"])
        except (KeyError, ValueError):
            continue
        if abs((d - dnes).days) > 1 or not r.get("home_score") or not r.get("away_score"):
            continue
        h, a = NFL_TYMY.get(r["home_team"]), NFL_TYMY.get(r["away_team"])
        if h and a:
            out.append({"sport": "americky-fotbal", "liga": "NFL", "home": h, "away": a, "h": int(r["home_score"]), "a": int(r["away_score"]),
                        "final": True, "start": r["gameday"] + "T" + (r.get("gametime") or "00:00"), "zdroj": "nflverse",
                        "extra": {"prodlouzeni": r.get("overtime") == "1", "spread": r.get("spread_line"), "total_line": r.get("total_line")}})
    log(f"   nflverse {datum}: {len(out)} zápasů")
    return out


def ziskej(datum, log=print, cache=True):
    """Všechny dostupné výsledky pro datum (cache v data/vysledky/). Nehotové zápasy se do cache neukládají trvale: cache jen pokud něco je."""
    d = config.DATA / "vysledky"
    f = d / f"{datum}.json"
    stary = datetime.date.fromisoformat(datum) < datetime.date.today() - datetime.timedelta(days=2)
    cache = cache and stary
    if cache and f.exists():
        try:
            return json.loads(f.read_text(encoding="utf-8"))
        except ValueError:
            pass
    vse = []
    for fn in (nhl, espn, nfl_csv):
        try:
            vse += fn(datum, log=log)
        except Exception as e:
            log(f"   {fn.__name__}: {type(e).__name__}: {e}")
    videno, uniq = set(), []
    for x in vse:
        k = (x["home"], x["away"], x["start"][:10], x["zdroj"])
        if k not in videno:
            videno.add(k)
            uniq.append(x)
    vse = uniq
    if vse and cache:
        d.mkdir(parents=True, exist_ok=True)
        f.write_text(json.dumps(vse, ensure_ascii=False), encoding="utf-8")
    return vse


def _tok(n):
    t = set(histdata._norm(n or "").split())
    if "la" in t:
        t = (t - {"la"}) | {"los", "angeles"}
    if "ny" in t:
        t = (t - {"ny"}) | {"new", "york"}
    return t


def shoda_tymu(a, b):
    """Stejný tým (Fortuna 'Florida Panthers' ~ NHL 'Panthers'): shoda názvu, podmnožina slov, nebo podobnost >= 0.88."""
    ta, tb = _tok(a), _tok(b)
    if not ta or not tb:
        return False
    if ta == tb or ta <= tb or tb <= ta:
        return True
    return SequenceMatcher(None, " ".join(sorted(ta)), " ".join(sorted(tb))).ratio() >= 0.88


def najdi(vysledky, zapas, sport=None, start=None):
    """Výsledek pro zápas 'Domácí - Hosté' (obě strany musí souhlasit, domácí/hosté i obráceně se zkouší jen v tomto pořadí)."""
    if " - " not in (zapas or ""):
        return None
    dom, hos = [x.strip() for x in zapas.split(" - ", 1)]
    for v in vysledky:
        if sport and v["sport"] != sport:
            continue
        if shoda_tymu(dom, v["home"]) and shoda_tymu(hos, v["away"]):
            return v
    return None
