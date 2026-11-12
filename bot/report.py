import datetime
import html
import json
import urllib.request
from zoneinfo import ZoneInfo
from . import config, report_prehled

CSS = """
:root{color-scheme:dark;--bg:#0b0f14;--card:#141a22;--card2:#1a222c;--txt:#e8eef5;--mut:#8f9bab;--line:#2a3441;--acc:#5aa9ff;--ok:#34c76b;--bad:#ff5c57;--warn:#e0a82e;--box:#14233a;--r:12px}
*{box-sizing:border-box}
body{font:15px/1.5 system-ui,-apple-system,"Segoe UI",Roboto,Arial,sans-serif;margin:0;background:var(--bg);color:var(--txt)}
.c{max-width:1040px;margin:0 auto;padding:12px 14px 60px}
h1{font-size:26px;margin:14px 0 4px;letter-spacing:-.3px}
h2{font-size:19px;margin:34px 0 10px;padding:10px 14px;background:linear-gradient(90deg,var(--card2),transparent);border-left:4px solid var(--acc);border-radius:6px;scroll-margin-top:64px}
h3{font-size:16px;margin:22px 0 4px}
a{color:var(--acc);text-decoration:none}a:hover{text-decoration:underline}
.mut{color:var(--mut);font-size:13px}
.txt{line-height:1.65;text-align:left;max-width:75ch}
p{margin:8px 0}
details{margin:8px 0;background:var(--card);border:1px solid var(--line);border-radius:var(--r);padding:8px 12px}summary{cursor:pointer;color:var(--mut)}
.w{overflow-x:auto;margin:8px 0;border:1px solid var(--line);border-radius:var(--r);background:var(--card)}
table{border-collapse:collapse;width:100%;font-size:14px}
th,td{padding:9px 12px;text-align:left;vertical-align:middle;border-bottom:1px solid var(--line)}
th{background:var(--card2);color:var(--mut);font-size:11.5px;text-transform:uppercase;letter-spacing:.5px;font-weight:600;white-space:nowrap}
tr:last-child td{border-bottom:0}tbody tr:hover td,tr:hover td{background:#18212c}
.box{background:var(--box);border-left:4px solid var(--acc);padding:10px 14px;border-radius:8px;margin:14px 0}
nav{position:sticky;top:0;z-index:5;display:flex;gap:6px;overflow-x:auto;padding:10px 0;background:linear-gradient(var(--bg) 80%,transparent);margin:0 -2px}
nav a{white-space:nowrap;padding:6px 12px;border:1px solid var(--line);border-radius:999px;background:var(--card);font-size:13px;color:var(--txt)}
nav a:hover{border-color:var(--acc);text-decoration:none}
.kpi{display:grid;grid-template-columns:repeat(auto-fit,minmax(130px,1fr));gap:10px;margin:14px 0}
.kpi div{background:var(--card);border:1px solid var(--line);border-radius:var(--r);padding:12px 14px}
.kpi b{display:block;font-size:24px;line-height:1.1}.kpi span{color:var(--mut);font-size:12px}
.pill{display:inline-block;min-width:52px;text-align:center;padding:3px 10px;border-radius:999px;font-weight:700;font-size:13px;border:1px solid transparent}
.pg{background:#12301f;color:var(--ok);border-color:#1f5a36}.py{background:#33290d;color:var(--warn);border-color:#5b4a14}.pr{background:#341616;color:var(--bad);border-color:#5e2626}
.bar{height:6px;background:var(--line);border-radius:3px;overflow:hidden;margin-top:6px;min-width:90px}.bar i{display:block;height:100%;background:var(--acc)}
.ana{background:var(--card);border:1px solid var(--line);border-radius:var(--r);padding:4px 18px 12px;margin:14px 0}
.ana h3{margin-top:14px}
.live{color:var(--ok);font-weight:bold}.paper{color:var(--mut)}.ok{color:var(--ok)}.veto{color:var(--bad)}.nej{color:var(--warn)}
@media(max-width:640px){body{font-size:14px}.c{padding:8px 8px 40px}h1{font-size:21px}th,td{padding:7px 8px}.ana{padding:2px 12px 10px}}
"""

def _e(x): return html.escape(str(x), quote=True)
def _vyber(p): return "Remíza" if p["vyber"] == "Draw" else p["vyber"]
def _cas(iso, zona): return datetime.datetime.fromisoformat(iso).astimezone(ZoneInfo(zona)).strftime("%d.%m. %H:%M")
def _pct(x): return "–" if x is None else f"{x * 100:+.1f} %"

def _veto_html(p):
    v = p.get("veto", "")
    cls = {"OK": "ok", "VETO": "veto"}.get(v, "nej")
    txt = {"OK": "✅ OK", "VETO": "⛔ VETO"}.get(v, "❔ " + (v or "NEOVĚŘENO"))
    d = p.get("veto_duvod", "")
    return f"<span class='{cls}'>{_e(txt)}</span>" + (f"<br><span class='mut'>{_e(d)}</span>" if d else "")

