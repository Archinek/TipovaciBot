"""Fáze 1: logování každé hrany z Fortuny, pohyb kurzu (CLV) a porovnání modelu s trhem (Brier).

Cíl: po pár týdnech spolehlivě říct, jestli model bije trh, a nesázet na víře.
  - zaloguj(): každý kandidát (kurz při objevení, p modelu, p trhu, p mix)
  - snimek():  opakovaně (closing job, cca co 30 min) přečte aktuální kurz téže linie -> pohyb a "uzavírací" kurz
  - vyhodnot(): doplní skutečný výsledek (fotbal z football-data, tenis ze Sackmannových dat)
  - souhrn():  Brier modelu / trhu / mixu, ROI plochého vkladu při vstupním kurzu, CLV (kurz vstupu / kurz těsně před startem)
Brier modelu nižší než Brier trhu na stovkách záznamů = model něco ví. Do té doby je to jen hypotéza.
"""
import csv
import datetime
import os

from . import config
from .fortuna import klic_nohy, nohy_zapasu

POLE = ["id", "datum", "zapas_id", "zapas", "start", "sport", "rodina", "kod", "home_fd", "away_fd", "hrac_fd", "typ", "linie", "strana",
        "noha_klic", "trh", "kurz_vstup", "kurz_posledni", "kurz_min", "kurz_max", "snimku", "p_model", "p_trh", "p", "edge",
        "tip_dne", "vysledek"]


def _cesta():
    return config.DATA / "fortuna_log.csv"


def nacti():
    if not _cesta().exists():
        return []
    with open(_cesta(), encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))


