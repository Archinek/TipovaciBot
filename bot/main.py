"""Vstupní bod. Příkazy:
  python -m bot.main morning   # vyhodnocení včerejška + ranní report + WhatsApp
  python -m bot.main closing   # uloží uzavírací fér kurzy (pro CLV) zápasům těsně před výkopem
  python -m bot.main settle    # jen vyhodnocení výsledků
  python -m bot.main resend    # znovu pošle dnešní WhatsApp zprávu
  python -m bot.main backtest [E0|all]   # ověří model doplňkových trhů na historii
  python -m bot.main builder "soccer_epl|Arsenal|Chelsea|karty>4.5,rohy>9.5|3.4|Rozhodčí"
  python -m bot.main sports    # diagnostika: které skupiny sportů vrací Odds API a které máš namapované
"""
import datetime
import json
import sys
from collections import defaultdict
from zoneinfo import ZoneInfo

from . import config, engine, histdata, mojekurzy, report, store, veto
from .oddsapi import OddsApi, OddsApiChyba

UTC = datetime.timezone.utc


def _log(*a):
    print(*a, flush=True)


def _nyni():
    return datetime.datetime.now(UTC)


# ------------------------------------------------------------ výběr sportů
def vyber_cile(api_sports, cfg, rezimy):
    mapa = {}
    for nazev, c in cfg["sporty"].items():
        for g in c.get("groups", []):
            mapa[g] = (nazev, c)
    cile, nenamapovane = [], set()
    for s in api_sports:
        if not s.get("active") or s.get("has_outrights"):
            continue
        m = mapa.get(s.get("group"))
        if not m:
            nenamapovane.add(s.get("group"))
            continue
        nazev, c = m
        rezim = rezimy.get(nazev, c.get("rezim", cfg["nastaveni"]["vychozi_rezim"]))
        if rezim == "off":
            continue
        cile.append({"key": s["key"], "nazev": nazev, "cfg": c, "rezim": rezim})
    cile.sort(key=lambda x: (x["cfg"].get("tier", "Z"), x["key"]))
    return cile, nenamapovane


# ------------------------------------------------------------ vyhodnocení
def vyhodnot(api, cfg, ted):
    """Doplní výsledek a zisk řádkům po zápase. Chyby jednoho sportu nezastaví zbytek."""
    rows = store.nacti()
    cekajici = [r for r in rows if not r["vysledek"]
                and engine.cas(r["start"]) < ted - datetime.timedelta(hours=3)]
    if not cekajici:
        return []
    podle = defaultdict(list)
    for r in cekajici:
        podle[r["sport_key"]].append(r)
    nove = []
    for sk, lst in podle.items():
        try:
            ev = {e["id"]: e for e in api.scores(sk, 3)}
        except OddsApiChyba as e:
            _log(f"⚠️ Scores {sk}: {e}")
            ev = {}
        for r in lst:
            e = ev.get(r["event_id"])
            v = engine.vitez(e) if e else None
            if v is not None:
                win = (r["vyber"] == v)
                r["vysledek"] = "win" if win else "loss"
                r["zisk_paper"] = round(float(r["best_kurz"]) - 1, 4) if win else -1.0
                if r["kurz_vzat"]:
                    r["zisk_real"] = round(float(r["kurz_vzat"]) - 1, 4) if win else -1.0
                nove.append(r)
            elif engine.cas(r["start"]) < ted - datetime.timedelta(days=5):
                r["vysledek"] = "nevyhodnoceno"
    store.uloz(rows)
    return nove


def souhrn_vcera(nove):
    r = [x for x in nove if x["veto"] != "VETO" and x["vysledek"] in ("win", "loss")]
    if not r:
        return ""
    w = sum(x["vysledek"] == "win" for x in r)
    roi = sum(float(x["zisk_paper"]) for x in r) / len(r)
    return f"{w}✅ / {len(r) - w}❌, paper ROI {roi * 100:+.1f} %"