def _tab_picks(picks, zona):
    if not picks: return "<p>Dnes nic nesplnilo podmínky (a to je v pořádku: žádná hrana = žádná sázka).</p>"
    r = ["<div class='w'><table><tr><th>Zápas</th><th>Výběr</th><th>Fér kurz</th><th>Sázej od</th><th>Nejlepší kurz</th><th>Edge</th><th>Stake*</th><th>Režim</th><th>Kontrola</th></tr>"]
    for p in picks:
        rez = "<span class='live'>SÁZET</span>" if p["rezim"] == "live" else "<span class='paper'>sledovat</span>"
        riz = f"<br><span class='nej'>⚠️ {_e(p['riziko'])}</span>" if p["riziko"] else ""
        r.append(f"<tr><td>{_e(p['zapas'])}<br><span class='mut'>{_e(p['sport'])} · {_cas(p['start'], zona)}</span></td><td><b>{_e(_vyber(p))}</b></td><td>{p['fair_kurz']}</td><td><b>{p['min_kurz']}</b></td><td>{p['best_kurz']}<br><span class='mut'>{_e(p['best_kniha'])}</span></td><td>{float(p['edge']) * 100:.1f} %{riz}{('<br><b>' + _e(p['moje_info']) + '</b>') if p.get('moje_info') else ''}</td><td>{p['stake_pct']} %</td><td>{rez}</td><td>{_veto_html(p)}</td></tr>")
    r.append("</table></div><p class='mut'>*Stake = ¼ Kelly, strop 2 % bankrollu.</p>")
    for p in picks:
        if p.get("analyza"):
            r.append(f"<h3>Analýza: {_e(p['zapas'])} <span class='mut'>({_e(p['sport'])}, {_e(_vyber(p))})</span></h3>{_analyza_html(p['analyza'])}")
    return "".join(r)

def _tab_metriky(rows_metr):
    if not rows_metr: return "<p class='mut'>Zatím žádné vyhodnocené sázky.</p>"
    r = ["<div class='w'><table><tr><th>Sport / Kategorie</th><th>N</th><th>Úspěšnost</th><th>Očekáváno</th><th>ROI paper ± CI (95%)</th><th>Sázek do jistoty</th><th>Ø CLV</th><th>ROI reálně</th></tr>"]
    for k, m in rows_metr.items():
        if not m.get("n"): continue
        real = "–" if m["roi_real"] is None else f"{_pct(m['roi_real'])} ({m['n_real']})"
        ci_text = f" ±{m.get('ci_95', 0)*100:.1f}%" if m.get("n") > 2 else ""
        r.append(f"<tr><td><b>{_e(k)}</b></td><td>{m['n']}</td><td>{m['winrate'] * 100:.1f} %</td><td>{m['ocekavany_winrate'] * 100:.1f} %</td><td><b>{_pct(m['roi_paper'])}{ci_text}</b></td><td>{m.get('sazek_do_jistoty', 'N/A')}</td><td>{_pct(m['avg_clv'])}</td><td>{real}</td></tr>")
    r.append("</table></div><p class='mut'><b>Sázek do jistoty:</b> Kolik tiketů je matematicky potřeba k potvrzení, že ROI není jen náhoda (pokud ukazuje 0, edge je prokázána). CI = Confidence Interval.</p>")
    return "".join(r)

NAZVY = {"goly": "Góly", "rohy": "Rohy", "karty": "Karty", "fauly": "Fauly", "sot": "Střely na bránu"}
def _noha(v, L, s): return f"{NAZVY.get(v, v)} {'Over' if s == 'over' else 'Under'} {L}"

def _tab_doplnkove(zapasy, kalib, zona):
    if not zapasy: return "<p class='mut'>Dnes žádný signál z vlastního modelu.</p>"
    o = []
    for z in zapasy:
        o.append(f"<h3>{_e(z['zapas'])} <span class='mut'>({_cas(z['start'], zona)})</span></h3>")
        if z["linie"]:
            o.append("<div class='w'><table><tr><th>Trh</th><th>P</th><th>Fér kurz</th><th>Sázej od</th></tr>")
            for l in z["linie"]: o.append(f"<tr><td>{_e(_noha(l['var'], l['linie'], l['strana']))}</td><td>{l['p'] * 100:.0f} %</td><td>{l['fair']}</td><td><b>{l['min_kurz']}</b></td></tr>")
            o.append("</table></div>")
        if z["builder"]:
            o.append("<div class='w'><table><tr><th>Builder (2 nohy)</th><th>P</th><th>Fér kurz</th><th>Sázej od</th><th>Korelace</th></tr>")
            for b in z["builder"]:
                txt = " + ".join(_noha(*n) for n in b["nohy"])
                o.append(f"<tr><td>{_e(txt)}</td><td>{b['p'] * 100:.0f} %</td><td>{b['fair']}</td><td><b>{b['min_kurz']}</b></td><td>×{b['korelace']}</td></tr>")
            o.append("</table></div>")
    return "".join(o)

IK = {"OK": "✅ OK", "VETO": "⛔ VETO", "NEJISTE": "❔ NEJISTÉ", "NEOVERENO": "❔ NEOVĚŘENO"}

def _blok(nazev, d):
    if not d: return ""
    if isinstance(d, str): return f"<li><b>{_e(nazev)}:</b> {_e(d)}</li>"
    cast = [str(v) for k, v in d.items() if k != "stav" and v]
    stav = f" <span class='mut'>({_e(d['stav'])})</span>" if d.get("stav") else ""
    return f"<li><b>{_e(nazev)}:</b> {_e(' – '.join(cast))}{stav}</li>" if cast else ""

