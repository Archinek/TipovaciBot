"""HTML report (GitHub Pages) + zprávy pro WhatsApp (Green API)."""
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
.c{max-width:980px;margin:0 auto;background:var(--card);padding:22px;border-radius:8px}
h1{font-size:22px;margin:0 0 6px}h2{font-size:18px;margin-top:28px;border-bottom:1px solid var(--line);padding-bottom:4px}
.mut{color:var(--mut);font-size:13px}a{color:var(--acc)}
.w{overflow-x:auto}table{border-collapse:collapse;width:100%;font-size:14px}
th,td{border:1px solid var(--line);padding:7px 9px;text-align:left;vertical-align:top}
th{background:var(--bg)}.box{background:var(--box);border-left:4px solid var(--acc);padding:10px 14px;border-radius:4px;margin:14px 0}
.live{color:var(--ok);font-weight:bold}.paper{color:var(--mut)}.ok{color:var(--ok)}.veto{color:var(--bad)}.nej{color:var(--warn)}
"""


def _e(x):
    return html.escape(str(x), quote=True)


def _vyber(p):
    return "Remíza" if p["vyber"] == "Draw" else p["vyber"]


def _cas(iso, zona):
    return datetime.datetime.fromisoformat(iso).astimezone(ZoneInfo(zona)).strftime("%d.%m. %H:%M")


def _pct(x):
    return "–" if x is None else f"{x * 100:+.1f} %"


def _veto_html(p):
    v = p.get("veto", "")
    cls = {"OK": "ok", "VETO": "veto"}.get(v, "nej")
    txt = {"OK": "✅ OK", "VETO": "⛔ VETO"}.get(v, "❔ " + (v or "NEOVĚŘENO"))
    d = p.get("veto_duvod", "")
    return f"<span class='{cls}'>{_e(txt)}</span>" + (f"<br><span class='mut'>{_e(d)}</span>" if d else "")


def _tab_picks(picks, zona):
    if not picks:
        return "<p>Dnes nic nesplnilo podmínky (a to je v pořádku: žádná hrana = žádná sázka).</p>"
    r = ["<div class='w'><table><tr><th>Zápas</th><th>Výběr</th><th>Fér kurz</th><th>Sázej od</th>"
         "<th>Nejlepší kurz</th><th>Edge</th><th>Stake*</th><th>Režim</th><th>Kontrola</th></tr>"]
    for p in picks:
        rez = ("<span class='live'>SÁZET</span>" if p["rezim"] == "live"
               else "<span class='paper'>sledovat</span>")
        riz = f"<br><span class='nej'>⚠️ {_e(p['riziko'])}</span>" if p["riziko"] else ""
        r.append(
            f"<tr><td>{_e(p['zapas'])}<br><span class='mut'>{_e(p['sport'])} · {_cas(p['start'], zona)}</span></td>"
            f"<td><b>{_e(_vyber(p))}</b></td><td>{p['fair_kurz']}</td><td><b>{p['min_kurz']}</b></td>"
            f"<td>{p['best_kurz']}<br><span class='mut'>{_e(p['best_kniha'])}</span></td>"
            f"<td>{float(p['edge']) * 100:.1f} %{riz}</td><td>{p['stake_pct']} %</td>"
            f"<td>{rez}</td><td>{_veto_html(p)}</td></tr>")
    r.append("</table></div><p class='mut'>*Stake = ¼ Kelly, strop 2 % bankrollu. "
             "Fér kurz = Pinnacle (nebo konsenzus) bez marže. „Sázej od“ = nejnižší kurz, při kterém má sázka "
             "požadovanou hranu: ověř ho u své kanceláře.</p>")
    return "".join(r)


def _tab_metriky(rows_metr):
    if not rows_metr:
        return "<p class='mut'>Zatím žádné vyhodnocené sázky.</p>"
    r = ["<div class='w'><table><tr><th></th><th>N</th><th>Úspěšnost</th><th>Očekáváno (fér p)</th>"
         "<th>ROI paper</th><th>Ø CLV</th><th>Ø posun čáry</th><th>ROI reálně (N)</th></tr>"]
    for k, m in rows_metr.items():
        if not m.get("n"):
            continue
        real = "–" if m["roi_real"] is None else f"{_pct(m['roi_real'])} ({m['n_real']})"
        r.append(f"<tr><td><b>{_e(k)}</b></td><td>{m['n']}</td><td>{m['winrate'] * 100:.1f} %</td>"
                 f"<td>{m['ocekavany_winrate'] * 100:.1f} %</td><td>{_pct(m['roi_paper'])}</td>"
                 f"<td>{_pct(m['avg_clv'])} ({m['n_clv']})</td><td>{_pct(m['avg_posun_cary'])}</td><td>{real}</td></tr>")
    r.append("</table></div><p class='mut'>Pod ~300 sázek je ROI hlavně šum. Hlavní ukazatel je Ø CLV: "
             "kurz, který bot našel, vs. uzavírací fér kurz.</p>")
    return "".join(r)


NAZVY = {"goly": "Góly", "rohy": "Rohy", "karty": "Karty", "fauly": "Fauly"}


def _noha(v, L, s):
    return f"{NAZVY.get(v, v)} {'Over' if s == 'over' else 'Under'} {L}"


def _tab_doplnkove(zapasy, kalib, zona):
    if not zapasy:
        return "<p class='mut'>Dnes žádný zápas v pokrytých ligách nevykazuje výrazný signál.</p>"
    o = []
    for z in zapasy:
        mu = " · ".join(f"{NAZVY[v]} {z['mu'][v]} (Ø {z['liga_prumer'][v]})" for v in z["mu"])
        ref = (f"rozhodčí: {_e(z['rozhodci'])}" if z.get("rozhodci")
               else "rozhodčí neznámý (doplň do data/rozhodci.json)")
        o.append(f"<h3>{_e(z['zapas'])} <span class='mut'>({_cas(z['start'], zona)})</span></h3>"
                 f"<p class='mut'>Model očekává: {_e(mu)} | {ref}</p>")
        if z["linie"]:
            o.append("<div class='w'><table><tr><th>Trh</th><th>P</th><th>Fér kurz</th><th>Sázej od</th></tr>")
            for l in z["linie"]:
                o.append(f"<tr><td>{_e(_noha(l['var'], l['linie'], l['strana']))}</td><td>{l['p'] * 100:.0f} %</td>"
                         f"<td>{l['fair']}</td><td><b>{l['min_kurz']}</b></td></tr>")
            o.append("</table></div>")
        if z["builder"]:
            o.append("<div class='w'><table><tr><th>Builder (2 nohy)</th><th>P</th><th>Fér kurz</th>"
                     "<th>Sázej od</th><th>Korelace</th></tr>")
            for b in z["builder"]:
                txt = " + ".join(_noha(*n) for n in b["nohy"])
                o.append(f"<tr><td>{_e(txt)}</td><td>{b['p'] * 100:.0f} %</td><td>{b['fair']}</td>"
                         f"<td><b>{b['min_kurz']}</b></td><td>×{b['korelace']}</td></tr>")
            o.append("</table></div>")
    kal = ""
    if kalib and kalib.get("n"):
        kal = ("<p class='mut'><b>Kalibrace modelu</b> (N=" + str(kalib["n"]) + f", Brier {kalib['brier']}): " +
               "; ".join(f"{_e(p['pasmo'])}: predikováno {p['predikovano'] * 100:.0f} % → skutečně "
                         f"{p['skutecne'] * 100:.0f} % (n={p['n']})" for p in kalib["pasma"]) + "</p>")
    else:
        kal = "<p class='mut'>Kalibrace zatím nemá data (první výsledky přijdou po odehrání zápasů).</p>"
    o.append("<p class='mut'>Bez kurzu tvé kanceláře: porovnej „Sázej od“ s její nabídkou včetně builderu. "
             "Model je statistický odhad a není ověřený proti trhu; sleduj kalibraci.</p>" + kal)
    return "".join(o)


def sestav_report(datum, picks, vyrazene, vcera, celkem, zona, dopl=None, kalib=None):
    vc = f"<div class='box'><b>Včerejší vyhodnocení:</b> {_e(vcera)}</div>" if vcera else ""
    vyr = ""
    if vyrazene:
        vyr = "<h2>Vyřazeno kontrolou (VETO)</h2><ul>" + "".join(
            f"<li>{_e(p['zapas'])} – {_e(_vyber(p))}: <span class='mut'>{_e(p.get('veto_duvod', ''))}</span></li>"
            for p in vyrazene) + "</ul>"
    kontexty = "".join(
        f"<h3>{_e(p['zapas'])}</h3><p>{_e(p['veto_kontext'])}</p>"
        for p in picks if p.get("veto_kontext"))
    return (
        "<!DOCTYPE html><html lang='cs'><head><meta charset='UTF-8'>"
        "<meta name='viewport' content='width=device-width, initial-scale=1.0'>"
        f"<title>TIPOVACI_BOT {datum}</title><style>{CSS}</style></head><body><div class='c'>"
        "<a href='../index.html'>⬅ Archiv a statistiky</a>"
        f"<h1>Ranní report {datum}</h1>"
        "<p class='mut'>Tipy vychází z kurzové analýzy (cena vs. Pinnacle), ne z predikce LLM. "
        "Gemini jen kontroluje rizika (zranění, sestavy). Žádná sázka není zaručená výhra.</p>"
        f"{vc}<h2>Dnešní příležitosti</h2>{_tab_picks(picks, zona)}"
        f"{('<h2>Ověřený kontext</h2>' + kontexty) if kontexty else ''}{vyr}"
        f"<h2>Doplňkové trhy (fotbal: góly, rohy, karty, fauly, buildery)</h2>{_tab_doplnkove(dopl, kalib, zona)}"
        f"<h2>Dosavadní bilance</h2>{_tab_metriky(celkem)}</div></body></html>")


def sestav_index(reporty, celkem, podle_tieru, podle_sportu, doporuceni):
    arch = "".join(f"<li><a href='reports/{_e(r)}.html'>{_e(r)}</a></li>" for r in reporty) or "<li>zatím nic</li>"
    dnes = ""
    if reporty:
        dnes = f"<p><a href='reports/{_e(reporty[0])}.html'><b>🔥 Nejnovější report ({_e(reporty[0])})</b></a></p>"
    dop = ""
    if doporuceni:
        dop = ("<div class='box'><b>Doporučení režimů (podle CLV):</b><ul>" + "".join(
            f"<li>{_e(s)}: <b>{_e(r)}</b></li>" for s, r in doporuceni.items()) + "</ul></div>")
    return (
        "<!DOCTYPE html><html lang='cs'><head><meta charset='UTF-8'>"
        "<meta name='viewport' content='width=device-width, initial-scale=1.0'>"
        f"<title>TIPOVACI_BOT</title><style>{CSS}</style></head><body><div class='c'>"
        "<h1>🤖 TIPOVACI_BOT</h1>" + dnes +
        f"<h2>Celkem</h2>{_tab_metriky({'vše': celkem})}"
        f"<h2>Podle tieru</h2>{_tab_metriky(podle_tieru)}"
        f"<h2>Podle sportu</h2>{_tab_metriky(podle_sportu)}{dop}"
        f"<h2>Archiv</h2><ul>{arch}</ul></div></body></html>")


# ------------------------------------------------------------------ WhatsApp
def _wa_doplnkove(zapasy, zona, max_zapasu=3):
    r = ["", "🧩 *DOPLŇKOVÉ TRHY* (model; ověř „od kurzu“ u své kanceláře):"]
    for z in (zapasy or [])[:max_zapasu]:
        r.append(f"• *{z['zapas']}* ({_cas(z['start'], zona)})")
        for l in sorted(z["linie"], key=lambda x: -x["p"])[:2]:
            r.append(f"   {_noha(l['var'], l['linie'], l['strana'])} → od *{l['min_kurz']}* "
                     f"(fér {l['fair']}, p {l['p'] * 100:.0f} %)")
        if z["builder"]:
            b = z["builder"][0]
            r.append("   Builder: " + " + ".join(_noha(*n) for n in b["nohy"])
                     + f" → od *{b['min_kurz']}* (fér {b['fair']}, korelace ×{b['korelace']})")
    return r if len(r) > 2 else []


def wa_ranni(datum, picks, vcera, url, zona, max_radku=6, dopl=None):
    ikona = {"OK": "✅", "VETO": "⛔"}
    def radek(p):
        return (f"• *{p['zapas']}* ({p['sport']}, {_cas(p['start'], zona)})\n"
                f"   👉 {_vyber(p)}: sázej od *{p['min_kurz']}* (fér {p['fair_kurz']}, "
                f"edge {float(p['edge']) * 100:.1f} %) {ikona.get(p.get('veto'), '❔')}"
                + (" ⚠️" if p["riziko"] else ""))
    live = [p for p in picks if p["rezim"] == "live"]
    paper = [p for p in picks if p["rezim"] != "live"]
    t = [f"🤖 *TIPOVACI_BOT | {datum}*"]
    if vcera:
        t.append(f"📊 Včera: {vcera}")
    if live:
        t += ["", "💰 *SÁZET (od uvedeného kurzu):*"] + [radek(p) for p in live[:max_radku]]
    if paper:
        t += ["", "📝 *SLEDOVAT (paper, nesázet):*"] + [radek(p) for p in paper[:max_radku]]
    if not picks:
        t += ["", "Dnes žádná hrana u výsledků zápasů, nesázíme. 🙂"]
    t += _wa_doplnkove(dopl, zona)
    if url:
        t += ["", f"📊 Detail a bilance: {url}/reports/{datum}.html"]
    return "\n".join(t)


def posli_wa(text):
    inst, token, chat = config.env("WA_INSTANCE_ID"), config.env("WA_API_TOKEN"), config.env("WA_GROUP_ID")
    if not (inst and token and chat):
        print("ℹ️ WhatsApp není nastaven (WA_INSTANCE_ID / WA_API_TOKEN / WA_GROUP_ID), přeskakuji.")
        return False
    api = config.env("WA_API_URL", "https://api.green-api.com").rstrip("/")
    url = f"{api}/waInstance{inst}/sendMessage/{token}"
    req = urllib.request.Request(
        url, data=json.dumps({"chatId": chat, "message": text}).encode("utf-8"),
        headers={"Content-Type": "application/json"}, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=30):
            print("✅ WhatsApp zpráva odeslána.")
            return True
    except Exception as e:
        print(f"❌ WhatsApp selhal: {type(e).__name__}")   # URL obsahuje token, nevypisujeme ji
        return False