# ------------------------------------------------------------ uzavírací kurzy
def uzaviraci(api, cfg, ted):
    rows = store.nacti()
    okno = ted + datetime.timedelta(minutes=80)
    due = [r for r in rows if not r["closing_fair_p"] and not r["vysledek"]
           and ted < engine.cas(r["start"]) <= okno]
    if not due:
        _log("ℹ️ Žádné zápasy těsně před výkopem, nic nestahuji.")
        return 0
    podle = defaultdict(list)
    for r in due:
        podle[r["sport_key"]].append(r)
    hotovo = 0
    for sk, lst in podle.items():
        ids = sorted({r["event_id"] for r in lst})
        try:
            data = {e["id"]: e for e in api.odds(sk, cfg["nastaveni"]["regiony"], event_ids=ids)}
        except OddsApiChyba as e:
            _log(f"⚠️ Closing {sk}: {e}")
            continue
        for r in lst:
            e = data.get(r["event_id"])
            if not e:
                continue
            ceny = engine.h2h_ceny(e)
            sharp = [b for b in cfg["sharp_kancelare"] if b in ceny]
            if r["fair_zdroj"].startswith("konsenzus"):
                fair = engine.fair_z_knih(ceny, list(ceny))
            elif sharp:
                fair = engine.fair_z_knih(ceny, ["pinnacle" if "pinnacle" in sharp else sharp[0]])
            else:
                fair = None
            if fair and r["vyber"] in fair:
                r["closing_fair_p"] = round(fair[r["vyber"]], 4)
                hotovo += 1
    store.uloz(rows)
    _log(f"✅ Uzavírací kurzy uloženy: {hotovo}")
    return hotovo


# ------------------------------------------------------------ doplňkové trhy (fotbal)
def _hist_fn(nast, ted):
    return lambda kod: histdata.nacti_ligu(kod, ted, 2, nast.get("cervena_karta_jako", 1))


def doplnkove_krok(api, cfg, ted, aktivni):
    """Zápasy v pokrytých ligách s nejvýraznějším signálem modelu. Chyby sem nesmí shodit ranní běh."""
    from . import doplnkove as dp            # lazy: numpy není potřeba pro closing job
    nast = cfg.get("doplnkove") or {}
    if not nast.get("zapnuto"):
        return []
    zona = ZoneInfo(cfg["nastaveni"]["zona"])
    do = ted + datetime.timedelta(hours=cfg["nastaveni"]["max_hodin_dopredu"])
    rozhodci = dp.nacti_rozhodci()
    zapasy = []
    for sk, kod in histdata.LIGY.items():
        if sk not in aktivni:
            continue
        try:
            ev = api.events(sk, ted, do)
        except OddsApiChyba as e:
            _log(f"⚠️ events {sk}: {e}")
            continue
        if not ev:
            continue
        rows = histdata.nacti_ligu(kod, ted, 2, nast["cervena_karta_jako"])
        if not rows:
            _log(f"⚠️ Historie ligy {kod} nedostupná, doplňkové trhy přeskakuji.")
            continue
        model = dp.fit(rows, ted, nast)
        if not model["vars"]:
            continue
        tymy = sorted({r["home"] for r in rows} | {r["away"] for r in rows})
        for e in ev:
            h = histdata.mapuj(e.get("home_team", ""), tymy)
            a = histdata.mapuj(e.get("away_team", ""), tymy)
            if not (h and a):
                _log(f"ℹ️ Nespárované týmy: {e.get('home_team')} / {e.get('away_team')}")
                continue
            start = engine.cas(e["commence_time"])
            ref = rozhodci.get(f"{start.astimezone(zona):%Y-%m-%d}|{h}|{a}")
            res = dp.analyzuj_zapas(model, h, a, ref, nast)
            if not res or not (res["linie"] or res["builder"]):
                continue
            res.update({"zapas": f"{e['home_team']} vs {e['away_team']}", "home_fd": h,
                        "away_fd": a, "kod": kod, "liga_klic": sk, "start": start.isoformat()})
            zapasy.append(res)
    zapasy.sort(key=lambda z: -z["signal"])
    _log(f"🧩 Doplňkové trhy: {len(zapasy)} zápasů se signálem.")
    return zapasy[:nast["max_zapasu"]]


