"""Horní část reportu: statický řádek, koláč do další úpravy modelu, úspěšnost podle období a sportů, a včerejší vyhodnocení po kategoriích."""
import datetime
import html

CSS = """
.strip{display:flex;flex-wrap:wrap;gap:8px 22px;align-items:center;background:var(--card);border:1px solid var(--line);border-radius:12px;padding:10px 16px;font-size:14px;margin:12px 0}
.strip .s{color:var(--mut);font-size:12px;display:block}.strip b{font-size:16px}.sep{width:1px;height:30px;background:var(--line)}
.roi{display:flex;gap:14px}
.tabs{display:inline-flex;background:var(--card);border:1px solid var(--line);border-radius:999px;padding:3px;margin:4px 0 12px}
.tabs button{all:unset;cursor:pointer;padding:6px 16px;border-radius:999px;font-size:13px;color:var(--mut)}.tabs button.on{background:var(--acc);color:#06121f;font-weight:700}
.grid{display:grid;grid-template-columns:minmax(260px,1fr) 1.6fr;gap:14px}@media(max-width:760px){.grid{grid-template-columns:1fr}}
.card{background:var(--card);border:1px solid var(--line);border-radius:12px;padding:16px 18px}.card h4{font-size:14px;margin:0 0 10px;color:var(--mut);font-weight:600;text-transform:uppercase;letter-spacing:.5px}
.donut{width:170px;height:170px;display:block;margin:4px auto}.dn{font-size:28px;font-weight:700;fill:var(--txt)}.ds{font-size:9px;fill:var(--mut)}
.legend{font-size:13px;margin-top:8px}.legend div{display:flex;justify-content:space-between;gap:10px;padding:3px 0;border-bottom:1px solid var(--line)}.legend div:last-child{border:0}
.big{font-size:40px;font-weight:800;line-height:1}.big small{font-size:14px;font-weight:500;color:var(--mut)}
.kp{display:flex;gap:22px;flex-wrap:wrap;margin:8px 0 14px}.kp div span{display:block;color:var(--mut);font-size:12px}.kp div b{font-size:20px}
.sr{padding:8px 0;border-bottom:1px solid var(--line)}.sr:last-child{border:0}.sn{font-weight:600}.sv{font-size:13px;margin-top:3px}
.bar2{position:relative;height:10px;background:var(--line);border-radius:5px;margin-top:5px}.bar2 i{display:block;height:100%;background:var(--acc);border-radius:5px}.bar2 b{position:absolute;top:-3px;width:2px;height:16px;background:var(--warn)}
.pos{color:var(--ok)}.neg{color:var(--bad)}
.js .per{display:none}.js .per.on{display:block}
.cat{display:flex;flex-wrap:wrap;gap:6px 14px;align-items:baseline;margin:22px 0 6px}.cat h3{font-size:16px;margin:0}
.chip{font-size:12px;padding:2px 10px;border-radius:999px;border:1px solid var(--line);background:var(--card);color:var(--mut)}.chip b{color:var(--txt)}
.v{display:inline-block;padding:3px 10px;border-radius:999px;font-weight:700;font-size:12.5px;white-space:nowrap}
.vw{background:#12301f;color:var(--ok);border:1px solid #1f5a36}.vl{background:#341616;color:var(--bad);border:1px solid #5e2626}.vv{background:#2a2a2a;color:var(--mut);border:1px solid #444}.vp{background:#14233a;color:var(--acc);border:1px solid #28466f}
td .m{color:var(--acc);font-weight:600}td .sp{color:var(--mut);font-size:12px}
tr.klik{cursor:pointer}tr.klik td:first-child{border-left:3px solid var(--acc)}tr.roz{display:none}tr.roz.on{display:table-row}tr.roz td{background:#10161d;padding:4px 18px 14px;white-space:normal}
.kdy{white-space:nowrap;font-weight:600}.sipka{color:var(--acc);font-size:12px}
"""