def uloz(rows):
    config.DATA.mkdir(parents=True, exist_ok=True)
    tmp = str(_cesta()) + ".tmp"
    with open(tmp, "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=POLE, extrasaction="ignore")
        w.writeheader()
        for r in rows:
            w.writerow({k: r.get(k, "") for k in POLE})
    os.replace(tmp, _cesta())


def zaloguj(kandidati, datum):
    """Přidá nové kandidáty (každá linie jen jednou za den). -> počet přidaných."""
    rows = nacti()
    mam = {r["id"] for r in rows}
    nove = []
    for c in kandidati:
        rid = f"{datum}|{c.get('zapas_id')}|{c.get('noha_klic')}"
        if rid in mam or not c.get("zapas_id") or not c.get("noha_klic"):
            continue
        mam.add(rid)
        nove.append({"id": rid, "datum": datum, "zapas_id": c["zapas_id"], "zapas": c["zapas"], "start": c.get("start"),
                     "sport": c.get("sport", ""), "rodina": c.get("rodina", ""), "kod": c.get("kod", ""),
                     "home_fd": c.get("home_fd", ""), "away_fd": c.get("away_fd", ""), "hrac_fd": c.get("hrac_fd") or "", "typ": c.get("typ", ""),
                     "linie": c.get("linie"), "strana": c.get("strana"), "noha_klic": c["noha_klic"], "trh": c.get("trh", ""),
                     "kurz_vstup": c["kurz_fortuna"], "kurz_posledni": c["kurz_fortuna"], "kurz_min": c["kurz_fortuna"],
                     "kurz_max": c["kurz_fortuna"], "snimku": 1, "p_model": c["p_model"], "p_trh": c["p_trh"], "p": c["p"],
                     "edge": c["edge"], "tip_dne": c.get("tip_dne", ""), "vysledek": ""})
    uloz(rows + nove)
    return len(nove)


def _start(r):
    try:
        return datetime.datetime.fromisoformat(r["start"])
    except (ValueError, TypeError, KeyError):
        return None


def snimek(klient, ted, okno_h=20, trhy_fn=None, log=print):
    """Pro ještě neodehrané zalogované linie přečte aktuální kurz. Stahuje JEN zápasy z logu (pár požadavků), ne celou nabídku."""
    from . import fortuna
    trhy_fn = trhy_fn or fortuna.trhy
    rows = nacti()
    otevrene = [r for r in rows if (_start(r) and ted - datetime.timedelta(minutes=2) < _start(r) <= ted + datetime.timedelta(hours=okno_h))]
    if not otevrene:
        return 0
    hotovo = 0
    sport_z = {r["zapas_id"]: r.get("sport") or None for r in otevrene}
    for zid in sorted({r["zapas_id"] for r in otevrene}):
        try:
            nohy = {klic_nohy(n): n["kurz"] for n in nohy_zapasu(trhy_fn(klient, zid), sport_z.get(zid))}
        except fortuna.FortunaBlok:
            raise
        except Exception as e:
            log(f"⚠️ Snímek {zid}: {type(e).__name__}: {e}")
            continue
        for r in otevrene:
            if r["zapas_id"] != zid or r["noha_klic"] not in nohy:
                continue
            k = nohy[r["noha_klic"]]
            r["kurz_posledni"] = k
            r["kurz_min"] = min(float(r["kurz_min"]), k)
            r["kurz_max"] = max(float(r["kurz_max"]), k)
            r["snimku"] = int(r["snimku"] or 0) + 1
            hotovo += 1
    uloz(rows)
    return hotovo


def _y(z, typ):
    """Skutečná hodnota z řádku historie zápasu (football-data: z['y'] = {var: (dom, hosté)})."""
    y = z["y"]
    if typ in ("goly", "rohy", "karty", "fauly", "sot"):
        return sum(y[typ]) if typ in y else None
    if typ in ("goly_dom", "sot_dom"):
        v = y.get(typ.split("_")[0])
        return v[0] if v else None
    if typ in ("goly_hos", "sot_hos"):
        v = y.get(typ.split("_")[0])
        return v[1] if v else None
    if typ == "btts":
        return 1 if (y["goly"][0] > 0 and y["goly"][1] > 0) else 0
    return None


def vyhodnot(nacti_historii, ted, nacti_tenis=None):
    """Doplní 'vysledek' (1 = linie by vyšla). nacti_historii(kod) -> řádky football-data.
    Tenis: nacti_tenis(ted) -> řádky Sackmann (zpožděné; výsledek se doplní, až v datech zápas bude)."""
    rows = nacti()
    cek = [r for r in rows if r["vysledek"] == "" and _start(r) and _start(r) + datetime.timedelta(hours=4) < ted]
    if not cek:
        return 0
    cache, hotovo, tenis_rows = {}, 0, None
    for r in cek:
        d0 = _start(r)
        if r["sport"] == "fotbal":
            if r["kod"] not in cache:
                cache[r["kod"]] = nacti_historii(r["kod"])
            for z in cache[r["kod"]]:
                if (z["home"], z["away"]) == (r["home_fd"], r["away_fd"]) and abs((z["datum"] - d0).days) <= 1:
                    y = _y(z, r["typ"])
                    if y is None:
                        break
                    L = float(r["linie"]) if r["linie"] not in ("", "None") else 0.5
                    if r["typ"] == "btts":
                        r["vysledek"] = str(int(y == 1) if r["strana"] == "ano" else int(y == 0))
                    else:
                        r["vysledek"] = str(int(y > L) if r["strana"] == "over" else int(y < L))
                    hotovo += 1
                    break
        elif r["sport"] == "tenis" and nacti_tenis:
            if tenis_rows is None:
                tenis_rows = nacti_tenis(ted)
            for z in tenis_rows:
                if {z["w"], z["l"]} == {r["home_fd"], r["away_fd"]} and abs((z["datum"] - d0).days) <= 14:
                    stat = "df" if r["typ"].startswith("df") else "ace"
                    kw, kl = (f"{stat}_w", f"{stat}_l")
                    if z.get(kw) is None or z.get(kl) is None:
                        break
                    hodn = {z["w"]: z[kw], z["l"]: z[kl]}
                    if r["typ"] in ("esa", "df"):
                        y = z[kw] + z[kl]
                    elif r["typ"] == "df_kdo":
                        a_, b_ = r["home_fd"], r["away_fd"]
                        if hodn[a_] == hodn[b_] or r.get("hrac_fd") not in hodn:
                            break                          # remíza = trh se vrací; bez jistého hráče nevyhodnocuji
                        r["vysledek"] = str(int(hodn[r["hrac_fd"]] > hodn[b_ if r["hrac_fd"] == a_ else a_]))
                        hotovo += 1
                        break
                    else:
                        y = hodn.get(r.get("hrac_fd"))     # hráč přiřazený modelem; bez něj nevyhodnocuji
                    if y is None:
                        break
                    L = float(r["linie"])
                    r["vysledek"] = str(int(y > L) if r["strana"] == "over" else int(y < L))
                    hotovo += 1
                    break
    uloz(rows)
    return hotovo


def souhrn(rows=None):
    """Statistiky logu: počty, CLV (pohyb kurzu) a Brier modelu / trhu / mixu na vyhodnocených linií."""
    rows = nacti() if rows is None else rows
    out = {"n": len(rows), "vyhodnoceno": 0}
    clv = [float(r["kurz_vstup"]) / float(r["kurz_posledni"]) - 1 for r in rows
           if r.get("kurz_posledni") and int(r.get("snimku") or 0) >= 2 and float(r["kurz_posledni"]) > 1]
    if clv:
        out["clv_prumer"] = round(sum(clv) / len(clv), 4)
        out["clv_kladne"] = round(sum(1 for x in clv if x > 0) / len(clv), 3)
        out["clv_n"] = len(clv)
    h = [r for r in rows if r.get("vysledek") in ("0", "1")]
    out["vyhodnoceno"] = len(h)
    if h:
        y = [int(r["vysledek"]) for r in h]

        def brier(klic):
            return round(sum((float(r[klic]) - yi) ** 2 for r, yi in zip(h, y)) / len(h), 4)
        out.update({"brier_model": brier("p_model"), "brier_trh": brier("p_trh"), "brier_mix": brier("p"),
                    "uspesnost": round(sum(y) / len(y), 3),
                    "roi_ploche": round(sum((float(r["kurz_vstup"]) - 1) if yi else -1.0 for r, yi in zip(h, y)) / len(h), 4)})
    return out


def souhrn_text(s):
    if not s or not s.get("n"):
        return ""
    t = [f"📊 Log Fortuny: {s['n']} linií"]
    if s.get("clv_n"):
        t.append(f"CLV {s['clv_prumer'] * 100:+.1f} % ({s['clv_kladne'] * 100:.0f} % linií se sebralo za lepší kurz než těsně před startem)")
    if s.get("vyhodnoceno"):
        t.append(f"vyhodnoceno {s['vyhodnoceno']}: Brier model {s['brier_model']} / trh {s['brier_trh']} / mix {s['brier_mix']}, "
                 f"ROI plochého vkladu {s['roi_ploche'] * 100:+.1f} %")
    else:
        t.append("zatím nic vyhodnoceno")
    return " | ".join(t)