def backtest_cmd(arg):
    from . import doplnkove as dp
    cfg = config.nacti_cfg()
    nast = cfg["doplnkove"]
    ted = _nyni()
    kody = [arg] if arg and arg != "all" else sorted(set(histdata.LIGY.values()))
    for kod in kody:
        rows = histdata.nacti_ligu(kod, ted, 3, nast["cervena_karta_jako"])
        if len(rows) < 400:
            _log(f"{kod}: málo dat ({len(rows)} zápasů), přeskakuji.")
            continue
        res = dp.backtest(rows, nast, ted - datetime.timedelta(days=365))
        _log(f"== {kod} ({len(rows)} zápasů v historii) ==")
        for v, x in res.items():
            _log(f"  {v:6s} n={x['n']:5d}  logloss model {x['logloss_model']}  základ {x['logloss_zaklad']}"
                 f"  zlepšení {x['zlepseni_pct']:+.2f} %")
    _log("Kladné zlepšení = model je lepší než naivní průměr ligy. Kolem nuly nebo záporné = nesázet.")


def builder_cmd(arg):
    """arg: 'soccer_epl|Arsenal|Chelsea|karty>4.5,rohy>9.5|3.40|Jméno rozhodčího' (kurz a rozhodčí volitelné)"""
    from . import doplnkove as dp
    cfg = config.nacti_cfg()
    nast = cfg["doplnkove"]
    c = [x.strip() for x in arg.split("|")]
    if len(c) < 4:
        _log("Formát: liga_klíč|Domácí|Hosté|karty>4.5,rohy>9.5|kurz|rozhodčí")
        return
    sk, home, away, txt = c[:4]
    kurz = float(c[4].replace(",", ".")) if len(c) > 4 and c[4] else None
    ref = c[5] if len(c) > 5 and c[5] else None
    if sk not in histdata.LIGY:
        _log(f"Liga {sk} není pokrytá (viz histdata.LIGY).")
        return
    ted = _nyni()
    rows = histdata.nacti_ligu(histdata.LIGY[sk], ted, 2, nast["cervena_karta_jako"])
    tymy = sorted({r["home"] for r in rows} | {r["away"] for r in rows})
    h, a = histdata.mapuj(home, tymy), histdata.mapuj(away, tymy)
    if not (h and a):
        _log(f"Týmy nespárovány: {home} / {away}")
        return
    model = dp.fit(rows, ted, nast)
    nohy = []
    for t in txt.split(","):
        op = ">" if ">" in t else "<"
        v, L = t.split(op)
        nohy.append((v.strip(), float(L), "over" if op == ">" else "under"))
    mus = {}
    for v, _, _ in nohy:
        mu = dp.predikuj(model["var"][v], h, a, ref, v) if v in model["var"] else None
        if mu is None:
            _log(f"Pro trh '{v}' nemám model nebo data týmů.")
            return
        mus[v] = mu
    sim = dp.simuluj(model, mus, nast["simulace"])
    joint, soucin = dp.cena_builderu(sim, nohy)
    fair = 1 / joint if joint else float("inf")
    text = (f"🧩 Builder {h} vs {a}: " + " + ".join(f"{dp.NAZVY[v]} {'Over' if s == 'over' else 'Under'} {L}" for v, L, s in nohy)
            + f"\nSpolečná pravděpodobnost {joint * 100:.1f} % (součin samostatných {soucin * 100:.1f} %, "
            f"korelace ×{joint / soucin:.2f})\nFér kurz {fair:.2f}, sázej od {fair * (1 + nast['min_edge']):.2f}")
    if kurz:
        text += f"\nTvůj kurz {kurz}: edge {(kurz * joint - 1) * 100:+.1f} %"
    _log(text)
    report.posli_wa(text)


# ------------------------------------------------------------ ranní běh
def _radek(k, datum, rezim, v):
    r = {p: "" for p in store.POLE}
    r.update(k)
    r.update({"datum": datum, "rezim": rezim, "veto": v[0], "veto_duvod": v[1]})
    r["_kontext"] = v[2]
    return r


