"""Test porovnání nabídky Fortuny s modelem na syntetické lize (bez sítě)."""
import datetime
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from bot import config, doplnkove as dp, fortuna_hodnota as fh  # noqa: E402
from test_doplnkove import synteticka_liga  # noqa: E402

TED = datetime.datetime(2026, 1, 1, tzinfo=datetime.timezone.utc)
ROWS = synteticka_liga()
for r in ROWS:
    r["datum"] = r["datum"].replace(year=2025)


def _cfg():
    c = config.nacti_cfg()
    c["fortuna"] = {**(c.get("fortuna") or {}), "vaha_modelu": 0.5, "min_edge": 0.03, "min_kurz": 1.4,
                    "max_kurz": 2.6, "max_rozchod": 0.12, "max_tipu": 10}
    return c


def _zapas(nazev, h, a, nohy, turnaj="1. Anglie"):
    return {"id": nazev, "nazev": nazev, "home": h, "away": a, "start": "2026-01-02T15:00:00+00:00",
            "sport": "fotbal", "turnaj": turnaj, "kategorie": "anglie", "nohy": nohy}


def _dvojice(L, p_trh, marze=1.03):
    return [{"trh": "goly", "linie": L, "strana": "over", "kurz": round(1 / (p_trh * marze), 2)},
            {"trh": "goly", "linie": L, "strana": "under", "kurz": round(1 / ((1 - p_trh) * marze), 2)}]


def test_hodnota():
    cfg = _cfg()
    m = dp.fit(ROWS, TED, cfg["doplnkove"])
    pm = fh.p_nohy(m, "T3", "T7", {"trh": "goly", "linie": 2.5, "strana": "over"})
    assert 0.2 < pm < 0.9
    zap = [
        _zapas("T3 - T7", "T3", "T7", _dvojice(2.5, pm - 0.10)),                         # trh levnější než model -> over má hranu
        _zapas("T1 - T2", "T1", "T2", _dvojice(2.5, pm - 0.10) if False else _dvojice(2.5, 0.5)),   # shodný trh, žádná hrana
        _zapas("Nikdo - Nikdo2", "Nikdo", "Nikdo2", _dvojice(2.5, 0.4)),                 # nespárováno
        {**_zapas("Esport A - B", "T3", "T7", _dvojice(2.5, 0.3)), "turnaj": "Esports Battle (2x4 min.)"},
        _zapas("T4 - T9", "T4", "T9", _dvojice(2.5, 0.99)),                              # absurdní rozchod -> zahodit
    ]
    # kurzy musí být v povoleném pásmu; over u T3-T7 s p_trh=pm-0.1
    out = fh.vyhodnot(zap, cfg, TED, log=lambda *a: None, nacti_model=lambda kod: ROWS if kod == "E0" else [])
    assert out, "měla by vzniknout aspoň jedna hrana"
    assert all(o["zapas"] == "T3 - T7" for o in out), [o["zapas"] for o in out]
    o = out[0]
    assert o["strana"] == "over" and o["edge"] >= 0.03 and o["sazej_od"] > 1.0
    assert o["kurz_fortuna"] * o["p"] - 1 > 0.029 and abs(o["p"] - (0.5 * o["p_model"] + 0.5 * o["p_trh"])) < 1e-3
    assert o["sazej_od"] * o["p"] >= 1.03 - 1e-6


def test_btts_a_tym():
    cfg = _cfg()
    m = dp.fit(ROWS, TED, cfg["doplnkove"])
    for n in ({"trh": "btts", "strana": "ano"}, {"trh": "goly_dom", "linie": 1.5, "strana": "over"},
              {"trh": "goly_hos", "linie": 0.5, "strana": "under"}, {"trh": "rohy", "linie": 9.5, "strana": "over"}):
        p = fh.p_nohy(m, "T3", "T7", n)
        assert p is not None and 0 < p < 1, n
    assert fh.p_nohy(m, "T3", "T7", {"trh": "1x2", "strana": "1"}) is None             # 1X2 záměrně nemodelujeme