SCRIPT = """<script>
document.documentElement.classList.add('js');
document.querySelectorAll('.tabs button').forEach(function(b){b.onclick=function(){
 document.querySelectorAll('.tabs button').forEach(function(x){x.classList.toggle('on',x===b)});
 document.querySelectorAll('.per').forEach(function(p){p.classList.toggle('on',p.dataset.k===b.dataset.k)});
 document.querySelectorAll('.roi div[data-k]').forEach(function(p){p.style.opacity=p.dataset.k===b.dataset.k?1:.55});};});
document.querySelectorAll('tr.klik').forEach(function(r){r.onclick=function(e){if(e.target.tagName==='A')return;var n=r.nextElementSibling;n.classList.toggle('on');
 var s=r.querySelector('.sipka');if(s)s.textContent=n.classList.contains('on')?'▲ skrýt rozbor':'▼ rozbor';};});
</script>"""

NAZVY = {"vcera": "Včera", "7": "7 dní", "30": "30 dní", "vse": "Celkem"}


def _e(x):
    return html.escape(str(x), quote=True)


def _pct(x, d=0):
    return f"{x * 100:.{d}f}".replace(".", ",") + " %"


def _sg(x, d=1):
    return f"{x * 100:+.{d}f}".replace(".", ",") + " %"


def _tr(x):
    return "pos" if x >= 0 else "neg"


def _datum_cz(iso):
    d = datetime.date.fromisoformat(iso)
    return f"{d.day}. {d.month}. {d.year}"


def _koláč(m):
    p = m["podil"]
    c = 2 * 3.14159265 * 40
    if m["druh"] == "celkem":
        radky = [("Stav", f"{m['stav']} / {m['cil']} vyhodnocených"), ("Odhad dosažení", m["eta"] or ("splněno" if p >= 1 else "bez dat"))]
    else:
        nej = sorted(((v["n"], sp, v["eta"]) for sp, v in m["sporty"].items() if v["n"] < m["cil"]), reverse=True)[:1]
        radky = [("Nejdál", f"{nej[0][1]} {nej[0][0]} / {m['cil']}" if nej else f"{m['stav']} / {m['cil']}"), ("Odhad dosažení", (nej[0][2] if nej and nej[0][2] else "bez dat"))]
    radky.append(("Co to odemkne", m["co"]))
    svg = (f"<svg class='donut' viewBox='0 0 100 100'><circle cx='50' cy='50' r='40' fill='none' stroke='#2a3441' stroke-width='11'/>"
           f"<circle cx='50' cy='50' r='40' fill='none' stroke='#5aa9ff' stroke-width='11' stroke-dasharray='{c * p:.1f} {c:.1f}' stroke-linecap='round' transform='rotate(-90 50 50)'/>"
           f"<text x='50' y='52' text-anchor='middle' class='dn'>{p * 100:.0f} %</text><text x='50' y='64' text-anchor='middle' class='ds'>do úpravy modelu</text></svg>")
    return svg + "<div class='legend'>" + "".join(f"<div><span>{_e(a)}</span><b>{_e(b)}</b></div>" for a, b in radky) + "</div>"


