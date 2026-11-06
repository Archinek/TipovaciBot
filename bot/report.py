import datetime
import html
import json
import urllib.request
from zoneinfo import ZoneInfo
from . import config

CSS = """
:root{--bg:#f4f4f4;--card:#fff;--txt:#222;--mut:#666;--line:#ddd;--acc:#0a66c2;--ok:#1a7f37;--bad:#cf222e;--warn:#9a6700;--box:#eef6ff}
@media (prefers-color-scheme:dark){:root{--bg:#121417;--card:#1c1f24;--txt:#e6e6e6;--mut:#9aa0a6;--line:#333;--acc:#58a6ff;--ok:#3fb950;--bad:#f85149;--warn:#d29922;--box:#16222f}}
body{font-family:Arial,sans-serif;margin:0;padding:16px;background:var(--bg);color:var(--txt)}
.c{max-width:1080px;margin:0 auto;background:var(--card);padding:22px;border-radius:8px}
h1{font-size:22px;margin:0 0 6px}h2{font-size:18px;margin-top:28px;border-bottom:1px solid var(--line);padding-bottom:4px}
.mut{color:var(--mut);font-size:13px}a{color:var(--acc)}
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

def _tab_fortuna(fort, zona):
    if not fort: return "<p class='mut'>Dnes v nabídce Fortuny žádná linie, kde by model a trh dávaly dostatečnou hranu.</p>"
    z = {}
    for f in fort: z.setdefault(f["zapas"], []).append(f)
    r = []
    for zapas, pl in z.items():
        f0 = pl[0]
        koment = {k.get("trh"): k.get("komentar", "") for k in (f0.get("analyza") or {}).get("komentare_k_trhum", [])}
        r.append(f"<h3>{_e(zapas)} <span class='mut'>({_e(f0['liga'])}, {_cas(f0['start'], zona)})</span></h3>")
        r.append("<div class='w'><table><tr><th>Trh</th><th>Kurz Fortuna</th><th>Sázej od</th><th>P model / trh / mix</th><th>Hrana</th></tr>")
        for f in pl:
            r.append(f"<tr><td>{_e(f['trh'])}</td><td>{f['kurz_fortuna']}</td><td><b>{f['sazej_od']}</b></td><td>{f['p_model'] * 100:.0f} / {f['p_trh'] * 100:.0f} / <b>{f['p'] * 100:.0f} %</b></td><td>{f['edge'] * 100:+.1f} %</td></tr>")
            if koment.get(f["trh"]): r.append(f"<tr><td colspan='5' class='mut'>{_e(koment[f['trh']])}</td></tr>")
        r.append("</table></div>")
        r.append(_analyza_html(f0.get("analyza")))
    r.append("<p class='mut'>Kurz Fortuny je jen orientační ceník (sázíš jinde): vyplatí se od hodnoty „Sázej od“. P mix = půl model, půl férový trh. Analýza vychází z dat bota a z vyhledávání Gemini; co nebylo dohledáno, je tak označeno.</p>")
    return "".join(r)

def _tab_tipdne(fort, zona):
    tip = sorted((f for f in (fort or []) if f.get("tip_dne")), key=lambda f: f["tip_dne"])
    if not tip: return "<p class='mut'>Dnes žádný kandidát nepřekročil práh. Je to normální: nutit sázku, když hrana není, je přesně chyba, kterou TOP tipéři nedělají.</p>"
    r = ["<div class='w'><table><tr><th>#</th><th>Zápas</th><th>Trh</th><th>Kurz Fortuna</th><th>Sázej od</th><th>P mix</th><th>Hrana</th><th>Analýza</th></tr>"]
    for f in tip:
        an = f.get("analyza") or {}
        r.append(f"<tr><td>{f['tip_dne']}</td><td>{_e(f['zapas'])}<br><span class='mut'>{_e(f['liga'])}, {_cas(f['start'], zona)}</span></td><td>{_e(f['trh'])}<br><span class='mut'>{_e(f.get('rodina', ''))}</span></td><td>{f['kurz_fortuna']}</td><td><b>{f['sazej_od']}</b></td><td>{f['p'] * 100:.0f} %</td><td>{f['edge'] * 100:+.1f} %</td><td>{IK.get(an.get('verdikt'), '')} {_e((an.get('duvod') or '')[:120])}</td></tr>")
    r.append("</table></div><p class='mut'>Výběr: hrana × důvěra v model (klesá s rozchodem model vs. trh) × váha typu trhu odvozená z profilů TOP tipérů; max. 1 linie na zápas, max. 2 z jednoho typu trhu. Kurz Fortuny je jen orientační ceník.</p>")
    return "".join(r)

def _tab_jistejsi(fort, zona):
    js = sorted((f for f in (fort or []) if f.get("jistejsi")), key=lambda f: f["jistejsi"])
    if not js: return "<p class='mut'>Dnes žádný kandidát s vyšší pravděpodobností a dostatečnou hranou.</p>"
    r = ["<div class='w'><table><tr><th>#</th><th>Zápas</th><th>Trh</th><th>Kurz Fortuna</th><th>Sázej od</th><th>P mix</th><th>Hrana</th><th>Vklad</th></tr>"]
    for f in js:
        r.append(f"<tr><td>{f['jistejsi']}</td><td>{_e(f['zapas'])}<br><span class='mut'>{_e(f['liga'])}, {_cas(f['start'], zona)}</span></td><td>{_e(f['trh'])}</td><td>{f['kurz_fortuna']}</td><td><b>{f['sazej_od']}</b></td><td>{f['p'] * 100:.0f} %</td><td>{f['edge'] * 100:+.1f} %</td><td>~{f.get('vklad_pct', 0)} % banku</td></tr>")
    r.append("</table></div><p class='mut'>Nižší kurz, vyšší úspěšnost: pro stabilní růst banku. Vklad = 1/4 Kelly se stropem 2 % banku.</p>")
    return "".join(r)

def _tab_univ(univ, zona):
    if not univ: return "<p class='mut'>Žádný kandidát.</p>"
    r = "".join(f"<tr><td>{html.escape(str(c['sport']))}</td><td>{html.escape(str(c['zapas']))}</td><td>{html.escape(str(c['trh']))}: <b>{html.escape(str(c['vyber']))}</b></td><td>{c['kurz']}</td><td>{c['p'] * 100:.0f} %</td></tr>" for c in univ)
    return f"<p class='mut'>Bez modelu: p je férová pravděpodobnost trhu bez marže, zisk to nezaručuje (výnos ≈ minus marže).</p><table><tr><th>Sport</th><th>Zápas</th><th>Výběr</th><th>Kurz</th><th>p</th></tr>{r}</table>"


def sestav_report(datum, picks, vyrazene, vcera, celkem, zona, dopl=None, kalib=None, fort=None, univ=None):
    vc = f"<div class='box'><b>Včera:</b> {_e(vcera)}</div>" if vcera else ""
    return f"<!DOCTYPE html><html lang='cs'><head><meta charset='UTF-8'><meta name='viewport' content='width=device-width, initial-scale=1.0'><title>TIPOVACI_BOT</title><style>{CSS}</style></head><body><div class='c'><a href='../index.html'>⬅ Archiv</a><h1>Ranní report {datum}</h1>{vc}<h2>⭐ Tip dne</h2>{_tab_tipdne(fort, zona)}<h2>🛡️ Jistější tipy</h2>{_tab_jistejsi(fort, zona)}<h2>Příležitosti</h2>{_tab_picks(picks, zona)}<h2>Doplňkové trhy (model)</h2>{_tab_doplnkove(dopl, kalib, zona)}<h2>Nabídka Fortuny vs. model</h2>{_tab_fortuna(fort, zona)}<h2>Nejpravděpodobnější z celé nabídky</h2>{_tab_univ(univ, zona)}<h2>Dosavadní bilance</h2>{_tab_metriky(celkem)}</div></body></html>"

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
            r.append(f"{f['tip_dne']}. *{f['zapas']}* {IK.get(an.get('verdikt'), '')}\n   {f['trh']} → od *{f['sazej_od']}* (Fortuna {f['kurz_fortuna']}, p {f['p'] * 100:.0f} %, hrana {f['edge'] * 100:+.1f} %, vklad ~{f.get('vklad_pct', 0)} % banku)")
    js = sorted((f for f in fort if f.get("jistejsi")), key=lambda f: f["jistejsi"])
    if js:
        r += ["", "🛡️ *JISTĚJŠÍ* (vyšší úspěšnost, nižší kurz):"]
        for f in js:
            an = f.get("analyza") or {}
            r.append(f"• *{f['zapas']}* {IK.get(an.get('verdikt'), '')}\n   {f['trh']} → od *{f['sazej_od']}* (Fortuna {f['kurz_fortuna']}, p {f['p'] * 100:.0f} %, vklad ~{f.get('vklad_pct', 0)} % banku)")
    r += ["", "🎯 *NABÍDKA vs. MODEL* (sázej od):"]
    for zapas, pl in list(z.items())[:max_zapasu]:
        an = pl[0].get("analyza") or {}
        r.append(f"• *{zapas}* {IK.get(an.get('verdikt'), '')}")
        for f in pl[:3]:
            r.append(f"   {f['trh']} → od *{f['sazej_od']}* (Fortuna {f['kurz_fortuna']}, hrana {f['edge'] * 100:+.1f} %)")
        if an.get("souhrn"): r.append(f"   _{an['souhrn'][:230]}_")
        if an.get("riziko"): r.append(f"   ⚠️ {an['riziko'][:140]}")
    return r

def wa_ranni(datum, picks, vcera, url, zona, max_radku=6, dopl=None, fort=None, log_text="", univ=None):
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
