import datetime
import html
import json
import urllib.request
from zoneinfo import ZoneInfo
from . import config

CSS = """
:root{color-scheme:dark;--bg:#0d1117;--card:#161b22;--txt:#e6edf3;--mut:#8b949e;--line:#30363d;--acc:#58a6ff;--ok:#3fb950;--bad:#f85149;--warn:#d29922;--box:#16222f}
body{font-family:Arial,sans-serif;margin:0;padding:16px;background:var(--bg);color:var(--txt)}
.c{max-width:1080px;margin:0 auto;background:var(--card);padding:22px;border-radius:8px}
h1{font-size:22px;margin:0 0 6px}h2{font-size:18px;margin-top:28px;border-bottom:1px solid var(--line);padding-bottom:4px}
.mut{color:var(--mut);font-size:13px}a{color:var(--acc)}.txt{line-height:1.55;text-align:justify}details{margin:6px 0}summary{cursor:pointer}
.w{overflow-x:auto}table{border-collapse:collapse;width:100%;font-size:14px}
th,td{border:1px solid var(--line);padding:7px 9px;text-align:left;vertical-align:top}
th{background:var(--bg)}.box{background:var(--box);border-left:4px solid var(--acc);padding:10px 14px;border-radius:4px;margin:14px 0}
.live{color:var(--ok);font-weight:bold}.paper{color:var(--mut)}.ok{color:var(--ok)}.veto{color:var(--bad)}.nej{color:var(--warn)}
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
                 f"{' <span class=mut>(model)</span>' if c['zdroj'] == 'model' else ''}</td><td>{_cas(c['start'], zona)}</td><td>{c['kurz']}</td><td><b>{c['sazej_od']}+</b></td><td>{c['p'] * 100:.0f} %</td></tr>")
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
    r = "".join(f"<tr><td>{html.escape(str(c['sport']))}</td><td>{html.escape(str(c['zapas']))}</td><td>{html.escape(str(c['trh']))}: <b>{html.escape(str(c['vyber']))}</b></td><td>{c['kurz']}</td><td>{c['p'] * 100:.0f} %</td></tr>" for c in univ)
    return f"<p class='mut'>Bez modelu, jen férová pravděpodobnost trhu.</p><table><tr><th>Sport</th><th>Zápas</th><th>Výběr</th><th>Kurz</th><th>p</th></tr>{r}</table>"


def sestav_report(datum, picks, vyrazene, vcera, celkem, zona, dopl=None, kalib=None, fort=None, univ=None, tik=None):
    vc = f"<div class='box'><b>Včera:</b> {_e(vcera)}</div>" if vcera else ""
    return f"<!DOCTYPE html><html lang='cs'><head><meta charset='UTF-8'><meta name='viewport' content='width=device-width, initial-scale=1.0'><title>TIPOVACI_BOT</title><style>{CSS}</style></head><body><div class='c'><a href='../index.html'>⬅ Archiv</a><h1>Ranní report {datum}</h1>{vc}<h2>⭐ Tip dne</h2>{_tab_tipdne(fort, zona)}<h2>🛡️ Jistější tipy</h2>{_tab_jistejsi(fort, zona)}<h2>🎟️ Denní tiket na kurz ~2.00</h2>{_tab_denni(tik, zona)}<h2>🔺 Pyramida: tiket pro každé kolo</h2>{_tab_pyramida(tik, zona)}<h2>Analýzy zápasů</h2>{_tab_fortuna(fort, zona)}<h2>Příležitosti (H2H)</h2>{_tab_picks(picks, zona)}<h2>Doplňkové trhy (model)</h2>{_tab_doplnkove(dopl, kalib, zona)}<h2>Nejpravděpodobnější z celé nabídky</h2>{_tab_univ(univ, zona)}<h2>Dosavadní bilance</h2>{_tab_metriky(celkem)}</div></body></html>"

def sestav_index(reporty, celkem, podle_tieru, podle_sportu, doporuceni):
    arch = "".join(f"<li><a href='reports/{_e(r)}.html'>{_e(r)}</a></li>" for r in reporty) or "<li>zatím nic</li>"
    dnes = f"<p><a href='reports/{_e(reporty[0])}.html'><b>🔥 Dnešní report ({_e(reporty[0])})</b></a></p>" if reporty else ""
    return f"<!DOCTYPE html><html lang='cs'><head><meta charset='UTF-8'><meta name='viewport' content='width=device-width, initial-scale=1.0'><title>TIPOVACI_BOT</title><style>{CSS}</style></head><body><div class='c'><h1>🤖 TIPOVACI_BOT</h1>{dnes}<h2>Celkem</h2>{_tab_metriky({'vše': celkem})}<h2>Podle sportu</h2>{_tab_metriky(podle_sportu)}<h2>Archiv</h2><ul>{arch}</ul></div></body></html>"

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

def wa_ranni(datum, picks, vcera, url, zona, max_radku=6, dopl=None, fort=None, log_text="", univ=None, tik=None):
    ikona = {"OK": "✅", "VETO": "⛔"}
    def radek(p): return f"• *{p['zapas']}* ({p['sport']})\n   👉 {_vyber(p)}: sázej od *{p['min_kurz']}* {ikona.get(p.get('veto'), '❔')}" + (f"\n   💱 {p['moje_info']}" if p.get("moje_info") else "") + (f"\n   📝 {p['analyza']['souhrn'][:220]}" if (p.get("analyza") or {}).get("souhrn") else "")
    live = [p for p in picks if p["rezim"] == "live"]
    paper = [p for p in picks if p["rezim"] != "live"]
    t = [f"🤖 *TIPOVACI_BOT | {datum}*"]
    if vcera: t.append(f"📊 Včera: {vcera}")
    if live: t += ["", "💰 *SÁZET:*"] + [radek(p) for p in live[:max_radku]]
    if paper: t += ["", "📝 *SLEDOVAT:*"] + [radek(p) for p in paper[:max_radku]]
    if not picks: t += ["", "Dnes žádná hrana v H2H."] 
    t += _wa_doplnkove(dopl, zona)
    t += _wa_fortuna(fort)
    from . import fortuna_vse
    t += _wa_tikety(tik, zona)
    t += fortuna_vse.text(univ)
    if log_text: t += ["", log_text]
    if url: t += ["", f"📊 Detail: {url}/reports/{datum}.html"]
    return "\n".join(t)

def posli_wa(text):
    inst, token, chat = config.env("WA_INSTANCE_ID"), config.env("WA_API_TOKEN"), config.env("WA_GROUP_ID")
    if not (inst and token and chat): return False
    api = config.env("WA_API_URL", "https://api.green-api.com").rstrip("/")
    url = f"{api}/waInstance{inst}/sendMessage/{token}"
    req = urllib.request.Request(url, data=json.dumps({"chatId": chat, "message": text}).encode("utf-8"), headers={"Content-Type": "application/json"}, method="POST")
    try: urllib.request.urlopen(req, timeout=30); return True
    except Exception: return False