def _panel(k, o, aktivni):
    s, sp = o["stat"], o["sporty"]
    on = " on" if aktivni else ""
    if not s.get("n"):
        return f"<div class='per{on}' data-k='{k}'><div class='card'><h4>Úspěšnost na celé nabídce · {NAZVY[k].lower()}</h4><p class='mut'>V tomto období zatím nic vyhodnoceno.</p></div></div>"
    rozdil = (s["uspesnost"] - s["cekano"]) * 100
    bars = ""
    for nazev, v in sorted(sp.items(), key=lambda x: -x[1]["n"]):
        bars += (f"<div class='sr'><div class='sn'>{_e(nazev.capitalize())} <span class='mut'>· {v['n']} sázek</span></div>"
                 f"<div class='bar2'><i style='width:{v['uspesnost'] * 100:.0f}%'></i><b style='left:{v['cekano'] * 100:.0f}%'></b></div>"
                 f"<div class='sv'><b>{_pct(v['uspesnost'])}</b> čekáno {_pct(v['cekano'])} <span class='{_tr(v['uspesnost'] - v['cekano'])}'>{(v['uspesnost'] - v['cekano']) * 100:+.1f} b.</span> "
                 f"ROI <span class='{_tr(v['roi'])}'>{_sg(v['roi'])}</span></div></div>")
    return (f"<div class='per{on}' data-k='{k}'><div class='card'><h4>Úspěšnost na celé nabídce · {NAZVY[k].lower()}</h4>"
            f"<div class='big'>{_pct(s['uspesnost'], 1)} <small>čekáno {_pct(s['cekano'], 1)} · rozdíl {rozdil:+.1f} b.</small></div>"
            f"<div class='kp'><div><span>Vyšlo</span><b>{s['vyslo']} z {s['n']}</b></div><div><span>ROI (flat)</span><b class='{_tr(s['roi'])}'>{_sg(s['roi'])}</b></div><div><span>Sportů</span><b>{len(sp)}</b></div></div>"
            f"<h4>Rozpad podle sportů</h4><div class='mut' style='margin:-4px 0 6px'>Modrá = skutečná úspěšnost, žlutá čárka = čekaná z trhu</div>{bars}</div></div>")


def horni(u):
    if not u:
        return ""
    ob = u["obdobi"]
    cel = ob["vse"]["stat"]
    roi = "".join(f"<div data-k='{k}' style='opacity:{1 if k == '7' else .55}'><span class='s'>{NAZVY[k].lower() if k != 'vse' else 'celkem'}</span>"
                  f"<b class='{_tr(ob[k]['stat']['roi']) if ob[k]['stat'].get('n') else ''}'>{_sg(ob[k]['stat']['roi']) if ob[k]['stat'].get('n') else '–'}</b></div>" for k in ("vcera", "7", "30", "vse"))
    m = u["dalsi_meta"]
    meta = f"{m['cil']} " + ("celkem" if m["druh"] == "celkem" else "u sportu")
    strip = (f"<div class='strip'><div><span class='s'>Zapsáno</span><b>{u['zapsano']}</b></div><div><span class='s'>Vyhodnoceno</span><b>{u['vyhodnoceno']}</b></div>"
             f"<div><span class='s'>Úspěšnost (celkem)</span><b>{_pct(cel['uspesnost'], 1) if cel.get('n') else '–'}</b></div><div class='sep'></div>"
             f"<div><span class='s'>ROI podle období</span><div class='roi'>{roi}</div></div><div class='sep'></div><div><span class='s'>Další meta</span><b>{_e(meta)}</b></div></div>")
    tabs = "<div class='tabs'>" + "".join(f"<button data-k='{k}'{' class=on' if k == '7' else ''}>{NAZVY[k]}</button>" for k in ("vcera", "7", "30", "vse")) + "</div>"
    panely = "".join(_panel(k, ob[k], k == "7") for k in ("vcera", "7", "30", "vse"))
    return (f"{strip}{tabs}<div class='grid'><div class='card'><h4>Kolik zbývá do další úpravy modelu</h4>{_koláč(m)}</div><div>{panely}</div></div>")


def _vysl(r, duvod=""):
    if r == "1":
        t, c = "✔ VÝHRA", "vw"
    elif r == "0":
        t, c = "✖ PROHRA", "vl"
    elif r == "V":
        return "<span class='v vv'>↺ ZRUŠENO (kurz 1.00)</span>"
    else:
        return "<span class='v vp'>⏳ čeká na výsledek</span>"
    d = (duvod or "").strip()
    if d and len(d) <= 22 and any(ch.isdigit() for ch in d):
        t += f" ({_e(d)})"
    return f"<span class='v {c}'>{t}</span>"


def _chips(s):
    if not s["n"]:
        return f"<span class='chip'>zatím <b>nevyhodnoceno</b> ({s['celkem']})</span>"
    return (f"<span class='chip'><b>{s['vyslo']}</b> z <b>{s['n']}</b> vyšlo</span><span class='chip'>úspěšnost <b>{_pct(s['uspesnost'])}</b></span>"
            f"<span class='chip'>ROI <b class='{_tr(s['roi'])}'>{_sg(s['roi'])}</b></span>")


