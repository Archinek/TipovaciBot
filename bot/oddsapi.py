"""Tenký klient The Odds API v4 (jen stdlib).

Ceny kreditů (podle dokumentace): /sports a /events zdarma,
/odds = počet marketů x počet regionů, /scores = 1 (2 s daysFrom).
"""
import json
import urllib.error
import urllib.parse
import urllib.request

BASE = "https://api.the-odds-api.com/v4"


class OddsApiChyba(RuntimeError):
    pass


def _iso(dt):
    return dt.strftime("%Y-%m-%dT%H:%M:%SZ")


class OddsApi:
    def __init__(self, klic):
        if not klic:
            raise OddsApiChyba("Chybí ODDS_API_KEY (GitHub Secret).")
        self.klic = klic
        self.zbyva = None
        self.utraceno = 0

    def _get(self, cesta, **params):
        params["apiKey"] = self.klic
        url = f"{BASE}{cesta}?{urllib.parse.urlencode(params)}"
        req = urllib.request.Request(url, headers={"User-Agent": "tipovaci-bot/1.0"})
        try:
            with urllib.request.urlopen(req, timeout=30) as r:
                data = json.load(r)
                h = r.headers
        except urllib.error.HTTPError as e:   # klíč v chybě nikdy nevypisujeme
            raise OddsApiChyba(f"HTTP {e.code} u {cesta}") from None
        except urllib.error.URLError as e:
            raise OddsApiChyba(f"Síťová chyba u {cesta}: {e.reason}") from None
        self.zbyva = h.get("x-requests-remaining", self.zbyva)
        try:
            self.utraceno += int(float(h.get("x-requests-last", 0)))
        except (TypeError, ValueError):
            pass
        return data

    def sports(self):
        return self._get("/sports")

    def events(self, sport_key, od, do):
        return self._get(f"/sports/{sport_key}/events",
                         commenceTimeFrom=_iso(od), commenceTimeTo=_iso(do))

    def odds(self, sport_key, regiony, od=None, do=None, event_ids=None):
        p = {"regions": ",".join(regiony), "markets": "h2h",
             "oddsFormat": "decimal", "dateFormat": "iso"}
        if od and do:
            p["commenceTimeFrom"], p["commenceTimeTo"] = _iso(od), _iso(do)
        if event_ids:
            p["eventIds"] = ",".join(event_ids)
        return self._get(f"/sports/{sport_key}/odds", **p)

    def scores(self, sport_key, dny=3):
        return self._get(f"/sports/{sport_key}/scores", daysFrom=dny, dateFormat="iso")
