"""Offline testy s falešnými daty ve tvaru odpovědí The Odds API (bez sítě).
Spuštění:  python tests/test_offline.py   (nebo pytest)"""
import datetime
import json
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from bot import config, engine, histdata, main as bm, report, store  # noqa: E402
histdata.nacti_ligu = lambda *a, **k: []     # testy nesmí na síť

UTC = datetime.timezone.utc
TED = datetime.datetime(2026, 11, 4, 7, 0, tzinfo=UTC)      # 08:00 v Praze (zimní čas)
START = TED + datetime.timedelta(hours=10)


def kniha(klic, d, r, a):
    return {"key": klic, "markets": [{"key": "h2h", "outcomes": [
        {"name": "Arsenal", "price": d}, {"name": "Draw", "price": r}, {"name": "Chelsea", "price": a}]}]}


def event(eid="e1", start=START):
    return {"id": eid, "sport_key": "soccer_epl", "home_team": "Arsenal", "away_team": "Chelsea",
            "commence_time": start.strftime("%Y-%m-%dT%H:%M:%SZ"),
            "bookmakers": [kniha("pinnacle", 2.00, 3.60, 3.90), kniha("unibet", 2.25, 3.40, 3.50),
                           kniha("betsson", 2.10, 3.50, 3.60), kniha("nordicbet", 2.12, 3.45, 3.55),
                           kniha("onexbet", 2.15, 3.50, 3.50)]}


class FakeApi:
    zbyva = "400"

    def __init__(self, scores=None):
        self._scores = scores or []

    def sports(self):
        return [{"key": "soccer_epl", "group": "Soccer", "active": True, "has_outrights": False},
                {"key": "soccer_winner", "group": "Soccer", "active": True, "has_outrights": True},
                {"key": "darts_x", "group": "Darts", "active": True, "has_outrights": False}]

    def events(self, k, od, do):
        if k != "soccer_epl":
            return []
        return [{"id": "e1", "home_team": "T3", "away_team": "T4",
                 "commence_time": START.strftime("%Y-%m-%dT%H:%M:%SZ")}]

    def odds(self, k, regiony, od=None, do=None, event_ids=None):
        return [event()]

    def scores(self, k, dny=3):
        return self._scores


def nastav_tmp():
    tmp = Path(tempfile.mkdtemp())
    config.DATA, config.DOCS = tmp / "data", tmp / "docs"
    config.DATA.mkdir()
    config.DOCS.mkdir()
    return tmp


def test_math():
    p = engine.no_vig_power([2.0, 3.6, 3.9])
    assert abs(sum(p) - 1) < 1e-9
    assert engine.min_kurz(0.5, 0.03) == 2.06
    assert engine.kelly_pct(0.5, 2.2, 0.25, 0.02) == 0.02       # strop
    assert engine.vitez({"completed": True, "home_team": "A", "away_team": "B",
                         "scores": [{"name": "A", "score": "1"}, {"name": "B", "score": "1"}]}) == "Draw"


def test_kandidati_a_filtry():
    cfg = config.nacti_cfg()
    scfg = cfg["sporty"]["fotbal"]
    k = engine.najdi_kandidaty(event(), "fotbal", scfg, cfg, TED)
    assert [x["vyber"] for x in k] == ["Arsenal"], k
    assert k[0]["edge"] > 0.05 and k[0]["fair_zdroj"] == "pinnacle" and k[0]["best_kniha"] == "unibet"
    # už začaté nebo příliš vzdálené zápasy se vyřadí
    assert engine.najdi_kandidaty(event(start=TED - datetime.timedelta(minutes=5)), "fotbal", scfg, cfg, TED) == []
    assert engine.najdi_kandidaty(event(start=TED + datetime.timedelta(hours=60)), "fotbal", scfg, cfg, TED) == []
    # bez Pinnacle (tier A) = žádný kandidát
    e = event()
    e["bookmakers"] = [b for b in e["bookmakers"] if b["key"] != "pinnacle"]
    assert engine.najdi_kandidaty(e, "fotbal", scfg, cfg, TED) == []