def vcera(u):
    vk = (u or {}).get("vcera_kat") or {}
    if not vk.get("kategorie") and not vk.get("tikety"):
        return "<h2 id='vcera'>🗓️ Včerejší vyhodnocení</h2><p class='mut'>Včera bot nezapsal žádné sázky k vyhodnocení.</p>"
    o = [f"<h2 id='vcera'>🗓️ Včerejší vyhodnocení ({_datum_cz(vk['datum'])})</h2><p class='mut'>Co bot včera poslal a jak to dopadlo. Výsledky bere z API Fortuny; co se zatím nenašlo, je označené jako čekající.</p>"]
    for k in vk["kategorie"]:
        o.append(f"<div class='cat'><h3>{k['ikona']} {_e(k['nazev'])}</h3>{_chips(k['souhrn'])}</div>")
        o.append("<div class='w'><table><tr><th>Příležitost (zápas a tip)</th><th>Kurz Fortuna</th><th>Sázej od</th><th>Důvěra</th><th>Pravděpodobnost</th><th>Výsledek</th></tr>")
        for r in k["radky"]:
            tip = _e(r["trh"]) + (f": <b>{_e(r['vyber'])}</b>" if r["vyber"] else "")
            sz = f"<b>{_e(r['sazej_od'])}+</b>" if r["sazej_od"] else "–"
            dv = f"{_e(r['duvera'])}/10" if r["duvera"] else "–"
            o.append(f"<tr><td><span class='m'>{_e(r['zapas'])}</span> <span class='sp'>({_e(r['sport'])})</span><br>{tip}</td><td>{r['kurz']:.2f}</td><td>{sz}</td><td>{dv}</td>"
                     f"<td>{r['p'] * 100:.0f} %</td><td>{_vysl(r['vysledek'], r['duvod'])}</td></tr>")
        o.append("</table></div>")
    if vk["tikety"]:
        hl = [t for t in vk["tikety"] if not t["klic"].endswith("_alt")]
        vyh = sum(1 for t in hl if t["vysledek"] == "1")
        chips = f"<span class='chip'>hlavní tikety: <b>{vyh}</b> z <b>{sum(1 for t in hl if t['vysledek'] in ('0', '1'))}</b> vyšly</span>"
        pyr = [t for t in hl if t["klic"].startswith("pyr")]
        if pyr:
            chips += "<span class='chip'>Pyramida: " + " · ".join(f"kolo {t['klic'][3:]} {'✔' if t['vysledek'] == '1' else '✖' if t['vysledek'] == '0' else '⏳'}" for t in pyr) + "</span>"
        o.append(f"<div class='cat'><h3>🎟️ 5) Denní tiket a 🔺 Pyramida</h3>{chips}</div>")
        o.append("<div class='w'><table><tr><th>Tiket</th><th>Nohy</th><th>Kurz celkem</th><th>Pravděpodobnost</th><th>Výsledek</th></tr>")
        for t in vk["tikety"]:
            noze = " · ".join(f"{_e(x['zapas'][:34])}: {_e(x['vyber'] or x['trh'])[:40]} {'✔' if x['vysledek'] == '1' else '✖' if x['vysledek'] == '0' else '↺' if x['vysledek'] == 'V' else '⏳'}" for x in t["noze"])
            kurz = f"{t['kurz']:.2f}" if t.get("kurz") else "–"
            p = f"{t['p'] * 100:.0f} %" if t.get("p") else "–"
            ok = sum(1 for x in t["noze"] if x["vysledek"] == "1")
            pocet = "%d z %d" % (ok, len(t["noze"]))
            o.append(f"<tr><td><b>{_e(t['nazev'])}</b></td><td>{noze}</td><td>{kurz}</td><td>{p}</td><td>{_vysl(t['vysledek'], pocet)}</td></tr>")
        o.append("</table></div>")
    return "".join(o)
