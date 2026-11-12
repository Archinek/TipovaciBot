"""Sonda zdrojů VÝSLEDKŮ (pro učení bota): uloží ukázky odpovědí, ať vidíme skutečný tvar, než napíšeme čtečky.

Zdroje: Teletext ČT (Tipsport – aktuální výsledky), NHL api-web (skóre, střely, boxscore), NFL (nflverse games.csv z GitHubu:
výsledky, spready, totaly, rozhodčí, počasí, odpočinek), NBA (oficiální CDN scoreboard). ESPN z GitHubu vrací 403, proto není.
Do data/probe_vysledky/ se uloží začátek každé odpovědi (u teletextu i adresy nalezené ve skriptech stránky).
Nic se neposílá ani nesází; jen se čte.
"""
import datetime
import json
import re
import urllib.error
import urllib.parse
import urllib.request

from . import config

ZDROJE = {
    "nhl_score_now": "https://api-web.nhle.com/v1/score/now",
    "nfl_games_csv": "https://raw.githubusercontent.com/nflverse/nfldata/master/data/games.csv",
    "tsdb_soccer": "https://www.thesportsdb.com/api/v1/json/3/eventsday.php?d={vcera}&s=Soccer",
    "tsdb_basketball": "https://www.thesportsdb.com/api/v1/json/3/eventsday.php?d={vcera}&s=Basketball",
    "tsdb_icehockey": "https://www.thesportsdb.com/api/v1/json/3/eventsday.php?d={vcera}&s=Ice_Hockey",
    "tsdb_volleyball": "https://www.thesportsdb.com/api/v1/json/3/eventsday.php?d={vcera}&s=Volleyball",
    "tsdb_handball": "https://www.thesportsdb.com/api/v1/json/3/eventsday.php?d={vcera}&s=Handball",
    "tsdb_tennis": "https://www.thesportsdb.com/api/v1/json/3/eventsday.php?d={vcera}&s=Tennis",
    "tsdb_amfootball": "https://www.thesportsdb.com/api/v1/json/3/eventsday.php?d={vcera}&s=American_Football",
    "tsdb_darts": "https://www.thesportsdb.com/api/v1/json/3/eventsday.php?d={vcera}&s=Darts",
    "espn_web_nfl": "https://site.web.api.espn.com/apis/v2/sports/football/nfl/scoreboard",
    "espn_cdn_nfl": "https://cdn.espn.com/core/nfl/scoreboard?xhr=1",
    "nba_stats_cdn": "https://cdn.nba.com/static/json/staticData/scheduleLeagueV2_1.json",
    "balldontlie": "https://api.balldontlie.io/v1/games?dates[]={vcera}",
    "wikipedia_ukazka": "https://en.wikipedia.org/api/rest_v1/page/summary/Association_football",
}
_TT = "https://api-teletext.ceskatelevize.cz/teletext-api/api/v1/pages/text"
_URL_RE = re.compile(r"""["'](https?://[^"'\s]{8,}|/[A-Za-z0-9_./-]*(?:api|teletext|json)[^"'\s]*)["']""")


_BROWSER = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36",
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "cs-CZ,cs;q=0.9,en;q=0.8",
    "Referer": "https://teletext.ceskatelevize.cz/",
    "Origin": "https://teletext.ceskatelevize.cz",
}


def _get(url, timeout=25):
    h = dict(_BROWSER) if "ceskatelevize.cz" in url else {"User-Agent": "TipovaciBot/1.0 (osobni projekt)", "Accept": "*/*"}
    req = urllib.request.Request(url, headers=h)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.status, r.headers.get("Content-Type", ""), r.read().decode("utf-8", "replace")


def _uloz(d, nazev, url, st, ct, body, hlava=8000, konec=0):
    cast = body[:hlava] + (f"\n\n[... konec souboru ...]\n{body[-konec:]}" if konec and len(body) > hlava + konec else "")
    (d / f"{nazev}.txt").write_text(f"{url}\nHTTP {st} {ct} délka {len(body)}\n\n{cast}", encoding="utf-8")


