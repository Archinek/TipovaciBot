"""Sonda zdrojů VÝSLEDKŮ (pro učení bota): uloží ukázky odpovědí, ať vidíme skutečný tvar, než napíšeme čtečky.

Zdroje: Teletext ČT (Tipsport – aktuální výsledky), NHL api-web (skóre, střely, boxscore), NFL (nflverse games.csv z GitHubu:
výsledky, spready, totaly, rozhodčí, počasí, odpočinek), NBA (oficiální CDN scoreboard). ESPN z GitHubu vrací 403, proto není.
Do data/probe_vysledky/ se uloží začátek každé odpovědi (u teletextu i adresy nalezené ve skriptech stránky).
Nic se neposílá ani nesází; jen se čte.
"""
import json
import re
import urllib.error
import urllib.parse
import urllib.request

from . import config

ZDROJE = {
    "teletext_751-1": "https://teletext.ceskatelevize.cz/?p=751-1",
    "teletext_760-2": "https://teletext.ceskatelevize.cz/?p=760-2",
    "ttapi_pages": "https://api-teletext.ceskatelevize.cz/teletext-api/api/v1/pages",
    "ttapi_text_a": "https://api-teletext.ceskatelevize.cz/teletext-api/api/v1/pages/text?page=751&subpage=1",
    "ttapi_text_b": "https://api-teletext.ceskatelevize.cz/teletext-api/api/v1/pages/text?pageNumber=751&subPageNumber=1",
    "ttapi_text_c": "https://api-teletext.ceskatelevize.cz/teletext-api/api/v1/pages/text?p=751-1",
    "ttapi_pages_a": "https://api-teletext.ceskatelevize.cz/teletext-api/api/v1/pages?page=751&subpage=1",
    "ttapi_pages_751": "https://api-teletext.ceskatelevize.cz/teletext-api/api/v1/pages/751",
    "ttapi_pages_751_1": "https://api-teletext.ceskatelevize.cz/teletext-api/api/v1/pages/751/1",
    "nhl_score_now": "https://api-web.nhle.com/v1/score/now",
    "nfl_games_csv": "https://raw.githubusercontent.com/nflverse/nfldata/master/data/games.csv",
    "nba_scoreboard": "https://cdn.nba.com/static/json/liveData/scoreboard/todaysScoreboard_00.json",
}
_URL_RE = re.compile(r"""["'](https?://[^"'\s]{8,}|/[A-Za-z0-9_./-]*(?:api|teletext|json)[^"'\s]*)["']""")


def _get(url, timeout=25):
    req = urllib.request.Request(url, headers={"User-Agent": "TipovaciBot/1.0 (osobni projekt)", "Accept": "*/*"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.status, r.headers.get("Content-Type", ""), r.read().decode("utf-8", "replace")


def _uloz(d, nazev, url, st, ct, body, hlava=8000, konec=0):
    cast = body[:hlava] + (f"\n\n[... konec souboru ...]\n{body[-konec:]}" if konec and len(body) > hlava + konec else "")
    (d / f"{nazev}.txt").write_text(f"{url}\nHTTP {st} {ct} délka {len(body)}\n\n{cast}", encoding="utf-8")


def probe(log=print):
    d = config.DATA / "probe_vysledky"
    d.mkdir(parents=True, exist_ok=True)
    for nazev, url in ZDROJE.items():
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
                        for m in re.finditer(r"teletext-api|api/v1/pages|subpage|subPage", js):
                            kontext.append(f"[{src}] ..." + js[max(0, m.start() - 300): m.end() + 400].replace("\n", " "))
                    except Exception as e:
                        log(f"   skript {src}: {type(e).__name__}")
                (d / f"{nazev}_kontext_api.txt").write_text("\n\n".join(kontext[:25]), encoding="utf-8")
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