def _analyza_html(an):
    if not an: return ""
    o = [f"<p><b>{IK.get(an.get('verdikt'), '❔')}</b> {_e(an.get('duvod', ''))}</p>"]
    if an.get("souhrn"): o.append(f"<p>{_e(an['souhrn'])}</p>")
    fak = "".join([_blok("Rozhodčí", an.get("rozhodci")), _blok("Hřiště", an.get("hriste")), _blok("Počasí", an.get("pocasi")),
                   _blok("Sestavy a zranění", an.get("sestavy_zraneni")), _blok("Program a únava", an.get("program"))])
    for f in an.get("faktory") or []:
        if not isinstance(f, dict): continue
        stav = f" <span class='mut'>({_e(f.get('stav', ''))})</span>" if f.get("stav") else ""
        dop = f" <b>{_e(f['dopad'])}</b>" if f.get("dopad") else ""
        fak += f"<li><b>{_e(str(f.get('kriterium', '')).replace('_', ' '))}:</b> {_e(f.get('zjisteni', ''))}{stav}{dop}</li>"
    if fak: o.append(f"<ul>{fak}</ul>")
    if an.get("pro"): o.append("<p><b>Pro:</b></p><ul>" + "".join(f"<li>{_e(x)}</li>" for x in an["pro"]) + "</ul>")
    if an.get("proti"): o.append("<p><b>Proti / riziko:</b></p><ul>" + "".join(f"<li>{_e(x)}</li>" for x in an["proti"]) + "</ul>")
    if an.get("riziko"): o.append(f"<p class='mut'>Hlavní riziko: {_e(an['riziko'])}</p>")
    return "".join(o)

def _duv(f, cfg=None):
    from . import tipsteri
    try: return tipsteri.duvera_10(f, cfg)
    except Exception: return None

def _prozaicky(an):
    """Souvislý rozbor zápasu; faktory, pro a proti jsou sbalené pod ním."""
    if not an: return ""
    text = an.get("text") or an.get("souhrn") or ""
    o = [f"<p><b>{IK.get(an.get('verdikt'), '❔')}</b> {_e(an.get('duvod', ''))}</p>"] if an.get("duvod") else []
    if text: o.append(f"<p class='txt'>{_e(text)}</p>")
    if an.get("riziko"): o.append(f"<p class='mut'>⚠️ Hlavní riziko: {_e(an['riziko'])}</p>")
    zbytek = _analyza_html({**an, "souhrn": "", "duvod": "", "riziko": ""})
    if zbytek: o.append(f"<details><summary class='mut'>Faktory, pro a proti</summary>{zbytek}</details>")
    return "".join(o)

def _tab_fortuna(fort, zona):
    if not fort: return "<p class='mut'>Žádná linie s dostatečnou hranou.</p>"
    z = {}
    for f in fort: z.setdefault(f["zapas"], []).append(f)
    r = []
    for zapas, pl in z.items():
        f0 = pl[0]
        koment = {k.get("trh"): k.get("komentar", "") for k in (f0.get("analyza") or {}).get("komentare_k_trhum", [])}
        r.append(f"<h3>ZÁPAS: {_e(zapas)} <span class='mut'>({_e(f0['liga'])}, {_cas(f0['start'], zona)})</span></h3>")
        r.append("<div class='w'><table><tr><th>Příležitost (trh a tip)</th><th>Kurz Fortuna</th><th>Sázej od (min. kurz)</th><th>Pravděpodobnost</th><th>Důvěra</th><th>Hrana</th></tr>")
        for f in pl:
            d = _duv(f)
            r.append(f"<tr><td>{_e(f['trh'])}</td><td>{f['kurz_fortuna']}</td><td><b>{f['sazej_od']}+</b></td><td><b>{f['p'] * 100:.0f} %</b> <span class='mut'>(model {f['p_model'] * 100:.0f}, trh {f['p_trh'] * 100:.0f})</span></td><td><b>{d if d else '–'}/10</b></td><td>{f['edge'] * 100:+.1f} %</td></tr>")
            if koment.get(f["trh"]): r.append(f"<tr><td colspan='6' class='mut'>{_e(koment[f['trh']])}</td></tr>")
        r.append("</table></div>")
        r.append(_prozaicky(f0.get("analyza")))
    return "".join(r)

def _tab_tipdne(fort, zona):
    tip = sorted((f for f in (fort or []) if f.get("tip_dne")), key=lambda f: f["tip_dne"])
    if not tip: return "<p class='mut'>Dnes žádný kandidát nepřekročil práh.</p>"
    r = ["<div class='w'><table><tr><th>#</th><th>Zápas</th><th>Trh</th><th>Kurz Fortuna</th><th>Sázej od</th><th>Pravděpodobnost</th><th>Důvěra</th><th>Hrana</th></tr>"]
    for f in tip:
        an = f.get("analyza") or {}
        r.append(f"<tr><td>{f['tip_dne']}</td><td>{_e(f['zapas'])}<br><span class='mut'>{_e(f['liga'])}, {_cas(f['start'], zona)}</span></td><td>{_e(f['trh'])}<br><span class='mut'>{_e(f.get('rodina', ''))}</span></td><td>{f['kurz_fortuna']}</td><td><b>{f['sazej_od']}</b></td><td>{f['p'] * 100:.0f} %</td><td>{_duv(f) or '–'}/10</td><td>{f['edge'] * 100:+.1f} %</td></tr>")
    r.append("</table></div>")
    return "".join(r)