def morning(api=None, veto_fn=None, wa_fn=None, ted=None, force=False):
    cfg = config.nacti_cfg()
    nast = cfg["nastaveni"]
    ted = ted or _nyni()
    lokalni = ted.astimezone(ZoneInfo(nast["zona"]))
    datum = lokalni.strftime("%Y-%m-%d")
    cesta_picks = config.DATA / f"picks_{datum}.json"
    if not force:
        h = nast["hodina_ranni_report"]
        if not (h <= lokalni.hour < h + 3):
            _log(f"ℹ️ Teď je {lokalni:%H:%M} v Praze, ranní okno je {h}:00–{h + 3}:00. Konec.")
            return None
        if cesta_picks.exists():
            _log(f"ℹ️ Report pro {datum} už existuje. Konec.")
            return None

    api = api or OddsApi(config.env("ODDS_API_KEY"))
    veto_fn = veto_fn or veto.zkontroluj
    wa_fn = wa_fn or report.posli_wa

    # 1) vyhodnocení starých tipů
    try:
        nove = vyhodnot(api, cfg, ted)
    except Exception as e:
        _log(f"⚠️ Vyhodnocení selhalo: {type(e).__name__}: {e}")
        nove = []
    vcera = souhrn_vcera(nove)

    # 2) cílové sporty
    rezimy = store.nacti_rezimy()
    if nast.get("odds_api_h2h", True):
        api_sports = api.sports()
        aktivni = {x['key'] for x in api_sports if x.get('active')}
        cile, nenamapovane = vyber_cile(api_sports, cfg, rezimy)
    else:                                                  # H2H porovnání s trhem přes placené Odds API je vypnuté: hlavní je celá nabídka Fortuny
        cile, nenamapovane, aktivni = [], set(), set()
        _log("ℹ️ Odds API (porovnání s Pinnaclem) je vypnuto v sporty.yaml; pracuje se s celou nabídkou Fortuny.")
    if nenamapovane:
        _log(f"ℹ️ Nenamapované skupiny Odds API (ignoruji): {sorted(g for g in nenamapovane if g)}")
    _log(f"🎯 Sportovních klíčů ke kontrole: {len(cile)}")

    # 3) kurzy a kandidáti
    od, do = ted, ted + datetime.timedelta(hours=nast["max_hodin_dopredu"])
    kandidati, kredity = [], 0
    naklad = len(nast["regiony"])
    for c in cile:
        if kredity + naklad > nast["kredity_max_na_beh"]:
            _log("⚠️ Dosažen limit kreditů na běh, zbytek sportů přeskakuji.")
            break
        try:
            if not api.events(c["key"], od, do):       # zdarma: nemá cenu platit za prázdné
                continue
            data = api.odds(c["key"], nast["regiony"], od, do)
            kredity += naklad
        except OddsApiChyba as e:
            _log(f"⚠️ {c['key']}: {e}")
            continue
        for ev in data:
            for k in engine.najdi_kandidaty(ev, c["nazev"], c["cfg"], cfg, ted):
                k["rezim"] = c["rezim"]
                kandidati.append(k)
    _log(f"📈 Kandidátů s hranou: {len(kandidati)} | kredity tento běh: {kredity} | zbývá: {api.zbyva}")

    # 4) top + veto
    top = engine.vyber_top(kandidati, nast)
    vysl = veto_fn(top, cfg) if top else {}
    radky = [_radek(k, datum, k["rezim"], vysl.get(k["id"], veto.NEOVERENO)) for k in top]
    picks = [r for r in radky if r["veto"] != "VETO"][:nast["max_tipu_denne"]]
    vyrazene = [r for r in radky if r["veto"] == "VETO"]
    # anonymní nabídka Fortuny (orientační ceník, sázíš jinde); chyba ani blok nikdy nesmí shodit ranní report
    zap_fortuna, univ = [], []
    try:
        from . import fortuna
        if (cfg.get("fortuna") or {}).get("zapnuto", True):
            zap_fortuna = fortuna.nabidka(filtry=("today", "tomorrow"),
                                          max_zapasu=(cfg.get("fortuna") or {}).get("max_zapasu", 0),
                                          max_sekund=(cfg.get("fortuna") or {}).get("max_sekund", 0), log=_log)
            try:
                from . import fortuna_vse
                univ = fortuna_vse.nejpravdepodobnejsi(zap_fortuna, cfg)
                _log(f"📋 Nejpravděpodobnější z celé nabídky: {len(univ)}.")
            except Exception as e:
                _log(f"⚠️ Žebříček celé nabídky selhal: {type(e).__name__}: {e}")
            fortuna.uloz_nabidku(zap_fortuna, datum)
    except Exception as e:
        _log(f"⚠️ Fortuna selhala: {type(e).__name__}: {e}")
    from . import fortuna as _f
    spar = mojekurzy.aplikuj(picks, [], cfg, extra=_f.radky_pro_mojekurzy(zap_fortuna))     # + ruční data/moje_kurzy.csv
    if spar:
        _log(f"💱 Spárováno {spar} tvých kurzů z moje_kurzy.csv (h2h).")
    ulozit = [{**r} for r in picks + vyrazene]
    for r in ulozit:
        r.pop("_kontext", None)
    pridano = store.pridej(ulozit)
    _log(f"📝 Do logu přidáno {pridano} řádků.")

    # 4b) doplňkové trhy (fotbal): chyba tady nikdy nesmí shodit ranní report
    dopl, kalib = [], {"n": 0}
    try:
        from . import doplnkove as dp
        dp.vyhodnot_log(_hist_fn(cfg.get("doplnkove") or {}, ted), ted)
        dopl = doplnkove_krok(api, cfg, ted, aktivni)
        spar2 = mojekurzy.aplikuj([], dopl, cfg)
        if spar2:
            _log(f"💱 Spárováno {spar2} tvých kurzů u doplňkových trhů.")
        dp.zaloguj_predikce(dopl, datum)
        kalib = dp.kalibrace(dp.nacti_log())
    except Exception as e:
        _log(f"⚠️ Doplňkové trhy selhaly: {type(e).__name__}: {e}")

    # 4c) Fortuna vs. model (fotbal, vedlejší trhy) + obsáhlá analýza s kritérii z YAML pro všechny sporty
    fort = []
    try:
        from . import analyza, fortuna_hodnota, tipsteri
        an = cfg.get("analyza") or {}
        if zap_fortuna:
            fort = fortuna_hodnota.vyhodnot(zap_fortuna, cfg, ted, log=_log)
            try:                                                      # tenis (esa): chyba dat nesmí shodit fotbal
                fort += fortuna_hodnota.vyhodnot_tenis(zap_fortuna, cfg, ted, log=_log)
            except Exception as e:
                _log(f"⚠️ Tenis (esa) selhal: {type(e).__name__}: {e}")
        tipsteri.tip_dne(fort, cfg)                                   # spočítá skóre; nejlepší půjdou do analýzy první
        fort.sort(key=lambda x: -x["skore"])
        if an.get("zapnuto", True):
            fort, fort_veto = analyza.rozsir(fort, cfg, max_zapasu=an.get("max_zapasu_fotbal", 6))
            if fort_veto:
                _log(f"⛔ Analýza vyřadila {len(fort_veto)} kandidátů z Fortuny (VETO).")
            picks, h2h_veto = analyza.rozsir(picks, cfg, max_zapasu=an.get("max_zapasu_h2h", 8))
            if h2h_veto:
                _log(f"⛔ Analýza vyřadila {len(h2h_veto)} h2h tipů (VETO).")
                for p in h2h_veto:
                    p["veto"], p["veto_duvod"] = "VETO", (p.get("analyza") or {}).get("duvod", "")
                vyrazene += h2h_veto
        tip = tipsteri.tip_dne(fort, cfg)                             # znovu po VETO: tip dne jen z kandidátů, které prošly
        _log(f"⭐ Tip dne: {len(tip)} z {len(fort)} kandidátů.")
    except Exception as e:
        _log(f"⚠️ Analýza/Fortuna selhala: {type(e).__name__}: {e}")
    try:                                                              # rozbor i pro nejpravděpodobnější sázky ze všech sportů (bez modelu)
        from . import analyza as _an
        if univ and (cfg.get("analyza") or {}).get("zapnuto", True) and (cfg.get("analyza") or {}).get("univ_zapnuto", True):
            univ, univ_veto = _an.rozsir_univ(univ, cfg)
            _log(f"🔎 Rozbor výběru z celé nabídky: {len(univ)} sázek, VETO {len(univ_veto)}.")
    except Exception as e:
        _log(f"⚠️ Rozbor výběru z celé nabídky selhal: {type(e).__name__}: {e}")
    jist = []
    try:                                                              # nejjistější příležitosti dne (libovolný kurz), s rozborem
        from . import analyza as _an2, tikety as _tk
        jist = _tk.jistoty(zap_fortuna, fort, cfg, ted) if zap_fortuna else []
        if jist and (cfg.get("analyza") or {}).get("zapnuto", True):
            jist, jist_veto = _an2.rozsir_univ(jist, cfg)
            _log(f"🔒 Nejjistější dne: {len(jist)} sázek, VETO {len(jist_veto)}.")
        else:
            _log(f"🔒 Nejjistější dne: {len(jist)} sázek.")
    except Exception as e:
        _log(f"⚠️ Nejjistější dne selhalo: {type(e).__name__}: {e}")
    log_text = ""
    try:                                                              # fáze 1: log hran, výsledky, CLV, Brier modelu vs. trhu
        from . import fortuna_log, tenis
        fortuna_log.vyhodnot(_hist_fn(cfg.get("doplnkove") or {}, ted), ted, nacti_tenis=tenis.nacti)
        pridano = fortuna_log.zaloguj(fort, datum)
        log_text = fortuna_log.souhrn_text(fortuna_log.souhrn())
        _log(f"🗂️ Log Fortuny: +{pridano} linií. {log_text}")
    except Exception as e:
        _log(f"⚠️ Log Fortuny selhal: {type(e).__name__}: {e}")

    try:                                                              # výsledky z internetu: vyhodnocení včerejších sázek ze všech sportů
        from . import vyhodnoceni
        vyhodnoceni.vyhodnot(ted, log=_log)
        _log("🗂️ " + vyhodnoceni.souhrn_text())                         # jen do logu: do reportu se evidence výsledků nepíše
        from . import ucici
        _log(f"🧠 Papírové tipy (učení): vyhodnoceno {ucici.vyhodnot(ted, log=_log)}")
        ucici.uloz_kalibraci(log=_log)
        _log(f"🧠 Papírové tipy (učení): +{ucici.zaloguj(datum, zap_fortuna, ted, log=_log, cfg=cfg)} nových z nabídky Fortuny")
    except Exception as e:
        _log(f"⚠️ Vyhodnocení sázek ze všech sportů selhalo: {type(e).__name__}: {e}")

    tik = None
    try:                                                              # denní tiket na kurz ~2.00 a Pyramida (z nabídky všech sportů)
        from . import tikety
        tik = tikety.sestav(zap_fortuna, fort, cfg, ted) if zap_fortuna else None
        if tik:
            _log(f"🎟️ Tikety: zásoba {tik['pocet_noh']} sázek, denní tiket {'ano' if tik['denni'] else 'ne'}, "
                 f"Pyramida kol {sum(1 for x in tik['pyramida'] if x['tiket'])}/10.")
    except Exception as e:
        _log(f"⚠️ Tikety selhaly: {type(e).__name__}: {e}")

    try:
        from . import vyhodnoceni
        _log(f"🗂️ Sázky ze všech sportů: +{vyhodnoceni.zaloguj(datum, univ, tik, jist, vd=[report._z_fort(f) | {"sport": f.get("sport") or ""} for f in report.vyber_value_drop(fort, cfg)], fild=[report._z_fort(f) | {"sport": f.get("sport") or ""} for f in report.vyber_fild(fort, cfg)])} nových do evidence.")
    except Exception as e:
        _log(f"⚠️ Evidence sázek selhala: {type(e).__name__}: {e}")

    # 5) výstupy
    for p in picks:
        p["veto_kontext"] = p.pop("_kontext", "")
    rows = store.nacti()
    celkem = store.metriky(rows)
    uceni = None
    try:
        from . import prehled
        uceni = prehled.vypocti(datum, cfg=cfg)
        from . import overeni
        for seznam in (univ, jist, fort):
            overeni.oznac(seznam, uceni["segmenty"])
    except Exception as e:
        _log(f"⚠️ Přehled učení selhal: {type(e).__name__}: {e}")
    sestav_vystupy(datum, picks, vyrazene, vcera, rows, cfg, nast, dopl, kalib, fort, univ, tik, jist, uceni, log_text)
    cesta_picks.write_text(json.dumps(
        {"datum": datum, "picks": picks, "vyrazene": vyrazene, "vcera": vcera, "doplnkove": dopl, "fortuna": fort, "univ": univ, "jistoty": jist},
        ensure_ascii=False, indent=2), encoding="utf-8")

    text = report.wa_ranni(datum, picks, vcera, config.pages_reports_url(), nast["zona"], dopl=dopl, fort=fort, log_text=log_text, univ=univ, tik=tik, jist=jist)
    wa_fn(text)
    return {"picks": picks, "vyrazene": vyrazene, "celkem": celkem}