def test_cely_beh_vyhodnoceni_a_closing():
    nastav_tmp()
    odeslano = []

    def veto_fn(top, cfg):
        return {k["id"]: ("OK", "bez nálezu", "Fakta.") for k in top}

    res = bm.morning(api=FakeApi(), veto_fn=veto_fn, wa_fn=odeslano.append, ted=TED)
    assert len(res["picks"]) == 1 and res["picks"][0]["vyber"] == "Arsenal"
    assert "sázej od" in odeslano[0] and "SLEDOVAT" in odeslano[0]       # výchozí režim = paper
    assert (config.DOCS / "reports" / "2026-11-04.html").exists()
    assert (config.DOCS / "index.html").exists()
    # idempotence: druhý běh téhož dne nic nedělá
    assert bm.morning(api=FakeApi(), veto_fn=veto_fn, wa_fn=odeslano.append, ted=TED) is None
    # mimo ranní okno
    assert bm.morning(api=FakeApi(), ted=TED + datetime.timedelta(hours=6)) is None

    # closing: 30 minut před výkopem
    ted2 = START - datetime.timedelta(minutes=30)
    assert bm.uzaviraci(FakeApi(), config.nacti_cfg(), ted2) == 1
    r = store.nacti()[0]
    assert 0.4 < float(r["closing_fair_p"]) < 0.6

    # vyhodnocení: Arsenal vyhrál 2:1
    sc = [{"id": "e1", "completed": True, "home_team": "Arsenal", "away_team": "Chelsea",
           "scores": [{"name": "Arsenal", "score": "2"}, {"name": "Chelsea", "score": "1"}]}]
    nove = bm.vyhodnot(FakeApi(sc), config.nacti_cfg(), START + datetime.timedelta(hours=5))
    assert len(nove) == 1 and nove[0]["vysledek"] == "win"
    m = store.metriky(store.nacti())
    assert m["n"] == 1 and m["roi_paper"] == 1.25 and m["avg_clv"] is not None
    html = report.sestav_report("2026-11-04", res["picks"], [], "1✅ / 0❌", {"vše": m}, "Europe/Prague")
    assert "Arsenal" in html and "<script" not in html


def test_veto_a_xss():
    nastav_tmp()
    def veto_fn(top, cfg):
        return {k["id"]: ("VETO", "<script>alert(1)</script> chybí brankář", "") for k in top}
    res = bm.morning(api=FakeApi(), veto_fn=veto_fn, wa_fn=lambda t: None, ted=TED)
    assert res["picks"] == [] and len(res["vyrazene"]) == 1
    html = (config.DOCS / "reports" / "2026-11-04.html").read_text(encoding="utf-8")
    assert "<script>alert" not in html and "&lt;script&gt;" in html


def test_doplnkove_integrace():
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    import test_doplnkove as td
    from bot import doplnkove as dp
    nastav_tmp()
    rows = td.synteticka_liga(seed=21)
    histdata.nacti_ligu = lambda *a, **k: rows          # syntetická "historie ligy"
    odeslano = []
    ver = lambda top, cfg: {k["id"]: ("OK", "", "") for k in top}
    res = bm.morning(api=FakeApi(), veto_fn=ver, wa_fn=odeslano.append, ted=TED)
    assert res is not None
    html = (config.DOCS / "reports" / "2026-11-04.html").read_text(encoding="utf-8")
    assert "Doplňkové trhy" in html and "Sázej od" in html and "T3 vs T4" in html
    assert "DOPLŇKOVÉ TRHY" in odeslano[0] and "od *" in odeslano[0]
    log = dp.nacti_log()
    assert len(log) > 0 and all(r["vysledek"] == "" for r in log)
    # vyhodnocení: zápas T3-T4 "odehraný" včera, výsledek známe z falešné historie
    r0 = log[0]
    hr = {"datum": datetime.datetime(2026, 11, 4, 17, tzinfo=UTC), "home": "T3", "away": "T4", "ref": "",
          "y": {"goly": (2, 1), "rohy": (6, 5), "karty": (2, 3), "fauly": (12, 13)}}
    hotovo = dp.vyhodnot_log(lambda kod: [hr], TED + datetime.timedelta(days=1))
    assert hotovo == len(log)
    assert all(r["vysledek"] in ("0", "1") for r in dp.nacti_log())
    assert dp.kalibrace(dp.nacti_log())["n"] == len(log)
    # CLI příkazy nespadnou
    bm.builder_cmd("soccer_epl|T3|T4|karty>3.5,fauly>23.5|2.4")
    bm.backtest_cmd("E0")


if __name__ == "__main__":
    for n, f in list(globals().items()):
        if n.startswith("test_"):
            f()
            print("✅", n)