def _tab_jistejsi(fort, zona):
    js = sorted((f for f in (fort or []) if f.get("jistejsi")), key=lambda f: f["jistejsi"])
    if not js: return "<p class='mut'>Dnes žádný kandidát s vyšší pravděpodobností a dostatečnou hranou.</p>"
    r = ["<div class='w'><table><tr><th>#</th><th>Zápas</th><th>Trh</th><th>Kurz Fortuna</th><th>Sázej od</th><th>Pravděpodobnost</th><th>Důvěra</th><th>Vklad</th></tr>"]
    for f in js:
        r.append(f"<tr><td>{f['jistejsi']}</td><td>{_e(f['zapas'])}<br><span class='mut'>{_e(f['liga'])}, {_cas(f['start'], zona)}</span></td><td>{_e(f['trh'])}</td><td>{f['kurz_fortuna']}</td><td><b>{f['sazej_od']}</b></td><td>{f['p'] * 100:.0f} %</td><td>{_duv(f) or '–'}/10</td><td>~{f.get('vklad_pct', 0)} % banku</td></tr>")
    r.append("</table></div>")
    return "".join(r)

def _tabulka_tiketu(t, zona, nadpis):
    if not t: return ""
    r = [f"<p><b>{_e(nadpis)}</b> — celkový kurz <b>{t['kurz']:.2f}</b>, pravděpodobnost výhry <b>{t['p'] * 100:.0f} %</b>, důvěra <b>{t['duvera']}/10</b>, "
         f"min. celkový kurz na Tipsportu <b>{t['min_celkovy_kurz']:.2f}</b></p>",
         "<div class='w'><table><tr><th>Zápas</th><th>Sázka</th><th>Start</th><th>Kurz Fortuna</th><th>Sázej od</th><th>p</th></tr>"]
    for c in t["noze"]:
        r.append(f"<tr><td>{_e(c['zapas'])}<br><span class='mut'>{_e(c.get('sport') or '')}, {_e(c.get('liga') or '')}</span></td><td>{_e(c['trh'])}{(': <b>' + _e(c['vyber']) + '</b>') if c['vyber'] else ''}"
                 f"{' <span class=mut>(model)</span>' if c['zdroj'] == 'model' else ''}</td><td>{_cas(c['start'], zona)}</td><td>{_kc(c['kurz'])}</td><td><b>{_kc(c['sazej_od'])}+</b></td><td>{c['p'] * 100:.0f} %</td></tr>")
    r.append("</table></div>")
    if t["hrana"] < 0:
        r.append(f"<p class='mut'>Hrana {t['hrana'] * 100:+.1f} %: tiket je poskládaný z férových kurzů trhu (bez modelu), očekávaný výnos je záporný o marži.</p>")
    else:
        r.append(f"<p class='mut'>Hrana {t['hrana'] * 100:+.1f} % (část sázek má model).</p>")
    return "".join(r)

def _tab_denni(tik, zona):
    if not tik or not tik.get("denni"): return "<p class='mut'>Dnes se nepodařilo poskládat tiket na kurz 2.00 (málo zápasů v okně).</p>"
    return _tabulka_tiketu(tik["denni"], zona, "Hlavní tiket") + _tabulka_tiketu(tik.get("denni_alt"), zona, "Alternativa (jiné zápasy)")

def _tab_pyramida(tik, zona):
    if not tik or not tik.get("pyramida"): return "<p class='mut'>Dnes nejsou data na Pyramidu.</p>"
    r = ["<p class='mut'>Každé kolo je samostatný tiket: musí vyhrát s celkovým kurzem aspoň požadovaným (kolo 1 = 1.10, 2 = 2.00 … 10 = 10.00). Vyber ten, který odpovídá tvému kolu. Min. vklad 50 Kč.</p>"]
    for k in tik["pyramida"]:
        if not k["tiket"]:
            r.append(f"<h3>Kolo {k['kolo']} (min. kurz {k['prah']:.2f})</h3><p class='mut'>Dnes nelze poskládat.</p>"); continue
        r.append(f"<h3>Kolo {k['kolo']} <span class='mut'>(min. kurz {k['prah']:.2f})</span></h3>" + _tabulka_tiketu(k["tiket"], zona, "Hlavní tiket") + _tabulka_tiketu(k.get("alt"), zona, "Alternativa (jiné zápasy)"))
    return "".join(r)

def _wa_tikety(tik, zona):
    from . import tikety
    if not tik: return []
    r = []
    d = tik.get("denni")
    if d:
        r += ["", f"🎟️ *DENNÍ TIKET (kurz ~2.00)* p {d['p'] * 100:.0f} %, důvěra {d['duvera']}/10, min. celkový kurz {d['min_celkovy_kurz']:.2f}"]
        r += [f"   • {c['zapas']} – {c['vyber'] or c['trh']} (od {c['sazej_od']}, Fortuna {c['kurz']})" for c in d["noze"]]
        if d["hrana"] < 0: r.append("   ℹ️ jen férové kurzy trhu, bez hrany")
    r += ["", "🔺 *PYRAMIDA* (tiket pro tvé kolo):"]
    for k in tik.get("pyramida") or []:
        t = k["tiket"]
        if not t: r.append(f"{k['kolo']}. kolo (≥{k['prah']:.2f}): nelze"); continue
        r.append(f"{k['kolo']}. kolo (≥{k['prah']:.2f}) p {t['p'] * 100:.0f} %, důvěra {t['duvera']}/10:")
        r += [f"   • {c['zapas'][:38]} – {(c['vyber'] or c['trh'])[:34]} (od {c['sazej_od']})" for c in t["noze"]]
    return r

