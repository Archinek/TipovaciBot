"""Analytická databáze SQLite postavená ze všech uložených dat (data/*). Vždy se staví znovu od nuly, zdroj pravdy zůstávají soubory v data/.

  python -m bot.main postavit_db [cesta]     # výchozí: data_db/tipovaci.sqlite

Tabulky: zapasy, trhy, nabidka (kurzy celé nabídky Fortuny po dnech), linie_nabidky (nohy modelů), prilezitosti (učící sázky s výsledky),
papir_nohy / papir_tikety / papir_tikety_nohy, fortuna_log, fortuna_picks, doplnkove, bety, kalibrace_trhu, vysledky_zdroje, hist_zapasy, popis.
Pohledy: v_prilezitosti_hotove, v_kalibrace_sport_kurz, v_kalibrace_trh, v_roi_denne, v_nevyhodnocene.
"""
import csv
import datetime
import gzip
import json
import sqlite3
from zoneinfo import ZoneInfo

from . import config

PRAHA = ZoneInfo("Europe/Prague")


def _cislo(x):
    if x is None:
        return None
    if isinstance(x, (int, float)):
        return x
    s = str(x).strip()
    if s == "":
        return None
    try:
        return int(s) if s.lstrip("-").isdigit() else float(s)
    except ValueError:
        return s


def _csv(f):
    op = gzip.open if str(f).endswith(".gz") else open
    with op(f, "rt", encoding="utf-8-sig", newline="") as fh:
        return list(csv.DictReader(fh))


def _json(f):
    try:
        return json.loads(f.read_text(encoding="utf-8"))
    except Exception:
        return None


def _tabulka(con, nazev, radky, sloupce=None, typy=None):
    """Vytvoří tabulku z řádků (dict); sloupce = sjednocení klíčů, číselné hodnoty se převedou."""
    radky = list(radky)
    sl = sloupce or list(dict.fromkeys(k for r in radky for k in r))
    if not sl:
        return 0
    con.execute(f'DROP TABLE IF EXISTS "{nazev}"')
    con.execute(f'CREATE TABLE "{nazev}" (' + ", ".join(f'"{c}"' for c in sl) + ")")
    con.executemany(f'INSERT INTO "{nazev}" VALUES ({",".join("?" * len(sl))})',
                    ([(_cislo(r.get(c)) if not isinstance(r.get(c), (list, dict)) else json.dumps(r.get(c), ensure_ascii=False)) for c in sl] for r in radky))
    return len(radky)


def _lokalni(start):
    try:
        d = datetime.datetime.fromisoformat(start)
    except Exception:
        return None
    return d.astimezone(PRAHA).replace(tzinfo=None) if d.tzinfo else d


