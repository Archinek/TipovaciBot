"""Testy: tenisový model es, parser trhů es/střel, tip dne, log kurzů (CLV, Brier). Bez sítě, syntetická data."""
import datetime
import math
import random
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from bot import config, fortuna, fortuna_hodnota as fh, fortuna_log as fl, tenis, tipsteri  # noqa: E402

UTC = datetime.timezone.utc
TED = datetime.datetime(2026, 11, 6, 9, tzinfo=UTC)
JMENA = [("Samuele", "Pieri"), ("Sergi", "Perez Contri"), ("Janice", "Tjen"), ("Polina", "Kudermetova"), ("Mai", "Hontama"),
         ("Magda", "Linette"), ("Luca", "Van Assche"), ("Rinky", "Hijikata"), ("Ben", "Shelton"), ("Tommy", "Paul"),
         ("Quentin", "Halys"), ("Arthur", "Fils"), ("Mark", "Taylor"), ("Adam", "Novak"), ("Karel", "Dvorak"), ("Jan", "Svoboda")]


def _liga(seed=7, n=2500, pravda=None):
    """Hráči s PRAVDIVOU silou podání a returnu; esa ~ Poisson(podání × 0.07 × s × r)."""
    rnd = random.Random(seed)
    hraci = [f"{a} {b}" for a, b in JMENA]
    if pravda:
        s, r = pravda
    else:
        s = {h: math.exp(rnd.gauss(0, 0.40)) for h in hraci}
        r = {h: math.exp(rnd.gauss(0, 0.15)) for h in hraci}
    rows = []
    for i in range(n):
        a, b = rnd.sample(hraci, 2)
        sv = rnd.randint(60, 110)
        ya = _pois(rnd, sv * 0.07 * s[a] * r[b])
        yb = _pois(rnd, sv * 0.07 * s[b] * r[a])
        w, l = (a, b) if rnd.random() < 0.5 else (b, a)
        ace = {a: ya, b: yb}
        rows.append({"datum": TED - datetime.timedelta(days=1 + (i * 600) // n), "turnaj": "Challenger Brisbane" if i % 3 else "ATP Madrid",
                     "povrch": "hard" if i % 3 else "clay", "bo": 3, "w": w, "l": l, "ace_w": ace[w], "ace_l": ace[l],
                     "sv_w": sv, "sv_l": sv})
    rows.sort(key=lambda x: x["datum"])
    return rows, s, r


def _pois(rnd, mu):
    L, k, p = math.exp(-mu), 0, 1.0
    while True:
        p *= rnd.random()
        if p <= L:
            return k
        k += 1


def test_csv_a_jmena():
    csvtxt = ("tourney_name,surface,tourney_date,best_of,winner_name,loser_name,w_ace,l_ace,w_svpt,l_svpt\n"
              "Brisbane,Hard,20260105,3,Samuele Pieri,Sergi Perez Contri,7,3,70,66\n"
              "Brisbane,Hard,20260105,3,Janice Tjen,Polina Kudermetova,,2,70,66\n"      # chybí statistika -> zahodit
              "Brisbane,Hard,20260106,3,Mai Hontama,Magda Linette,4,5,10,12\n")           # retirement (málo podání) -> zahodit
    rows = tenis.parsuj(csvtxt)
    assert len(rows) == 1 and rows[0]["w"] == "Samuele Pieri" and rows[0]["povrch"] == "hard"
    hraci = {h: set(tenis._tokeny(h)) for h in ("Samuele Pieri", "Sergi Perez Contri", "Tommy Paul", "Taylor Fritz", "Tommy Robredo")}
    assert tenis.najdi_hrace("Pieri Samuele", hraci) == "Samuele Pieri"
    assert tenis.najdi_hrace("S.Pieri", hraci) == "Samuele Pieri"
    assert tenis.najdi_hrace("Perez Contri Sergi", hraci) == "Sergi Perez Contri"
    assert tenis.najdi_hrace("Paul Tommy", hraci) == "Tommy Paul"
    assert tenis.najdi_hrace("Nikdo Neznamy", hraci) is None
    assert tenis.najdi_hrace("T. Paul", {**hraci, "Tom Paul": {"tom", "paul"}}) is None     # nejednoznačné -> raději nic


def test_model_es():
    rows, pravda, odolnost = _liga()
    m = tenis.fit(rows, TED)
    assert m and m["k_hrac"] >= 3
    hraci = list(pravda)
    # odhadnutá síla podání musí korelovat s pravdou
    xs, ys = [pravda[h] for h in hraci], [m["s"][h] for h in hraci]
    mx, my = sum(xs) / len(xs), sum(ys) / len(ys)
    kor = sum((x - mx) * (y - my) for x, y in zip(xs, ys)) / math.sqrt(sum((x - mx) ** 2 for x in xs) * sum((y - my) ** 2 for y in ys))
    assert kor > 0.9, kor
    silny, slaby = max(hraci, key=lambda h: pravda[h]), min(hraci, key=lambda h: pravda[h])
    stredni = sorted(hraci, key=lambda h: pravda[h])[len(hraci) // 2]
    a = tenis.predikuj(m, silny, stredni, "hard", 3)
    b = tenis.predikuj(m, slaby, stredni, "hard", 3)
    assert a["a"] > b["a"] * 1.5 and a["celkem"] > b["celkem"]
    na = {"trh": "esa_hrac", "linie": 5.5, "strana": "over", "hrac": silny}
    r1 = tenis.p_nohy(m, na, silny, stredni, "hard", 3)
    r2 = tenis.p_nohy(m, na, slaby, stredni, "hard", 3) if False else tenis.p_nohy(m, {**na, "hrac": slaby}, slaby, stredni, "hard", 3)
    assert r1["p"] > r2["p"] and r1["hrac_fd"] == silny
    # over + under = 1, neznámý hráč -> None
    po = tenis.p_nohy(m, {"trh": "esa", "linie": 9.5, "strana": "over"}, silny, stredni, "hard", 3)["p"]
    pu = tenis.p_nohy(m, {"trh": "esa", "linie": 9.5, "strana": "under"}, silny, stredni, "hard", 3)["p"]
    assert abs(po + pu - 1) < 1e-9
    assert tenis.p_nohy(m, {"trh": "esa", "linie": 9.5, "strana": "over"}, "Cizinec Neznamy", stredni) is None
    # kalibrace na nových datech z téhož procesu: průměrná predikce ~ průměr skutečnosti
    novy, _, _ = _liga(seed=99, n=600, pravda=(pravda, odolnost))
    sp = sk = 0.0
    for r in novy:
        if r["w"] in m["n"] and r["l"] in m["n"]:
            mu = tenis.predikuj(m, r["w"], r["l"], r["povrch"], 3)
            if mu:
                sp += mu["celkem"]; sk += r["ace_w"] + r["ace_l"]
    assert 0.9 < sp / sk < 1.1, sp / sk


def _trh(nazev, popis, vysl):
    return {"marketTypeName": nazev, "marketTypeDesc": popis, "syntheticGroupKey": "",
            "outcomes": [{"name": n, "longName": n, "odds": k} for n, k in vysl]}


def test_parser_es_a_strel():
    def dvojice(nazev, popis, L, ko, ku):
        return _trh(nazev, popis, [(f"Více než {L}", ko), (f"Méně než {L}", ku)])
    n = fortuna.parsuj_trh(dvojice("Počet es v zápasu", "", 11.5, 1.9, 1.85))
    assert {x["trh"] for x in n} == {"esa"} and {x["strana"] for x in n} == {"over", "under"}
    n = fortuna.parsuj_trh(dvojice("Počet es Linette v zápasu", "", 3.5, 1.85, 1.9))
    assert {x["trh"] for x in n} == {"esa_hrac"} and n[0]["hrac"] == "linette"
    n = fortuna.parsuj_trh(dvojice("Počet es v zápasu", "1. hráče", 5.5, 1.8, 1.95))
    assert n[0]["trh"] == "esa_hrac" and n[0]["pozice"] == "1"
    assert fortuna.parsuj_trh(dvojice("Počet es v 1. setu", "", 3.5, 1.8, 1.9)) == []                   # sety neřešíme
    assert fortuna.parsuj_trh(dvojice("Počet es v zápasu", "", 11, 1.8, 1.9)) == []                      # celočíselná linie = push
    n = fortuna.parsuj_trh(dvojice("Počet střel na bránu v zápasu", "", 8.5, 1.9, 1.9))
    assert {x["trh"] for x in n} == {"sot"}
    n = fortuna.parsuj_trh(dvojice("Počet střel na bránu v zápasu", "1. týmu", 4.5, 1.9, 1.9))
    assert {x["trh"] for x in n} == {"sot_dom"}
    assert fortuna.parsuj_trh(dvojice("Počet střel na bránu hráče Vignolo", "", 0.5, 1.4, 2.6)) == []     # hráčské střely: bez modelu
    assert fortuna.klic_nohy(n[0]) == "sot_dom|4.5|over|"


def _cfg():
    c = config.nacti_cfg()
    c["fortuna"] = {**c["fortuna"], "vaha_modelu": 0.5, "min_edge": 0.03, "max_rozchod": 0.12, "max_tipu": 10}
    return c


def _dvojka(trh, L, p_over_trh, marze=1.04, **extra):
    return [{"trh": trh, "linie": L, "strana": "over", "kurz": round(1 / (p_over_trh * marze), 2), **extra},
            {"trh": trh, "linie": L, "strana": "under", "kurz": round(1 / ((1 - p_over_trh) * marze), 2), **extra}]


def test_vyhodnot_tenis_a_tip_dne():
    rows, pravda, odolnost = _liga()
    hraci = sorted(pravda, key=lambda h: -pravda[h])
    silny, stredni = hraci[0], hraci[len(hraci) // 2]
    m = tenis.fit(rows, TED)
    # trh podceňuje esa silného podávajícího o 10 procentních bodů -> model vidí hodnotu na Over
    L = next(l for l in (3.5, 4.5, 5.5, 6.5, 7.5, 8.5) if 0.45 < tenis.p_nohy(m, {"trh": "esa_hrac", "linie": l, "strana": "over", "hrac": silny},
                                                                           silny, stredni, "hard", 3)["p"] < 0.7)
    pm = tenis.p_nohy(m, {"trh": "esa_hrac", "linie": L, "strana": "over", "hrac": silny}, silny, stredni, "hard", 3)["p"]
    jm = lambda h: " ".join(reversed(h.split(" ", 1)))                    # Fortuna: "Příjmení Jméno"
    z = {"id": "t1", "nazev": f"{jm(silny)} - {jm(stredni)}", "home": jm(silny), "away": jm(stredni), "start": "2026-11-06T13:00:00+00:00",
         "sport": "tenis", "turnaj": "ATP Challenger Brisbane", "turnaj_popis": "", "kategorie": "", "live": False,
         "nohy": _dvojka("esa_hrac", L, pm - 0.10, pozice="1")}
    out = fh.vyhodnot_tenis([z], _cfg(), TED, log=lambda *a: None, nacti_data=lambda ted: rows)
    over = [c for c in out if c["strana"] == "over"]
    assert over and over[0]["edge"] > 0.03 and over[0]["sazej_od"] > 1.5 and over[0]["typ"] == "esa_hrac"
    assert over[0]["hrac_fd"] == silny and jm(silny) in over[0]["trh"] and over[0]["data"]["povrch"] == "hard"
    assert not [c for c in out if c["strana"] == "under"]
    # tip dne: 1 linie na zápas, max 2 z rodiny, pořadí podle skóre
    base = {"p_model": 0.6, "p_trh": 0.55, "zapas": "", "typ": "esa", "edge": 0.05}
    kand = [{**base, "zapas": "A", "edge": 0.09}, {**base, "zapas": "A", "edge": 0.08},                # stejný zápas
            {**base, "zapas": "B", "edge": 0.07}, {**base, "zapas": "C", "edge": 0.065},               # 3. esa -> rodina plná
            {**base, "zapas": "D", "edge": 0.04, "typ": "fauly"}, {**base, "zapas": "E", "edge": 0.03, "typ": "goly"}]
    tip = tipsteri.tip_dne(kand, config.nacti_cfg())
    assert [t["zapas"] for t in tip] == ["A", "B", "D"] and [t["tip_dne"] for t in tip] == [1, 2, 3]
    assert tip[0]["rodina"] == "Tenis: esa" and all("skore" in c for c in kand)
    # velký rozchod modelu a trhu srazí důvěru (skóre klesne)
    a = tipsteri.skore({**base, "p_model": 0.60, "p_trh": 0.59}, config.nacti_cfg())
    b = tipsteri.skore({**base, "p_model": 0.70, "p_trh": 0.59}, config.nacti_cfg())
    assert a > b > 0


def test_log_clv_brier():
    tmp = Path(tempfile.mkdtemp())
    config.DATA = tmp / "data"
    config.DATA.mkdir()
    start = (TED + datetime.timedelta(hours=6)).isoformat()
    c = {"zapas": "T1 - T2", "zapas_id": "f1", "start": start, "sport": "fotbal", "rodina": "Fotbal: fauly", "kod": "E0",
         "home_fd": "T1", "away_fd": "T2", "typ": "fauly", "linie": 24.5, "strana": "over", "noha_klic": "fauly|24.5|over|",
         "trh": "Fauly: více než 24.5", "kurz_fortuna": 2.10, "p_model": 0.55, "p_trh": 0.50, "p": 0.525, "edge": 0.10}
    c2 = {**c, "zapas_id": "f2", "zapas": "T3 - T4", "home_fd": "T3", "away_fd": "T4", "noha_klic": "goly_dom|1.5|over|", "typ": "goly_dom",
          "linie": 1.5, "kurz_fortuna": 1.9, "p_model": 0.5, "p_trh": 0.5, "p": 0.5}
    assert fl.zaloguj([c, c2], "2026-11-06") == 2 and fl.zaloguj([c, c2], "2026-11-06") == 0       # idempotentní
    # snímek: kurz fauly Over 24.5 klesl z 2.10 na 1.80
    trhy = {"f1": [_trh("Počet faulů v zápasu", "", [("Více než 24.5", 1.80), ("Méně než 24.5", 2.00)])],
            "f2": []}
    n = fl.snimek(None, TED + datetime.timedelta(hours=1), trhy_fn=lambda k, zid: trhy[zid], log=lambda *a: None)
    assert n == 1
    r = {x["zapas_id"]: x for x in fl.nacti()}
    assert float(r["f1"]["kurz_posledni"]) == 1.80 and int(r["f1"]["snimku"]) == 2 and float(r["f1"]["kurz_min"]) == 1.80
    s = fl.souhrn()
    assert s["clv_n"] == 1 and abs(s["clv_prumer"] - (2.10 / 1.80 - 1)) < 1e-3
    # vyhodnocení z historie: T1-T2 mělo 14+13 = 27 faulů (over 24.5 vyšlo), T3-T4 doma dal 1 gól (over 1.5 nevyšlo)
    datum = TED + datetime.timedelta(hours=6)
    hist = [{"datum": datum, "home": "T1", "away": "T2", "ref": "", "y": {"fauly": (14, 13), "goly": (2, 0)}},
            {"datum": datum, "home": "T3", "away": "T4", "ref": "", "y": {"goly": (1, 1)}}]
    assert fl.vyhodnot(lambda kod: hist, TED + datetime.timedelta(days=1)) == 2
    r = {x["zapas_id"]: x for x in fl.nacti()}
    assert r["f1"]["vysledek"] == "1" and r["f2"]["vysledek"] == "0"
    s = fl.souhrn()
    assert s["vyhodnoceno"] == 2 and s["brier_model"] > 0 and abs(s["roi_ploche"] - ((2.10 - 1) - 1) / 2) < 1e-3
    assert "Brier" in fl.souhrn_text(s) and "CLV" in fl.souhrn_text(s)




def test_report_tip_dne():
    from bot import report
    f = {"zapas": "A - B", "home": "A", "away": "B", "start": "2026-11-06T13:00:00+00:00", "liga": "Liga <x>", "trh": "Esa hráče A: více než 5.5",
         "typ": "esa_hrac", "kurz_fortuna": 2.0, "p_model": 0.58, "p_trh": 0.52, "p": 0.55, "edge": 0.10, "sazej_od": 1.87,
         "fair": 1.82, "mu": 6.1, "tip_dne": 1, "jistejsi": 1, "vklad_pct": 0.9, "rodina": "Tenis: esa", "skore": 0.1, "sport": "tenis"}
    html = report.sestav_report("2026-11-06", [], [], "", {"vše": {"n": 0}}, "Europe/Prague", fort=[f])
    assert "Tip dne" in html and "Liga &lt;x&gt;" in html and "Liga <x>" not in html
    txt = report.wa_ranni("2026-11-06", [], "", "", "Europe/Prague", fort=[f], log_text="📊 Log Fortuny: 1 linií")
    assert "TIP DNE" in txt and "od *1.87*" in txt and "Log Fortuny" in txt and "JISTĚJŠÍ" in txt and "vklad ~0.9 %" in txt
    assert "Dnes žádný kandidát" in report.sestav_report("2026-11-06", [], [], "", {"vše": {"n": 0}}, "Europe/Prague", fort=[])


def test_jistejsi_a_vklad():
    cfg = config.nacti_cfg()
    zakl = {"p_model": 0.66, "p_trh": 0.63, "typ": "esa", "kurz_fortuna": 1.70, "p": 0.645, "edge": 0.097, "zapas": "A"}
    kand = [{**zakl}, {**zakl, "zapas": "B", "p": 0.60, "edge": 0.03, "kurz_fortuna": 1.75},
            {**zakl, "zapas": "C", "p": 0.45, "edge": 0.20, "kurz_fortuna": 2.8},            # velká hrana, ale nízká úspěšnost -> ne mezi jistější
            {**zakl, "zapas": "D", "p": 0.62, "edge": 0.01}]                                   # hrana pod prahem
    tip = tipsteri.tip_dne(kand, cfg, n=1)
    assert [t["zapas"] for t in tip] == ["C"]                       # tip dne = největší hrana × důvěra
    js = sorted((c for c in kand if c.get("jistejsi")), key=lambda c: c["jistejsi"])
    assert [c["zapas"] for c in js] == ["A", "B"]                   # jistější: C je v tip dne a má nízké p, D nízkou hranu
    assert all(0 < c["vklad_pct"] <= 2.0 for c in kand)
    assert kand[0]["vklad_pct"] == round(min(2.0, 0.25 * 0.097 / 0.70 * 100), 2)


def test_dvojchyby_a_under_nula():
    rows, pravda, odolnost = _liga()
    for i, r in enumerate(rows):                     # dvojchyby: hráč 'Jan Svoboda' dělá o 40 % víc
        for k, jm in (("df_w", r["w"]), ("df_l", r["l"])):
            base = random.Random(i * 2 + (k == "df_l")).randint(1, 5)
            r[k] = base * (1.4 if jm == "Jan Svoboda" else 1)
    m = tenis.fit(rows, TED, stat="df")
    assert m["s"]["Jan Svoboda"] > 1.2 * m["s"]["Karel Dvorak"]
    r = tenis.p_kdo_vice(m, "Jan Svoboda", "Karel Dvorak", "hard", 3)
    assert r["p_home"] > 0.6 and abs(r["p_home"] + r["p_away"] - 1) < 1e-9
    # Under 0.5 es (Shubladze): hráč s nejslabším podáním má vysokou P(0 es)
    ma = tenis.fit(rows, TED)
    slaby = min(pravda, key=lambda h: pravda[h]); silny = max(pravda, key=lambda h: pravda[h])
    p_slaby = tenis.p_nohy(ma, {"trh": "esa_hrac", "linie": 0.5, "strana": "under", "hrac": slaby}, slaby, silny, "hard", 3)
    p_silny = tenis.p_nohy(ma, {"trh": "esa_hrac", "linie": 0.5, "strana": "under", "hrac": silny}, silny, slaby, "hard", 3)
    assert p_slaby["p"] > p_silny["p"] and p_silny["p"] < 0.05
    # parser: kdo zahraje více dvojchyb (bez remízy) a počet dvojchyb
    n = fortuna.parsuj_trh(_trh("Kdo zahraje více dvojchyb v zápasu (bez remízy)", "", [("Sasnovich", 2.16), ("Sakkari", 1.65)]))
    assert [(x["trh"], x["hrac"]) for x in n] == [("df_kdo", "Sasnovich"), ("df_kdo", "Sakkari")]
    n = fortuna.parsuj_trh(_trh("Počet dvojchyb v zápasu", "", [("Více než 4.5", 1.9), ("Méně než 4.5", 1.9)]))
    assert {x["trh"] for x in n} == {"df"}
    # vyhodnocení df_kdo end-to-end s nabídkou
    jm = lambda h: " ".join(reversed(h.split(" ", 1)))
    z = {"id": "d1", "nazev": "Svoboda Jan - Dvorak Karel", "home": jm("Jan Svoboda"), "away": jm("Karel Dvorak"), "start": "2026-11-06T13:00:00+00:00",
         "sport": "tenis", "turnaj": "ATP Challenger Brisbane", "turnaj_popis": "", "kategorie": "", "live": False,
         "nohy": [{"trh": "df_kdo", "linie": None, "strana": "svoboda jan", "hrac": jm("Jan Svoboda"), "kurz": round(1 / ((r["p_home"] - 0.10) * 1.04), 2)},
                  {"trh": "df_kdo", "linie": None, "strana": "dvorak karel", "hrac": jm("Karel Dvorak"), "kurz": round(1 / ((1 - r["p_home"] + 0.10) * 1.04), 2)}]}
    out = fh.vyhodnot_tenis([z], _cfg(), TED, log=lambda *a: None, nacti_data=lambda ted: rows)
    assert out and out[0]["typ"] == "df_kdo" and out[0]["hrac_fd"] == "Jan Svoboda" and out[0]["edge"] > 0.03


def test_log_tenis_vyhodnoceni():
    tmp = Path(tempfile.mkdtemp())
    config.DATA = tmp / "data"
    config.DATA.mkdir()
    start = (TED - datetime.timedelta(hours=8)).isoformat()
    zakl = {"zapas_id": "t1", "start": start, "sport": "tenis", "kod": "tenis", "home_fd": "Luca Van Assche", "away_fd": "Rinky Hijikata",
            "kurz_fortuna": 1.9, "p_model": 0.6, "p_trh": 0.55, "p": 0.575, "edge": 0.09}
    kand = [{**zakl, "zapas": "T1", "typ": "esa", "linie": 9.5, "strana": "over", "noha_klic": "esa|9.5|over|", "trh": "esa"},
            {**zakl, "zapas": "T1", "typ": "esa_hrac", "linie": 0.5, "strana": "under", "hrac_fd": "Rinky Hijikata", "noha_klic": "esa_hrac|0.5|under|x", "trh": "x"},
            {**zakl, "zapas": "T1", "typ": "df_kdo", "linie": None, "strana": "luca", "hrac_fd": "Luca Van Assche", "noha_klic": "df_kdo|None|luca|Luca", "trh": "y"}]
    assert fl.zaloguj(kand, "2026-11-06") == 3
    z = {"datum": TED - datetime.timedelta(hours=7), "w": "Luca Van Assche", "l": "Rinky Hijikata", "ace_w": 8, "ace_l": 3, "df_w": 4, "df_l": 2}
    assert fl.vyhodnot(lambda kod: [], TED, nacti_tenis=lambda ted: [z]) == 3
    r = {x["typ"]: x for x in fl.nacti()}
    assert r["esa"]["vysledek"] == "1"          # 11 es > 9.5
    assert r["esa_hrac"]["vysledek"] == "0"     # Hijikata 3 es, Under 0.5 nevyšlo
    assert r["df_kdo"]["vysledek"] == "1"       # Van Assche víc dvojchyb (4:2)


if __name__ == "__main__":
    for f in (test_csv_a_jmena, test_model_es, test_parser_es_a_strel, test_vyhodnot_tenis_a_tip_dne, test_log_clv_brier,
              test_report_tip_dne, test_jistejsi_a_vklad, test_dvojchyby_a_under_nula, test_log_tenis_vyhodnoceni):
        f()
        print("✅", f.__name__)