def _tab_univ(univ, zona):
    if not univ: return "<p class='mut'>Žádný kandidát.</p>"
    r = []
    for c in univ:
        r.append(f"<h3>{_e(str(c['sport']).upper())} · ZÁPAS: {_e(c['zapas'])} <span class='mut'>({_e(c.get('liga') or '')}, {_cas(c['start'], zona)})</span></h3>")
        r.append("<div class='w'><table><tr><th>Příležitost (trh a tip)</th><th>Kurz Fortuna</th><th>Sázej od (min. kurz)</th><th>Pravděpodobnost</th><th>Důvěra</th></tr>")
        r.append(f"<tr><td>{_e(c['trh'])}: <b>{_e(c['vyber'])}</b></td><td>{c['kurz']}</td><td><b>{c.get('sazej_od', '–')}+</b></td>"
                 f"<td><b>{c['p'] * 100:.0f} %</b></td><td><b>{c.get('duvera') or '–'}/10</b></td></tr></table></div>")
        r.append(_prozaicky(c.get("analyza")))
    return "".join(r)


def _kc(v):
    return "–" if v is None else f"{float(v):.2f}"


def _pil_p(p):
    t = "pg" if p >= 0.75 else "py" if p >= 0.55 else "pr"
    return f"<span class='pill {t}'>{p * 100:.0f} %</span>"


def _pil_d(d):
    if not d: return "<span class='mut'>–</span>"
    t = "pg" if d >= 7 else "py" if d >= 5 else "pr"
    return f"<span class='pill {t}'>{d}/10</span>"


def _kompakt(radky, zona, prazdno):
    """Přehledová tabulka: jeden řádek na příležitost, klik na řádek rozbalí rozbor zápasu. Řádek = dict s klíči zapas, liga, start, trh, kurz, sazej_od, p, duvera, analyza, hrana (volitelně)."""
    if not radky: return f"<p class='mut'>{_e(prazdno)}</p>"
    r = ["<div class='w'><table><tr><th>Kdy</th><th>Příležitost (zápas a tip)</th><th>Kurz Fortuna</th><th>Sázej od</th><th>Pravděpodobnost</th><th>Důvěra</th></tr>"]
    for x in radky:
        hr = f"<br><span class='mut'>hrana {x['hrana'] * 100:+.1f} %</span>" if x.get("hrana") is not None else ""
        an = _prozaicky(x.get("analyza"))
        kl = " class='klik'" if an else ""
        sip = "<br><span class='sipka'>▼ rozbor</span>" if an else ""
        r.append(f"<tr{kl}><td class='kdy'>{_cas(x['start'], zona)}</td>"
                 f"<td><span class='m'>{_e(x['zapas'])}</span><br><span class='mut'>{_e(x.get('sport') or '')} {_e(x.get('liga') or '')}</span><br>{_e(x['trh'])}{(': <b>' + _e(x['vyber']) + '</b>') if x.get('vyber') else ''}{sip}</td>"
                 f"<td>{_kc(x['kurz'])}</td><td><b>{_kc(x.get('sazej_od'))}+</b></td>"
                 f"<td>{_pil_p(x['p'])}{hr}</td><td>{_pil_d(x.get('duvera'))}</td></tr>")
        if an:
            r.append(f"<tr class='roz'><td colspan='6'>{an}</td></tr>")
    r.append("</table></div>")
    return "".join(r)


def _z_fort(f):
    return {"zapas": f["zapas"], "sport": f.get("sport") or "", "analyza": f.get("analyza"), "liga": f.get("liga"), "start": f["start"], "trh": f["trh"], "vyber": "", "kurz": f["kurz_fortuna"],
            "sazej_od": f["sazej_od"], "p": f["p"], "duvera": _duv(f), "hrana": f.get("edge")}


def vyber_value_drop(fort, cfg=None):
    """Největší hrana modelu proti trhu: tam se kurz nejspíš sníží (CLV to ověřuje)."""
    n = int(((cfg or {}).get("report") or {}).get("value_drop_max", 5))
    return sorted((f for f in (fort or []) if f.get("edge") is not None), key=lambda f: -f["edge"])[:n]


def vyber_fild(fort, cfg=None):
    """Fildův tip: statistické trhy (rohy, střely, fauly, karty) s kurzem od `fild_min_kurz`; nejvyšší hrana napřed."""
    r = ((cfg or {}).get("report") or {})
    kmin, n = float(r.get("fild_min_kurz", 1.80)), int(r.get("fild_max", 5))
    rodiny = [x.lower() for x in r.get("fild_rodiny", ["rohy", "střely", "fauly", "karty"])]
    kand = [f for f in (fort or []) if f["kurz_fortuna"] >= kmin and any(x in (f.get("rodina") or "").lower() for x in rodiny)]
    return sorted(kand, key=lambda f: (-f["edge"], -f["p"]))[:n]