def sestav_vystupy(datum, picks, vyrazene, vcera, rows, cfg, nast, dopl=None, kalib=None, fort=None, univ=None, tik=None, jist=None, uceni=None, model_text=""):
    config.DOCS.mkdir(parents=True, exist_ok=True)
    (config.DOCS / "reports").mkdir(exist_ok=True)
    (config.DOCS / ".nojekyll").touch()
    celkem = store.metriky(rows)
    podle_tieru = store.metriky_podle(rows, "tier")
    podle_sportu = store.metriky_podle(rows, "sport")
    (config.DOCS / "reports" / f"{datum}.html").write_text(
        report.sestav_report(datum, picks, vyrazene, vcera, {"vše": celkem, **podle_tieru}, nast["zona"],
                             dopl=dopl, kalib=kalib, fort=fort, univ=univ, tik=tik, jist=jist, cfg=cfg, uceni=uceni, model_text=model_text),
        encoding="utf-8")

    doporuceni = {}
    for sport, m in podle_sportu.items():
        d = store.doporuceny_rezim(m, cfg["auto_rizeni"])
        if d:
            doporuceni[sport] = d
    if cfg["auto_rizeni"].get("automaticky") and doporuceni:
        r = store.nacti_rezimy()
        r.update(doporuceni)
        store.uloz_rezimy(r)

    reporty = sorted((p.stem for p in (config.DOCS / "reports").glob("*.html")), reverse=True)
    (config.DOCS / "index.html").write_text(
        report.sestav_index(reporty, celkem, podle_tieru, podle_sportu, doporuceni), encoding="utf-8")


