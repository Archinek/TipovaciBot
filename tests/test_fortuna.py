"""Test stahování nabídky Fortuny na falešném klientovi (bez sítě)."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from bot import fortuna  # noqa: E402


class Fake:
    pocet = 0
    def __init__(self, blok_po=None): self.n, self.blok_po = 0, blok_po
    def get(self, url):
        self.n += 1
        if self.blok_po and self.n > self.blok_po:
            raise fortuna.FortunaBlok("403")
        if "/tournaments" in url:
            return [{"id": "t1", "name": "Premier League", "sportSeoName": "fotbal", "features": ["MATCHES"],
                     "filters": ["today", "all"]},
                    {"id": "t2", "name": "Rusko", "features": ["MATCHES"], "filters": ["tomorrow"]},      # bez 'today' -> přeskočit
                    {"id": "t3", "name": "Volby", "features": ["RACES"], "filters": ["today"]}]           # politika -> přeskočit
        if "/tournament/t3/" in url or ("/tournament/t2/" in url and "timeFilter=today" in url):
            raise AssertionError("tyhle turnaje se vůbec nemají volat")
        if "/tournament/t2/" in url:
            return []                                              # zítra: nic
        if "/matches" in url:
            return [{"id": "f1", "name": "Chelsea - Arsenal", "kind": "PREMATCH", "status": "ACTIVE", "hasMarkets": True,
                     "startDatetime": 1793982540000,
                     "participants": [{"type": "AWAY", "name": "Arsenal"}, {"type": "HOME", "name": "Chelsea"}]},
                    {"id": "f1", "name": "duplicita - x", "kind": "PREMATCH", "status": "ACTIVE", "hasMarkets": True},
                    {"id": "f2", "name": "Live - Zapas", "kind": "LIVE", "status": "ACTIVE", "hasMarkets": True}]
        return [{"name": "Počet žlutých karet", "marketTypeName": "Over/Under",
                 "outcomes": [{"name": "Více než 4.5", "odds": 1.85}, {"name": "Méně než 4.5", "odds": 1.9}]},
                {"name": "Barva dresů", "outcomes": [{"name": "A", "odds": 3.0}]}]


def test_nabidka():
    z = fortuna.nabidka(Fake(), filtry=("today", "tomorrow"), log=lambda *a: None)
    assert len(z) == 1 and z[0]["home"] == "Chelsea" and z[0]["away"] == "Arsenal" and z[0]["sport"] == "fotbal"
    assert z[0]["start"].startswith("2026-11-0")
    assert len(z[0]["trhy"]) == 1 and z[0]["trhy"][0]["vysledky"][0]["kurz"] == 1.85    # nezajímavý trh pryč


def test_blok_konci():
    try:
        fortuna.nabidka(Fake(blok_po=2), filtry=("today",), log=lambda *a: None)
        assert False, "měl skončit"
    except fortuna.FortunaBlok:
        pass


if __name__ == "__main__":
    test_nabidka(); test_blok_konci(); print("✅ test_fortuna")


def _real(n):
    import json
    return json.loads((Path(__file__).parent / "data" / f"fortuna_trhy_{n}.json").read_text(encoding="utf-8"))


def test_parser_skutecne_trhy():
    n = fortuna.nohy_zapasu(_real(1))
    def najdi(trh, strana, L=None):
        return [x for x in n if x["trh"] == trh and x["strana"] == strana and x["linie"] == L]
    assert najdi("1x2", "1")[0]["kurz"] == 3.8 and najdi("1x2", "2")[0]["kurz"] == 1.72
    assert najdi("goly", "over", 2.5)[0]["kurz"] == 1.64 and najdi("goly", "under", 2.5)[0]["kurz"] == 1.96
    assert not najdi("goly", "over", 1.0) and not najdi("goly", "over", 4.0)          # celočíselné linie se přeskakují
    assert najdi("btts", "ano")[0]["kurz"] == 1.64
    assert najdi("goly_dom", "over", 2.5)[0]["kurz"] == 6.0                           # Grulla Morioka (1. tým)
    assert najdi("goly_hos", "over", 2.5)[0]["kurz"] == 3.05                          # Okinawa SV (2. tým)
    assert najdi("goly_1p", "over", 2.5)[0]["kurz"] == 4.9
    assert najdi("dnb", "1") and najdi("dc", "10")
    assert not [x for x in n if "poločas" in str(x)]                                  # výsledek poločasů apod. se nebere
    m2 = fortuna.nohy_zapasu(_real(2))
    assert any(x["trh"] == "goly" and x["linie"] == 3.5 and x["kurz"] == 2.16 for x in m2)


def test_celkove_trhy_top_zapasu():
    def trh(nazev, hranice):
        return {"marketTypeName": nazev, "syntheticGroupKey": "x", "outcomes": [
            {"name": f"Více než {hranice}", "longName": f"Více než {hranice}", "odds": 1.9},
            {"name": f"Méně než {hranice}", "longName": f"Méně než {hranice}", "odds": 1.9}]}
    for nazev, ocekavano in (("Počet rohových kopů v zápasu", "rohy"), ("Počet faulů v zápasu", "fauly"),
                             ("Počet žlutých karet v zápasu (Nepočítá se - druhá ŽK pro hráče)", "karty")):
        n = fortuna.parsuj_trh(trh(nazev, 9.5))
        assert {x["trh"] for x in n} == {ocekavano}, nazev
    for nazev in ("Cracovia počet rohových kopů v zápasu", "Počet rohových kopů v 1. poločasu", "Hráč - počet faulů"):
        assert fortuna.parsuj_trh(trh(nazev, 4.5)) == [], nazev           # týmové / poločasové / hráčské netvrdíme jako celkové


def test_virtualni():
    assert fortuna.je_virtualni({"turnaj": "Esports Battle - Liga mistrů (2x4 min.)"})
    assert not fortuna.je_virtualni({"turnaj": "Japonsko - Football League", "kategorie": "japonsko"})


if __name__ == "__main__":
    test_parser_skutecne_trhy(); test_celkove_trhy_top_zapasu(); test_virtualni(); print("✅ test_fortuna (parser)")