def _analyzy(sekce):
    """Souvislé rozbory zápasů ke všem tabulkám výše; každý zápas jednou. sekce = [(zdroj, polozka)] v pořadí důležitosti."""
    videno, r = set(), []
    for zdroj, f in sekce:
        if f["zapas"] in videno or not f.get("analyza"): continue
        videno.add(f["zapas"])
        if zdroj == "fort":
            sirka = f"{_e(f['trh'])}"
            r.append(f"<h3>ZÁPAS: {_e(f['zapas'])} <span class='mut'>({_e(f.get('liga') or '')}, {{cas}})</span></h3><p class='mut'>{sirka}: kurz {f['kurz_fortuna']}, sázej od {_kc(f['sazej_od'])}+, p {f['p'] * 100:.0f} % (model {f['p_model'] * 100:.0f}, trh {f['p_trh'] * 100:.0f}), důvěra {_duv(f) or '–'}/10</p>"
                     + _prozaicky(f["analyza"]))
        else:
            r.append(f"<h3>{_e(str(f.get('sport') or '').upper())} · ZÁPAS: {_e(f['zapas'])} <span class='mut'>({_e(f.get('liga') or '')}, {{cas}})</span></h3><p class='mut'>{_e(f['trh'])}: {_e(f.get('vyber') or '')}, kurz {f['kurz']}, sázej od {_kc(f.get('sazej_od'))}+, p {f['p'] * 100:.0f} %, důvěra {f.get('duvera') or '–'}/10</p>"
                     + _prozaicky(f["analyza"]))
        r[-1] = "<article class='ana'>" + r[-1].replace("{cas}", "{CAS:" + f["start"] + "}") + "</article>"
    return r


def _dosad_cas(text, zona):
    import re
    return re.sub(r"\{CAS:([^}]*)\}", lambda m: _cas(m.group(1), zona), text)


def sestav_report(datum, picks, vyrazene, vcera, celkem, zona, dopl=None, kalib=None, fort=None, univ=None, tik=None, jist=None, cfg=None, uceni=None, model_text=""):
    vc = f"<div class='box'><b>Včera:</b> {_e(vcera)}</div>" if vcera else ""
    vd, fild = vyber_value_drop(fort, cfg), vyber_fild(fort, cfg)
    h2h = ("<p><b>H2H (srovnání knih):</b></p>" + _tab_picks(picks, zona)) if picks else ""
    prehled = (
        "<h2 id='vd'>💧 1) Value drop</h2><p class='mut'>Největší rozdíl mezi modelem a kurzem trhu: kurz se tu nejspíš sníží. Skutečné snížení bot dál ověřuje (CLV).</p>"
        + _kompakt([_z_fort(f) for f in vd], zona, "Dnes žádný kandidát s dostatečnou hranou.") + h2h
        + "<h2 id='fild'>🎯 2) Fildův tip</h2><p class='mut'>Statistické trhy (rohy, střely, fauly, karty) s kurzem od %.2f; to, co se skutečně hraje.</p>" % float(((cfg or {}).get("report") or {}).get("fild_min_kurz", 1.80))
        + _kompakt([_z_fort(f) for f in fild], zona, "Dnes žádná statistická příležitost s tak vysokým kurzem a hranou.")
        + "<h2 id='tip'>🛡️ 3) Tipsport od kurzu 1.30 (z celé nabídky)</h2><p class='mut'>Seřazeno od nejvyšší pravděpodobnosti. Kliknutím na řádek se rozbalí rozbor zápasu. Pravděpodobnost je u sportů bez modelu jen férový trh.</p>"
        + _kompakt(sorted(univ or [], key=lambda c: -c["p"]), zona, "Žádný kandidát.")
        + "<h2 id='jist'>🔒 4) Nejjistější dne (libovolný kurz)</h2><p class='mut'>Nejvyšší pravděpodobnost z celé dnešní nabídky, ověřená rozborem. Žádná sázka není stoprocentní.</p>"
        + _kompakt(jist, zona, "Dnes žádná sázka nepřekročila práh jistoty.")
        + "<h2 id='den'>🎟️ 5) Denní tiket na kurz ~2.00</h2>" + _tab_denni(tik, zona))
    sekce = [("fort", f) for f in vd + fild] + [("univ", c) for c in (univ or [])] + [("univ", c) for c in (jist or [])]
    analyzy = "".join(_dosad_cas("".join(_analyzy(sekce)), zona)) or "<p class='mut'>Dnes bez rozborů.</p>"
    nav = ("<nav><a href='#vcera'>Včera</a><a href='#vd'>Value drop</a><a href='#fild'>Fildův tip</a><a href='#tip'>Tipsport 1.30+</a><a href='#jist'>Nejjistější</a>"
           "<a href='#den'>Denní tiket</a><a href='#ana'>Analýzy</a><a href='#uc'>Učení</a><a href='#pyr'>Pyramida</a></nav>")
    kpi = ("<div class='kpi'>" + "".join(f"<div><b>{n}</b><span>{t}</span></div>" for n, t in (
        (len(vd), "Value drop"), (len(fild), "Fildův tip"), (len(univ or []), "Tipsport 1.30+"), (len(jist or []), "Nejjistější dne"),
        (len({c["zapas"] for _, c in sekce if c.get("analyza")}), "rozborů zápasů"))) + "</div>")
    dalsi = (f"<h2 id='uc'>📈 Učení bota: přehled a postup</h2>{_tab_uceni(uceni, model_text)}"
             f"<details><summary><b>Doplňkové trhy (model)</b></summary>{_tab_doplnkove(dopl, kalib, zona)}</details>"
             f"<details><summary><b>Dosavadní bilance</b></summary>{_tab_metriky(celkem)}</details>")
    return (f"<!DOCTYPE html><html lang='cs'><head><meta charset='UTF-8'><meta name='viewport' content='width=device-width, initial-scale=1.0'><title>TIPOVACI_BOT</title><style>{CSS}{report_prehled.CSS}</style></head>"
            f"<body><div class='c'><a href='../index.html'>⬅ Archiv</a><h1>Ranní report {datum}</h1>{vc}{nav}{report_prehled.horni(uceni)}{report_prehled.vcera(uceni)}{prehled}<h2 id='ana'>📝 Analýzy zápasů</h2>{analyzy}{dalsi}"
            f"<h2 id='pyr'>🔺 Pyramida: tiket pro každé kolo</h2>{_tab_pyramida(tik, zona)}</div>{report_prehled.SCRIPT}</body></html>")