# ------------------------------------------------------------ ostatní příkazy
def resend():
    cfg = config.nacti_cfg()
    nast = cfg["nastaveni"]
    datum = _nyni().astimezone(ZoneInfo(nast["zona"])).strftime("%Y-%m-%d")
    p = config.DATA / f"picks_{datum}.json"
    if not p.exists():
        _log("⚠️ Dnešní picks neexistují.")
        return
    d = json.loads(p.read_text(encoding="utf-8"))
    report.posli_wa(report.wa_ranni(d["datum"], d["picks"], d.get("vcera", ""),
                                    config.pages_reports_url(), nast["zona"], dopl=d.get("doplnkove")))


def sports():
    cfg = config.nacti_cfg()
    api = OddsApi(config.env("ODDS_API_KEY"))
    s = api.sports()
    cile, nenam = vyber_cile(s, cfg, store.nacti_rezimy())
    _log(f"Aktivních klíčů celkem: {sum(1 for x in s if x.get('active'))}")
    _log(f"Namapovaných (budou se stahovat): {len(cile)}")
    _log("Skupiny API bez mapování (přidej do sporty.yaml pokud chceš): "
         f"{sorted(g for g in nenam if g)}")
    skupiny = defaultdict(int)
    for c in cile:
        skupiny[c["nazev"]] += 1
    _log(f"Klíčů podle sportu: {dict(skupiny)}")