def teletext_api(d, log=print):
    """Teletext ČT data API (stránka volá jen fetch(adresa) bez parametrů). Zkusí tři sady hlaviček; uloží stavy i začátek odpovědi."""
    sady = {
        "prohlizec": dict(_BROWSER),
        "minimum": {"User-Agent": _BROWSER["User-Agent"], "Accept": "*/*"},
        "curl": {"User-Agent": "curl/8.5.0", "Accept": "*/*"},
    }
    radky = []
    for url in (_TT, _TT.rsplit("/", 1)[0]):
        for jm, h in sady.items():
            try:
                req = urllib.request.Request(url, headers=h)
                with urllib.request.urlopen(req, timeout=25) as r:
                    body = r.read().decode("utf-8", "replace")
                    radky.append(f"{url} [{jm}] HTTP {r.status} délka {len(body)}")
                    (d / f"ttapi_ok_{jm}.txt").write_text(f"{url}\n{body[:12000]}", encoding="utf-8")
                    log(f"teletext API [{jm}]: HTTP {r.status}, {len(body)} znaků")
            except Exception as e:
                radky.append(f"{url} [{jm}] {type(e).__name__}: {e}")
                log(f"teletext API [{jm}]: {type(e).__name__}: {e}")
    (d / "ttapi_stavy.txt").write_text("\n".join(radky), encoding="utf-8")


def probe(log=print):
    d = config.DATA / "probe_vysledky"
    d.mkdir(parents=True, exist_ok=True)
    vcera = (datetime.date.today() - datetime.timedelta(days=1)).isoformat()
    teletext_api(d, log)
    for nazev, url in ZDROJE.items():
        url = url.replace("{vcera}", vcera)
        try:
            st, ct, body = _get(url)
        except Exception as e:
            (d / f"{nazev}.txt").write_text(f"{url}\nCHYBA {type(e).__name__}: {e}", encoding="utf-8")
            log(f"{nazev}: CHYBA {type(e).__name__}: {e}")
            continue
        _uloz(d, nazev, url, st, ct, body, konec=3000 if nazev == "nfl_games_csv" else 0)        # uloží se HNED, než se cokoli zpracuje
        log(f"{nazev}: HTTP {st}, {len(body)} znaků ({ct})")
        try:
            if nazev.startswith("teletext"):                       # stránka se nejspíš skládá skriptem: najdi adresy dat
                nalezeno = set(_URL_RE.findall(body))
                kontext = []
                for src in re.findall(r"""<script[^>]+src=["']([^"']+)""", body)[:12]:
                    try:
                        _, _, js = _get(urllib.parse.urljoin(url, src))
                        nalezeno |= set(_URL_RE.findall(js))
                        for m in re.finditer(r"TELETEXT_API_URL_TEXT|TELETEXT_API_URL\b|TELETEXT_IMAGE_BASE_URL|\.get\(|fetch\(", js):
                            if 'TELETEXT_API_URL="' in js[m.start() - 5: m.end() + 40] or "TELETEXT_IMAGE_BASE_URL=" in js[m.start(): m.end() + 5]:
                                continue
                            kontext.append(f"[{src}] ..." + js[max(0, m.start() - 300): m.end() + 400].replace("\n", " "))
                    except Exception as e:
                        log(f"   skript {src}: {type(e).__name__}")
                (d / f"{nazev}_kontext_api.txt").write_text("\n\n".join(kontext[:60]), encoding="utf-8")
                (d / f"{nazev}_adresy.txt").write_text("\n".join(sorted(nalezeno)[:300]), encoding="utf-8")
                log(f"   nalezeno {len(nalezeno)} adres ve skriptech")
            elif nazev == "nhl_score_now":                         # boxscore jednoho odehraného zápasu (střely, hráči, vyloučení)
                js = json.loads(body)
                st2, ct2, sc = _get(f"https://api-web.nhle.com/v1/score/{js.get('prevDate')}")
                _uloz(d, "nhl_score_prevdate", f"https://api-web.nhle.com/v1/score/{js.get('prevDate')}", st2, ct2, sc, hlava=6000)
                hry = [g for g in json.loads(sc).get("games", []) if g.get("gameState") in ("OFF", "FINAL")]
                if hry:
                    u = f"https://api-web.nhle.com/v1/gamecenter/{hry[0]['id']}/boxscore"
                    st3, ct3, bx = _get(u)
                    _uloz(d, "nhl_boxscore", u, st3, ct3, bx, hlava=9000)
                    log(f"   boxscore {hry[0]['id']}: HTTP {st3}, {len(bx)} znaků")
        except Exception as e:
            log(f"   {nazev}: zpracování selhalo: {type(e).__name__}: {e}")