def test_analyza_a_report():
    import json
    from bot import analyza, report
    cfg = _cfg()
    m = dp.fit(ROWS, TED, cfg["doplnkove"])
    pm = fh.p_nohy(m, "T3", "T7", {"trh": "goly", "linie": 2.5, "strana": "over"})
    zap = [_zapas("T3 - T7", "T3", "T7", _dvojice(2.5, pm - 0.10))]
    out = fh.vyhodnot(zap, cfg, TED, log=lambda *a: None, nacti_model=lambda kod: ROWS if kod == "E0" else [])
    assert out and out[0]["data"]["rozhodci_v_lize"] and out[0]["data"]["domaci"]["zapasu"] == 10
    # bez Gemini: analýza z dat, NEOVERENO
    import os; os.environ.pop("GEMINI_API_KEY", None)
    ok, vet = analyza.rozsir([dict(o) for o in out], cfg)
    assert len(ok) == len(out) and ok[0]["analyza"]["verdikt"] == "NEOVERENO" and not vet
    # s falešným Gemini: VETO vyřadí, OK nechá
    def fake(prompt):
        assert "FOTBAL:" in prompt and "rozhodci_v_lize" in prompt and "T3 - T7" in prompt and "rozhodci_vliv" in prompt
        return "```json\n" + json.dumps({"vysledky": [{"id": "T3 - T7", "verdikt": "VETO", "duvod": "Chybí brankář"}]}) + "\n```"
    ok, vet = analyza.rozsir([dict(o) for o in out], cfg, vola_gemini=fake)
    assert not ok and len(vet) == len(out)
    def fake2(prompt):
        return json.dumps({"vysledky": [{"id": "T3 - T7", "verdikt": "OK", "duvod": "Vše sedí", "souhrn": "Text.",
                                         "rozhodci": {"jmeno": "R2", "stav": "nalezeno", "statistika": "6.5 žlutých", "dopad": "víc karet"},
                                         "pro": ["a"], "proti": ["b"], "riziko": "r", "komentare_k_trhum": []}]})
    ok, _ = analyza.rozsir([dict(o) for o in out], cfg, vola_gemini=fake2)
    html = report._tab_fortuna(ok, "Europe/Prague")
    assert "R2" in html and "Vše sedí" in html and "T3 - T7" in html
    wa = "\n".join(report._wa_fortuna(ok))
    assert "T3 - T7" in wa and "sázej od" in wa.lower()


def test_h2h_vsechny_sporty():
    import json
    from bot import analyza, fortuna, mojekurzy, report
    cfg = _cfg()
    # Fortuna: tenisový vítěz (obráceně seřazení hráči) + fotbal 1X2
    tenis = {"marketTypeName": "Vítěz zápasu", "syntheticGroupKey": "winner", "outcomes": [
        {"name": "1", "longName": "Novak D.", "odds": 1.8}, {"name": "2", "longName": "Rune H.", "odds": 2.0}]}
    z = [{"home": "Novak D.", "away": "Rune H.", "sport": "tenis", "nohy": fortuna.nohy_zapasu([tenis])}]
    rows = fortuna.radky_pro_mojekurzy(z)
    assert {r["vyber"] for r in rows} == {"Novak D.", "Rune H."}
    picks = [{"zapas": "Rune H. vs Novak D.", "sport": "tenis", "vyber": "Rune H.", "fair_p": 0.55, "min_kurz": 1.87,
              "start": "2026-11-07T10:00:00+00:00", "tier": "A", "stake_pct": 1, "rezim": "paper", "veto": "OK", "riziko": "",
              "fair_kurz": 1.82, "best_kurz": 2.0, "best_kniha": "pinnacle", "veto_duvod": "", "edge": 0.0}]
    assert mojekurzy.aplikuj(picks, [], cfg, extra=rows) == 1 and picks[0]["moje_kurz"] == 2.0
    assert "Fortuna" in picks[0]["moje_info"] and "vyplatí" in picks[0]["moje_info"]
    sporty_v_promptu = []
    def fake(prompt):
        sporty_v_promptu.append(prompt)
        return json.dumps({"vysledky": [{"id": "Rune H. vs Novak D.", "verdikt": "OK", "duvod": "sedí", "souhrn": "Souhrn.",
                          "faktory": [{"kriterium": "povrch_kurtu", "zjisteni": "tvrdý", "stav": "nalezeno", "dopad": "+ sedí"}],
                          "pro": ["a"], "proti": ["b"], "riziko": "r"}]})
    ok, vet = analyza.rozsir(picks, cfg, vola_gemini=fake, max_zapasu=5)
    assert len(ok) == 1 and not vet and "TENIS:" in sporty_v_promptu[0]
    html = report._tab_picks(ok, "Europe/Prague")
    wa = report.wa_ranni("2026-11-07", ok, "", "", "Europe/Prague")
    assert "povrch kurtu" in html, html[-600:]
    assert len(wa) < 200 and "Souhrn." not in wa


if __name__ == "__main__":
    test_hodnota(); test_btts_a_tym(); test_analyza_a_report(); test_h2h_vsechny_sporty(); print("✅ test_fortuna_hodnota")
