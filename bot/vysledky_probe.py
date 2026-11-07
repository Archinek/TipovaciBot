"""Sonda zdrojů VÝSLEDKŮ (pro učení bota): uloží ukázky odpovědí, ať vidíme skutečný tvar, než napíšeme čtečky.

Zdroje: Teletext ČT (stránky Tipsport – aktuální výsledky, 751 a dál), veřejné JSON ESPN (NFL, NBA, NHL) a NHL api-web.
Do data/probe_vysledky/ se uloží začátek každé odpovědi (a u teletextu i adresy nalezené ve skriptech stránky).
Nic se tím neposílá a nic se nesází; jen se čte.
"""
import re
import urllib.error
import urllib.request

from . import config

ZDROJE = {
    "teletext_751-1": "https://teletext.ceskatelevize.cz/?p=751-1",
    "teletext_760-2": "https://teletext.ceskatelevize.cz/?p=760-2",
    "espn_nfl": "https://site.api.espn.com/apis/site/v2/sports/football/nfl/scoreboard",
    "espn_nba": "https://site.api.espn.com/apis/site/v2/sports/basketball/nba/scoreboard",
    "espn_nhl": "https://site.api.espn.com/apis/site/v2/sports/hockey/nhl/scoreboard",
    "nhl_score_now": "https://api-web.nhle.com/v1/score/now",
}


def _get(url, timeout=25):
    req = urllib.request.Request(url, headers={"User-Agent": "TipovaciBot/1.0 (osobni projekt)", "Accept": "*/*"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.status, r.headers.get("Content-Type", ""), r.read().decode("utf-8", "replace")


def probe(log=print):
    d = config.DATA / "probe_vysledky"
    d.mkdir(parents=True, exist_ok=True)
    for nazev, url in ZDROJE.items():
        try:
            st, ct, body = _get(url)
            (d / f"{nazev}.txt").write_text(f"{url}\nHTTP {st} {ct} délka {len(body)}\n\n{body[:8000]}", encoding="utf-8")
            log(f"{nazev}: HTTP {st}, {len(body)} znaků ({ct})")
            if nazev.startswith("teletext"):                           # stránka se nejspíš skládá skriptem: najdi adresy dat
                nalezeno = set(re.findall(r"""["'](https?://[^"'\\s]+|/[A-Za-z0-9_\\-./]*(?:api|teletext|json)[^"'\\s]*)["']""", body))
                for src in re.findall(r"""<script[^>]+src=["']([^"']+)""", body)[:6]:
                    try:
                        u = src if src.startswith("http") else urllib.request.urljoin(url, src)
                        _, _, js = _get(u)
                        nalezeno |= set(re.findall(r"""["'](https?://[^"'\\s]{8,}|/[A-Za-z0-9_\\-./]*(?:api|teletext|json)[^"'\\s]*)["']""", js))
                    except Exception as e:
                        log(f"   skript {src}: {type(e).__name__}")
                (d / f"{nazev}_adresy.txt").write_text("\n".join(sorted(nalezeno)[:300]), encoding="utf-8")
                log(f"   nalezeno {len(nalezeno)} adres ve skriptech")
        except Exception as e:
            (d / f"{nazev}.txt").write_text(f"{url}\nCHYBA {type(e).__name__}: {e}", encoding="utf-8")
            log(f"{nazev}: CHYBA {type(e).__name__}: {e}")