def main(argv):
    cmd = argv[1] if len(argv) > 1 else "morning"
    force = config.env("FORCE_RUN") == "1"
    if cmd == "morning":
        morning(force=force)
    elif cmd == "closing":
        try:
            uzaviraci(OddsApi(config.env("ODDS_API_KEY")), config.nacti_cfg(), _nyni())
        except Exception as e:                              # bez Odds API klíče stále chceme snímek kurzů Fortuny
            _log(f"⚠️ Closing (Odds API): {type(e).__name__}: {e}")
        try:                                                # pohyb kurzu zalogovaných linií Fortuny (CLV); jen pár požadavků
            from . import fortuna, fortuna_log
            if (config.nacti_cfg().get("fortuna") or {}).get("zapnuto", True):
                _log(f"📉 Snímek kurzů Fortuny: {fortuna_log.snimek(fortuna.Klient(pauza=0.4), _nyni(), log=_log)} linií aktualizováno.")
        except Exception as e:
            _log(f"⚠️ Snímek Fortuny selhal: {type(e).__name__}: {e}")
    elif cmd == "settle":
        api, cfg = OddsApi(config.env("ODDS_API_KEY")), config.nacti_cfg()
        nove = vyhodnot(api, cfg, _nyni())
        _log(f"Vyhodnoceno {len(nove)} řádků. {souhrn_vcera(nove)}")
    elif cmd == "resend":
        resend()
    elif cmd == "sports":
        sports()
    elif cmd == "vysledky_test":
        import datetime as _dt
        from . import vysledky
        for dd in (1, 2):
            d = (_dt.date.today() - _dt.timedelta(days=dd)).isoformat()
            v = vysledky.ziskej(d, log=_log, cache=False)
            _log(f"📊 Výsledky {d}: {len(v)} zápasů; ukázka: " + "; ".join(f"{x['liga']} {x['home']} {x['h']}:{x['a']} {x['away']}" for x in v[:4]))
    elif cmd == "vysledky_fortuna":
        import datetime as _dt
        from . import vysledky_fortuna as vf
        d = (_dt.date.today() - _dt.timedelta(days=1)).isoformat()
        z = vf.stahni({d}, {"hokej", "basketbal", "fotbal", "tenis"}, log=_log)
        if z:
            n = vf.doplnit_detail(z[:2], log=_log)
            _log(f"📊 Detail se všemi trhy u 2 zápasů: {n}; počty trhů: " + ", ".join(f"{x['name']} {len(x['trhy'])}" for x in z[:2]))
        _log(f"📊 Výsledky Fortuny {d}: {len(z)} zápasů, s vyhodnocenými trhy {sum(1 for x in z if x['trhy'])}; "
             + "; ".join(f"{x['sport']} {x['name']} {x['h']}:{x['a']} ({len(x['trhy'])} trhů)" for x in z[:4]))
    elif cmd == "vysledky_probe":
        from . import vysledky_probe
        vysledky_probe.probe(log=_log)
    elif cmd == "fortuna_vysledky":
        from . import vysledky_probe
        vysledky_probe.fortuna_vysledky(log=_log)
    elif cmd == "fortuna_probe":
        from . import fortuna
        fortuna.probe()
    elif cmd == "fortuna":
        from . import fortuna
        zona = ZoneInfo(config.nacti_cfg()["nastaveni"]["zona"])
        datum = _nyni().astimezone(zona).strftime("%Y-%m-%d")
        _log(f"Uloženo: {fortuna.uloz_nabidku(fortuna.nabidka(), datum)}")
    elif cmd == "backtest":
        backtest_cmd(argv[2] if len(argv) > 2 else "all")
    elif cmd == "builder":
        builder_cmd(argv[2] if len(argv) > 2 else "")
    else:
        _log(__doc__)
        sys.exit(2)


if __name__ == "__main__":
    main(sys.argv)
