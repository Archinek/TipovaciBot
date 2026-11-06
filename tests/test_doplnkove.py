"""Testy modelu doplňkových trhů na SYNTETICKÝCH datech (bez sítě)."""
import datetime
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from bot import config, doplnkove as dp, histdata  # noqa: E402

UTC = datetime.timezone.utc
NAST = config.nacti_cfg()["doplnkove"]


def nb_draw(rng, mu, r):
    return rng.poisson(rng.gamma(r, mu / r))


def synteticka_liga(ucinek_tymu=0.25, ucinek_rozhodciho=0.25, zapasu=760, seed=7):
    rng = np.random.default_rng(seed)
    tymy = [f"T{i}" for i in range(20)]
    att = {v: {t: float(np.exp(rng.normal(0, ucinek_tymu))) for t in tymy} for v in dp.PROMENNE}
    de = {v: {t: float(np.exp(rng.normal(0, ucinek_tymu))) for t in tymy} for v in dp.PROMENNE}
    rozh = {f"R{i}": float(np.exp(rng.normal(0, ucinek_rozhodciho))) for i in range(12)}
    zaklad = {"goly": (1.5, 1.2), "rohy": (5.4, 4.5), "karty": (2.0, 2.3), "fauly": (11.5, 11.5), "sot": (4.8, 4.0)}
    start = datetime.datetime(2024, 8, 1, tzinfo=UTC)
    rows = []
    for i in range(zapasu):
        h, a = rng.choice(tymy, 2, replace=False)
        ref = f"R{rng.integers(12)}"
        den = start + datetime.timedelta(days=int(i * 600 / zapasu))
        # sdílený latentní faktor = korelace mezi trhy
        sdileny = float(np.exp(rng.normal(0, 0.12)))
        y = {}
        for v in dp.PROMENNE:
            mh, ma = zaklad[v]
            f = rozh[ref] if v in dp.S_ROZHODCIM else 1.0
            muh = mh * att[v][h] * de[v][a] * f * sdileny
            mua = ma * att[v][a] * de[v][h] * f * sdileny
            y[v] = (int(nb_draw(rng, muh, 25)), int(nb_draw(rng, mua, 25)))
        rows.append({"datum": den, "home": str(h), "away": str(a), "ref": ref, "y": y})
    return rows


def test_pmf_a_over():
    for mu, r in [(2.7, 1e6), (10.0, 20.0), (24.0, 40.0)]:
        assert abs(dp.pmf_nb(mu, r, 200).sum() - 1) < 1e-6
    p = dp.p_over_linie(10.0, 20.0, [8.5, 9.5, 10.5, 11.5])
    v = [p[L] for L in sorted(p)]
    assert v == sorted(v, reverse=True) and 0 < v[-1] < v[0] < 1


def test_model_pouziva_informaci_a_nepodvadi():
    # 1) data s reálným týmovým efektem: model musí porazit naivní průměr ligy
    rows = synteticka_liga()
    od = datetime.datetime(2025, 5, 1, tzinfo=UTC)
    bt = dp.backtest(rows, NAST, od)
    kladne = [v for v, x in bt.items() if x["zlepseni_pct"] > 0.3]
    assert len(kladne) >= 3, bt
    # 2) data BEZ týmového i rozhodcovského efektu: model nesmí být výrazně horší (smrštění funguje)
    ploche = synteticka_liga(ucinek_tymu=0.0, ucinek_rozhodciho=0.0, seed=11)
    bt0 = dp.backtest(ploche, NAST, od)
    assert all(x["zlepseni_pct"] > -1.5 for x in bt0.values()), bt0