def _r_stat(n, s):
    if not s.get("n"): return f"<tr><td>{_e(n)}</td><td colspan='5' class='mut'>zatím nic vyhodnoceno</td></tr>"
    rozdil = (s["uspesnost"] - s["cekano"]) * 100
    return (f"<tr><td>{_e(n)}</td><td>{s['n']}</td><td><b>{s['uspesnost'] * 100:.0f} %</b></td><td>{s['cekano'] * 100:.0f} %</td>"
            f"<td>{rozdil:+.1f} b.</td><td>{s['roi'] * 100:+.1f} %</td></tr>")


def _t_stat(hlavicka, radky):
    if not radky: return "<p class='mut'>Zatím žádná data.</p>"
    r = [f"<div class='w'><table><tr><th>{_e(hlavicka)}</th><th>Sázek</th><th>Úspěšnost</th><th>Čekáno (trh)</th><th>Rozdíl</th><th>ROI (flat)</th></tr>"]
    r += [_r_stat(k, v) for k, v in sorted(radky.items(), key=lambda x: -x[1].get("n", 0))]
    return "".join(r) + "</table></div>"


def _tab_uceni(u, model_text=""):
    if not u: return "<p class='mut'>Přehled se nepodařilo sestavit.</p>"
    r = []
    if u["chyby"]:
        r.append("<h3>Kde se bot včera spletl</h3><p class='mut'>Nejpravděpodobnější sázky, které nevyšly:</p><ul>" + "".join(
            f"<li>{_e(c['zapas'])} – {_e(c['trh'])}{(': ' + _e(c['vyber'])) if c['vyber'] else ''}, kurz {c['kurz']}, čekáno {float(c['p']) * 100:.0f} %</li>" for c in u["chyby"]) + "</ul>")
    c = u["celkem"]
    r.append("<h3>Celková bilance učení</h3>")
    if c.get("n"):
        r.append(f"<p>Zapsáno <b>{u['zapsano']}</b> sázek, vyhodnoceno <b>{u['vyhodnoceno']}</b>. Úspěšnost <b>{c['uspesnost'] * 100:.1f} %</b> "
                 f"(čekáno {c['cekano'] * 100:.1f} %), ROI (flat) <b>{c['roi'] * 100:+.1f} %</b>. Tempo ~{u['tempo_den']:.0f} vyhodnocených sázek denně.</p>")
        r.append("<p class='mut'>Rozdíl = úspěšnost minus čekaná pravděpodobnost trhu (v procentních bodech). Kladný = trh podceňuje, záporný = přeceňuje. "
                 "ROI je záporné o marži kanceláře, dokud nenajdeme systematickou chybu trhu.</p>")
    else:
        r.append(f"<p class='mut'>Zapsáno {u['zapsano']} sázek, zatím žádná není vyhodnocená.</p>")
    r.append(_t_stat("Sport", u["sporty"]))
    r.append(_t_stat("Kategorie (co bot ukazuje)", u["skupiny"]))
    r.append(_t_stat("Pásmo kurzu", u["pasma"]))
    if model_text: r.append(f"<p class='mut'>Model fotbalu a tenisu: {_e(model_text)}</p>")
    r.append("<h3>Postup k dalším metám (kdy sáhnout do kódu)</h3><div class='w'><table><tr><th>Meta</th><th>Stav</th><th>Co to odemkne</th><th>Odhad</th></tr>")
    for m in u["mety"]:
        procent = f"{m['podil'] * 100:.0f} %"
        cil = f"{m['cil']} " + ("vyhodnocených celkem" if m["druh"] == "celkem" else "u sportu")
        if m["druh"] == "celkem":
            odhad = "splněno" if m["stav"] >= m["cil"] else (m["eta"] or "bez dat")
            stav = f"{m['stav']} / {m['cil']} ({procent})<div class='bar'><i style='width:{m['podil'] * 100:.0f}%'></i></div>"
        else:
            dosazene = [sp for sp, v in m["sporty"].items() if v["n"] >= m["cil"]]
            nej = sorted(((v["n"], sp, v["eta"]) for sp, v in m["sporty"].items() if v["n"] < m["cil"]), reverse=True)[:2]
            stav = f"nejdál {m['stav']} / {m['cil']} ({procent})<div class='bar'><i style='width:{m['podil'] * 100:.0f}%'></i></div>" + (f"; splněno: {', '.join(dosazene)}" if dosazene else "")
            odhad = ", ".join(f"{sp} ~{e}" for _, sp, e in nej if e) or ("splněno" if dosazene else "bez dat")
        r.append(f"<tr><td>{_e(cil)}</td><td>{stav}</td><td>{_e(m['co'])}</td><td>{_e(odhad)}</td></tr>")
    r.append("</table></div>")
    return "".join(r)