def postav(cesta=None, log=print):
    data = config.DATA
    cesta = cesta or (config.ROOT / "data_db" / "tipovaci.sqlite")
    cesta.parent.mkdir(parents=True, exist_ok=True)
    if cesta.exists():
        cesta.unlink()
    con = sqlite3.connect(cesta)
    con.execute("PRAGMA journal_mode=OFF")
    con.execute("PRAGMA synchronous=OFF")
    pocty = {}

    # --- celá nabídka Fortuny po dnech
    con.execute("CREATE TABLE zapasy (zn INTEGER PRIMARY KEY, zapas_id TEXT UNIQUE, nazev, home, away, start_utc, start_praha, sport, turnaj, turnaj_id, kategorie, prvni_snapshot, posledni_snapshot)")
    con.execute("CREATE TABLE typy_trhu (typ_id INTEGER PRIMARY KEY, typ)")
    con.execute("CREATE TABLE trhy (trh_id INTEGER PRIMARY KEY, nazev, typ_id INTEGER)")
    con.execute("CREATE TABLE vybery (vyber_id INTEGER PRIMARY KEY, vyber)")
    con.execute("CREATE TABLE nabidka (snapshot, zn INTEGER, trh_id INTEGER, vyber_id INTEGER, kurz REAL)")
    con.execute("CREATE TABLE linie_nabidky (snapshot, zn INTEGER, trh, linie REAL, strana, kurz REAL)")
    zap, trh_id, typ_id, vyb_id, nab, lin = {}, {}, {}, {}, 0, 0
    for f in sorted(data.glob("fortuna_nabidka_*.json")):
        snap = f.stem.rsplit("_", 1)[1]
        d = _json(f)
        if not isinstance(d, list):
            continue
        radky, linie = [], []
        for z in d:
            zid = z.get("id")
            if not zid:
                continue
            if zid not in zap:
                zap[zid] = [len(zap) + 1, zid, z.get("nazev"), z.get("home"), z.get("away"), z.get("start"),
                            (_lokalni(z.get("start") or "") or "") and _lokalni(z["start"]).isoformat(timespec="minutes"),
                            z.get("sport"), z.get("turnaj"), z.get("turnaj_id"), z.get("kategorie"), snap, snap]
            else:
                zap[zid][12] = snap
            for t in z.get("trhy") or []:
                k = (t.get("nazev"), t.get("typ"))
                if k not in trh_id:
                    trh_id[k] = len(trh_id) + 1
                    if t.get("typ") not in typ_id:
                        typ_id[t.get("typ")] = len(typ_id) + 1
                for o in t.get("vysledky") or []:
                    v = o.get("nazev")
                    if v not in vyb_id:
                        vyb_id[v] = len(vyb_id) + 1
                    radky.append((snap, zap[zid][0], trh_id[k], vyb_id[v], o.get("kurz")))
            for n in z.get("nohy") or []:
                linie.append((snap, zap[zid][0], n.get("trh"), n.get("linie"), n.get("strana"), n.get("kurz")))
        con.executemany("INSERT INTO nabidka VALUES (?,?,?,?,?)", radky)
        con.executemany("INSERT INTO linie_nabidky VALUES (?,?,?,?,?,?)", linie)
        nab += len(radky)
        lin += len(linie)
        log(f"   nabídka {snap}: {len(radky)} kurzů")
    con.executemany("INSERT INTO zapasy VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)", zap.values())
    con.executemany("INSERT INTO typy_trhu VALUES (?,?)", ((i, t) for t, i in typ_id.items()))
    con.executemany("INSERT INTO trhy VALUES (?,?,?)", ((i, k[0], typ_id[k[1]]) for k, i in trh_id.items()))
    con.executemany("INSERT INTO vybery VALUES (?,?)", ((i, v) for v, i in vyb_id.items()))
    pocty.update(zapasy=len(zap), trhy=len(trh_id), nabidka=nab, linie_nabidky=lin)

    # --- učící příležitosti (bot je otipuje a vyhodnotí podle výsledků Fortuny)
    podle_nazvu = {}
    for zid, z in zap.items():
        podle_nazvu.setdefault(z[2], []).append((_lokalni(z[5] or ""), zid))

    def najdi_id(nazev, start):
        kand, s = podle_nazvu.get(nazev) or [], _lokalni(start or "")
        if not kand or s is None:
            return None
        dobre = [(abs((k[0] - s).total_seconds()), k[1]) for k in kand if k[0]]
        if not dobre:
            return None
        rozdil, zid = min(dobre)
        return zid if rozdil <= 12 * 3600 else None

    pril, cache = [], {}
    for f in sorted((data / "ucici").glob("*.csv.gz")):
        for r in _csv(f):
            k = (r.get("zapas"), r.get("start"))
            if k not in cache:
                cache[k] = najdi_id(*k)
            r["zapas_id"], r["soubor"] = cache[k], f.name[:10]
            pril.append(r)
    pocty["prilezitosti"] = _tabulka(con, "prilezitosti", pril)

    # --- papírové sázky, tikety, logy
    for jm, f in (("papir_nohy", "nohy.csv"), ("fortuna_log", "fortuna_log.csv"), ("doplnkove", "doplnkove.csv"), ("bety", "bety.csv")):
        p = data / f
        pocty[jm] = _tabulka(con, jm, _csv(p)) if p.exists() else 0
    tik = _json(data / "tikety_log.json") or []
    pocty["papir_tikety"] = _tabulka(con, "papir_tikety", [{k: v for k, v in t.items() if k != "noze"} | {"pocet_nohou": len(t.get("noze") or [])} for t in tik])
    pocty["papir_tikety_nohy"] = _tabulka(con, "papir_tikety_nohy", [{"datum": t.get("datum"), "klic": t.get("klic"), "noha_id": n} for t in tik for n in t.get("noze") or []])
    kal = _json(data / "kalibrace_trhu.json") or {}
    pocty["kalibrace_trhu"] = _tabulka(con, "kalibrace_trhu", [{"klic": k} | v for k, v in kal.items()])
    picks = []
    for f in sorted(data.glob("picks_*.json")):
        d = _json(f) or {}
        for z in d.get("fortuna") or []:
            picks.append({"datum": d.get("datum")} | {k: v for k, v in z.items()})
    pocty["fortuna_picks"] = _tabulka(con, "fortuna_picks", picks)

    # --- skutečné výsledky z veřejných zdrojů a historie fotbalu
    vys = []
    for f in sorted((data / "vysledky").glob("*.json")):
        for z in _json(f) or []:
            vys.append({"soubor": f.stem} | {k: v for k, v in z.items() if k != "extra"} | {f"extra_{k}": v for k, v in (z.get("extra") or {}).items()})
    pocty["vysledky_zdroje"] = _tabulka(con, "vysledky_zdroje", vys)
    hist = []
    for f in sorted((data / "hist").glob("*.csv")):
        for r in _csv(f):
            hist.append({"soubor": f.name} | r)
    pocty["hist_zapasy"] = _tabulka(con, "hist_zapasy", hist)

    # --- indexy, pohledy, popis
    for sql in (
        "CREATE INDEX i_nab_zn ON nabidka(zn)",
        "CREATE INDEX i_lin_zn ON linie_nabidky(zn)",
        "CREATE INDEX i_zap_start ON zapasy(start_praha)", "CREATE INDEX i_zap_sport ON zapasy(sport)",
        "CREATE INDEX i_pril_datum ON prilezitosti(datum)", "CREATE INDEX i_pril_sport ON prilezitosti(sport)", "CREATE INDEX i_pril_zapas ON prilezitosti(zapas_id)",
    ):
        con.execute(sql)
    _pohledy(con)
    _popis(con)
    con.commit()
    con.execute("VACUUM")
    con.close()
    log(f"📦 Databáze {cesta} ({cesta.stat().st_size / 1e6:.0f} MB): " + ", ".join(f"{k} {v}" for k, v in pocty.items()))
    return pocty