def test_rozhodci_a_korelace():
    rows = synteticka_liga(ucinek_rozhodciho=0.35, seed=3)
    ted = datetime.datetime(2026, 1, 1, tzinfo=UTC)
    model = dp.fit(rows, ted, NAST)
    assert set(model["vars"]) == set(dp.PROMENNE)
    ref = model["var"]["karty"]["ref"]
    assert len(ref) >= 8 and max(ref.values()) / min(ref.values()) > 1.1     # rozhodčí se liší
    assert model["R"][0, 1] > 0.05 or model["R"].max() < 0.99                # kopule je platná matice
    h, a = "T1", "T2"
    sim = dp.simuluj(model, {v: model["var"][v]["mu_liga"] for v in model["vars"]}, 20000)
    j, soucin = dp.cena_builderu(sim, [("karty", 3.5, "over"), ("fauly", 23.5, "over")])
    assert j > 0 and soucin > 0
    assert abs(float(model["R"][0, 0]) - 1) < 1e-6


def test_builder_korelace_se_projevi():
    # ručně nastavená kladná korelace: společná pravděpodobnost > součin marginálů
    model = {"vars": ["karty", "fauly"], "R": np.array([[1, 0.6], [0.6, 1.0]]),
             "var": {"karty": {"r": 30.0}, "fauly": {"r": 40.0}}}
    sim = dp.simuluj(model, {"karty": 4.2, "fauly": 24.0}, 40000, seed=1)
    j, s = dp.cena_builderu(sim, [("karty", 3.5, "over"), ("fauly", 23.5, "over")])
    assert j > s * 1.1, (j, s)
    j2, s2 = dp.cena_builderu(sim, [("karty", 3.5, "over"), ("fauly", 23.5, "under")])
    assert j2 < s2


def test_analyza_zapasu_a_filtry():
    rows = synteticka_liga(seed=5)
    model = dp.fit(rows, datetime.datetime(2026, 1, 1, tzinfo=UTC), NAST)
    res = dp.analyzuj_zapas(model, "T3", "T4", None, NAST)
    assert res and all(NAST["min_kurz"] <= l["min_kurz"] <= NAST["max_kurz"] for l in res["linie"])
    assert dp.analyzuj_zapas(model, "NEZNAMY", "T4", None, NAST) is None
    for b in res["builder"]:
        assert NAST["builder_min_kurz"] <= b["fair"] <= NAST["builder_max_kurz"]


def test_loader_a_mapovani():
    csv = ("Div,Date,Time,HomeTeam,AwayTeam,FTHG,FTAG,FTR,Referee,HF,AF,HC,AC,HY,AY,HR,AR\n"
           "E0,16/08/2025,20:00,Liverpool,Bournemouth,4,2,H,M Oliver,10,12,7,3,1,2,0,0\n"
           "E0,17/08/25,15:00,Man United,Arsenal,0,1,A,A Taylor,11,9,4,6,2,3,1,0\n"
           "E0,18/08/2025,15:00,Chelsea,Fulham,,,,,,,,,,,,\n")
    r = histdata.parsuj(csv)
    assert len(r) == 2 and r[0]["y"]["karty"] == (1, 2) and r[1]["y"]["karty"] == (3, 3)
    assert r[1]["ref"] == "A Taylor" and r[1]["y"]["fauly"] == (11, 9)
    fd = ["Man United", "Man City", "Newcastle", "Nott'm Forest", "Brighton"]
    assert histdata.mapuj("Manchester United", fd) == "Man United"
    assert histdata.mapuj("Newcastle United", fd) == "Newcastle"
    assert histdata.mapuj("Nottingham Forest", fd) == "Nott'm Forest"
    assert histdata.mapuj("Brighton and Hove Albion", fd) == "Brighton"
    assert histdata.mapuj("Neexistující FC", fd) is None


def test_kalibrace():
    rows = [{"p": "0.65", "vysledek": "1"}, {"p": "0.65", "vysledek": "0"},
            {"p": "0.75", "vysledek": "1"}, {"p": "0.9", "vysledek": ""}]
    k = dp.kalibrace(rows)
    assert k["n"] == 3 and k["pasma"][0]["n"] == 2 and k["pasma"][0]["skutecne"] == 0.5


if __name__ == "__main__":
    for n, f in list(globals().items()):
        if n.startswith("test_"):
            f()
            print("✅", n)