def sestav_index(reporty, celkem, podle_tieru, podle_sportu, doporuceni):
    arch = "".join(f"<li><a href='reports/{_e(r)}.html'>{_e(r)}</a></li>" for r in reporty) or "<li>zatím nic</li>"
    dnes = f"<p><a href='reports/{_e(reporty[0])}.html'><b>🔥 Dnešní report ({_e(reporty[0])})</b></a></p>" if reporty else ""
    return f"<!DOCTYPE html><html lang='cs'><head><meta charset='UTF-8'><meta name='viewport' content='width=device-width, initial-scale=1.0'><title>TIPOVACI_BOT</title><style>{CSS}{report_prehled.CSS}</style></head><body><div class='c'><h1>🤖 TIPOVACI_BOT</h1>{dnes}<h2>Celkem</h2>{_tab_metriky({'vše': celkem})}<h2>Podle sportu</h2>{_tab_metriky(podle_sportu)}<h2>Archiv</h2><ul>{arch}</ul></div></body></html>"

def _wa_doplnkove(zapasy, zona, max_zapasu=3):
    r = ["", "🧩 *MODEL & BUILDERY*:"]
    for z in (zapasy or [])[:max_zapasu]:
        r.append(f"• *{z['zapas']}*")
        for l in sorted(z["linie"], key=lambda x: -x["p"])[:2]: r.append(f"   {_noha(l['var'], l['linie'], l['strana'])} → od *{l['min_kurz']}*" + (f" | 💱 {l['moje_info']}" if l.get("moje_info") else ""))
        if z["builder"]:
            b = z["builder"][0]
            r.append("   BB: " + " + ".join(_noha(*n) for n in b["nohy"]) + f" → od *{b['min_kurz']}* (korelace ×{b['korelace']})")
    return r if len(r) > 2 else []

def _wa_fortuna(fort, max_zapasu=4):
    if not fort: return []
    z = {}
    for f in fort: z.setdefault(f["zapas"], []).append(f)
    r = []
    tip = sorted((f for f in fort if f.get("tip_dne")), key=lambda f: f["tip_dne"])
    if tip:
        r += ["", "⭐ *TIP DNE* (nejlepší z celé nabídky):"]
        for f in tip:
            an = f.get("analyza") or {}
            r.append(f"{f['tip_dne']}. *{f['zapas']}* {IK.get(an.get('verdikt'), '')}\n   {f['trh']} → od *{f['sazej_od']}* (Fortuna {f['kurz_fortuna']}; p {f['p'] * 100:.0f} %, důvěra {_duv(f) or '–'}/10, vklad ~{f.get('vklad_pct', 0)} % banku)")
    js = sorted((f for f in fort if f.get("jistejsi")), key=lambda f: f["jistejsi"])
    if js:
        r += ["", "🛡️ *JISTĚJŠÍ* (vyšší úspěšnost, nižší kurz):"]
        for f in js:
            an = f.get("analyza") or {}
            r.append(f"• *{f['zapas']}* {IK.get(an.get('verdikt'), '')}\n   {f['trh']} → od *{f['sazej_od']}* (Fortuna {f['kurz_fortuna']}; p {f['p'] * 100:.0f} %, důvěra {_duv(f) or '–'}/10, vklad ~{f.get('vklad_pct', 0)} % banku)")
    r += ["", "🎯 *NABÍDKA vs. MODEL* (sázej od):"]
    for zapas, pl in list(z.items())[:max_zapasu]:
        an = pl[0].get("analyza") or {}
        r.append(f"• *{zapas}* {IK.get(an.get('verdikt'), '')}")
        for f in pl[:3]:
            r.append(f"   {f['trh']} → od *{f['sazej_od']}* (Fortuna {f['kurz_fortuna']}; p {f['p'] * 100:.0f} %, důvěra {_duv(f) or '–'}/10)")
        if an.get("souhrn"): r.append(f"   _{an['souhrn'][:230]}_")
        if an.get("riziko"): r.append(f"   ⚠️ {an['riziko'][:140]}")
    return r

def wa_ranni(datum, picks, vcera, url, zona, max_radku=6, dopl=None, fort=None, log_text="", univ=None, tik=None, jist=None):
    """WhatsApp: jen nadpis a odkaz na report (celý text je moc dlouhý)."""
    t = [f"🤖 *TIPOVACI_BOT | {datum}*"]
    if url: t += ["", f"📊 Dnešní report: {url}/reports/{datum}.html"]
    else: t += ["", "📊 Report je na GitHub Pages."]
    return "\n".join(t)

def posli_wa(text):
    inst, token, chat = config.env("WA_INSTANCE_ID"), config.env("WA_API_TOKEN"), config.env("WA_GROUP_ID")
    if not (inst and token and chat): return False
    api = config.env("WA_API_URL", "https://api.green-api.com").rstrip("/")
    url = f"{api}/waInstance{inst}/sendMessage/{token}"
    req = urllib.request.Request(url, data=json.dumps({"chatId": chat, "message": text}).encode("utf-8"), headers={"Content-Type": "application/json"}, method="POST")
    try: urllib.request.urlopen(req, timeout=30); return True
    except Exception: return False