def _pohledy(con):
    zisk = "CASE CAST(vysledek AS TEXT) WHEN '1' THEN kurz-1 WHEN '0' THEN -1 ELSE 0 END"
    pasmo = ("CASE WHEN kurz<1.3 THEN '1.0-1.3' WHEN kurz<1.6 THEN '1.3-1.6' WHEN kurz<2 THEN '1.6-2' WHEN kurz<2.6 THEN '2.0-2.6' "
             "WHEN kurz<3.5 THEN '2.6-3.5' WHEN kurz<5 THEN '3.5-5' ELSE '5+' END")
    con.executescript(f"""
CREATE VIEW v_nabidka AS
  SELECT n.snapshot, z.zapas_id, z.nazev AS zapas, z.sport, z.turnaj, z.start_praha, t.nazev AS trh, y.typ AS typ_trhu, v.vyber, n.kurz
  FROM nabidka n JOIN zapasy z USING(zn) JOIN trhy t USING(trh_id) JOIN typy_trhu y ON y.typ_id=t.typ_id JOIN vybery v USING(vyber_id);
CREATE VIEW v_prilezitosti_hotove AS
  SELECT *, CAST(vysledek AS INTEGER) AS vyhra, {pasmo} AS pasmo_kurzu, {zisk} AS zisk_plochy_vklad
  FROM prilezitosti WHERE CAST(vysledek AS TEXT) IN ('1','0');
CREATE VIEW v_kalibrace_sport_kurz AS
  SELECT sport, pasmo_kurzu, COUNT(*) AS n, ROUND(AVG(p),4) AS odhad_p, ROUND(AVG(vyhra),4) AS skutecna_uspesnost,
         ROUND(AVG(vyhra)-AVG(p),4) AS rozdil, ROUND(AVG(zisk_plochy_vklad),4) AS roi_plochy_vklad
  FROM v_prilezitosti_hotove GROUP BY sport, pasmo_kurzu ORDER BY sport, pasmo_kurzu;
CREATE VIEW v_kalibrace_trh AS
  SELECT sport, skupina, zdroj, COUNT(*) AS n, ROUND(AVG(p),4) AS odhad_p, ROUND(AVG(vyhra),4) AS skutecna_uspesnost,
         ROUND(AVG(zisk_plochy_vklad),4) AS roi_plochy_vklad
  FROM v_prilezitosti_hotove GROUP BY sport, skupina, zdroj;
CREATE VIEW v_roi_denne AS
  SELECT datum, COUNT(*) AS n, ROUND(AVG(vyhra),4) AS uspesnost, ROUND(AVG(zisk_plochy_vklad),4) AS roi_plochy_vklad
  FROM v_prilezitosti_hotove GROUP BY datum ORDER BY datum;
CREATE VIEW v_nevyhodnocene AS
  SELECT sport, liga, trh, COUNT(*) AS n FROM prilezitosti WHERE vysledek IS NULL OR CAST(vysledek AS TEXT)='' GROUP BY sport, liga, trh ORDER BY n DESC;
""")