def fortuna_vysledky(log=print):
    """Sonda výsledků Fortuny (v3): API /offer/result/api/v1_0. Už víme: sports?date=, tournament/<id>/matches?date=&overviewMarkets=true
    (skóre a u každého trhu result WINNING/LOSING/VOIDED). Zjišťujeme: výpis turnajů daného sportu a dne, všechny trhy (ne jen přehledové).
    Poctivý User-Agent, pauzy, při 403/429 se končí."""
    from . import fortuna
    d = config.DATA / "probe_vysledky"
    d.mkdir(parents=True, exist_ok=True)
    den = (datetime.date.today() - datetime.timedelta(days=1)).isoformat()
    zaklad = "https://api.ifortuna.cz/offer/result/api/v1_0"
    k = fortuna.Klient(pauza=0.6)

    def stahni(nazev, url):
        try:
            data = k.get(url)
        except fortuna.FortunaBlok as e:
            log(f"⛔ {e}")
            raise
        except Exception as e:
            log(f"⚠️ {nazev}: {type(e).__name__}: {e}")
            (d / f"fortuna_vysl_{nazev}.txt").write_text(f"{url}\nCHYBA {type(e).__name__}: {e}", encoding="utf-8")
            return None
        text = json.dumps(data, ensure_ascii=False, indent=1)
        (d / f"fortuna_vysl_{nazev}.txt").write_text(f"{url}\ndélka {len(text)}\n\n{text[:40000]}", encoding="utf-8")
        log(f"✅ {nazev}: {len(text)} znaků")
        return data

    try:
        sporty = stahni("sporty", f"{zaklad}/sports?date={den}") or []
        tid = "ufo:tour:0w-01n"
        m = stahni("zapasy_prehled", f"{zaklad}/tournament/{tid}/matches?date={den}&overviewMarkets=true") or {}
        fx = (m.get("fixtures") or [{}])[0].get("id") or "ufo:mtch:1xm-02f"
        q = urllib.parse.quote
        varianty = [
            f"fixture/{fx}?date={den}", f"fixture/{fx}/markets?date={den}", f"fixture/{fx}/markets?date={den}&overviewMarkets=false",
            f"fixtures/{fx}?date={den}", f"match/{fx}?date={den}", f"matches/{fx}?date={den}",
            f"tournament/{tid}/matches/{fx}?date={den}", f"tournament/{tid}/match/{fx}?date={den}", f"tournament/{tid}/fixture/{fx}?date={den}",
            f"tournament/{tid}/matches?date={den}&fixtureId={fx}", f"tournament/{tid}/matches?date={den}&overviewMarkets=true&fixtureId={fx}",
            f"tournament/{tid}/matches?date={den}&allMarkets=true", f"tournament/{tid}/matches?date={den}&overviewMarkets=true&allMarkets=true",
            f"tournament/{tid}/markets?date={den}", f"fixture/{fx}/outcomes?date={den}", f"fixture/{fx}/result?date={den}",
        ]
        for i, v in enumerate(varianty):
            stahni(f"v4_{i:02d}", f"{zaklad}/{v}")
    except fortuna.FortunaBlok:
        return
    log("📊 Sonda výsledků Fortuny hotová, soubory fortuna_vysl_*.txt v data/probe_vysledky/ (poslat je).")