POPIS = [
    ("zapasy", "zn", "Číselný klíč zápasu (používá ho nabidka a linie_nabidky)"),
    ("zapasy", "zapas_id", "Id zápasu ve Fortuně (ufo:mtch:…), shodné s id ve výsledcích"),
    ("zapasy", "start_utc / start_praha", "Začátek zápasu (UTC a pražský čas)"),
    ("zapasy", "prvni_snapshot / posledni_snapshot", "První a poslední den, kdy byl zápas ve stažené nabídce"),
    ("trhy", "trh_id, nazev, typ_id", "Slovník trhů nabídky Fortuny (název trhu; typ_id → typy_trhu)"),
    ("vybery", "vyber_id, vyber", "Slovník možností sázky (Více než 2.5, jména hráčů…)"),
    ("v_nabidka", "*", "Pohodlný pohled: celá nabídka s texty (zápas, trh, typ trhu, výběr, kurz) – pro dotazy nad jedním dnem/zápasem"),
    ("nabidka", "snapshot", "Den stažení nabídky (ráno), kurzy jsou stav v tu chvíli"),
    ("nabidka", "zn, trh_id, vyber_id, kurz", "Jedna možnost sázky a její kurz u Fortuny"),
    ("linie_nabidky", "trh, linie, strana, kurz", "Over/Under linie, které bot modeluje (góly, střely, rohy, karty…)"),
    ("prilezitosti", "p", "Odhadnutá pravděpodobnost bota (zdroj = trh, model, tipsteři…)"),
    ("prilezitosti", "vysledek", "1 = vyhrálo, 0 = prohrálo, V = vráceno/neplatí, prázdné = zatím nevyhodnoceno"),
    ("prilezitosti", "zapas_id", "Id zápasu ve Fortuně (nalezeno podle názvu a času, může chybět)"),
    ("prilezitosti", "soubor", "Den souboru, ve kterém je příležitost uložena"),
    ("v_prilezitosti_hotove", "zisk_plochy_vklad", "Zisk při vkladu 1 jednotka na kurz: kurz-1 / -1"),
    ("v_kalibrace_sport_kurz", "rozdil", "skutečná úspěšnost minus odhadnutá p: kladné = bot podhodnocuje, záporné = nadhodnocuje"),
    ("papir_nohy", "*", "Papírové sázky ze všech sportů (vyhodnocené z výsledků Fortuny)"),
    ("papir_tikety / papir_tikety_nohy", "*", "Papírové tikety (denní tiket, Pyramida…) a jejich nohy"),
    ("fortuna_log", "*", "Log linií Fortuny s vývojem kurzu (CLV)"),
    ("fortuna_picks", "*", "Tipy z reportů po dnech"),
    ("kalibrace_trhu", "klic", "Kalibrace po sportu a pásmu kurzu uložená botem"),
    ("vysledky_zdroje", "*", "Výsledky z veřejných zdrojů (ESPN, football-data…)"),
    ("hist_zapasy", "*", "Historie fotbalu (football-data.co.uk)"),
]


def _popis(con):
    con.execute("CREATE TABLE popis (tabulka, sloupec, vyznam)")
    con.executemany("INSERT INTO popis VALUES (?,?,?)", POPIS)
