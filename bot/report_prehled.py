"""Horní část reportu: statický řádek, koláč do další úpravy modelu, úspěšnost podle období a sportů, a včerejší vyhodnocení po kategoriích."""
import datetime
import html
from .cisla import tis

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
.kolace{display:grid;grid-template-columns:repeat(auto-fit,minmax(190px,1fr));gap:12px}.kol{background:var(--card2);border:1px solid var(--line);border-radius:12px;padding:12px}.kol.akt{border-color:var(--acc);box-shadow:0 0 0 1px var(--acc)}.kn{font-weight:700;font-size:13px;text-align:center}.kol .donut{width:110px;height:110px;margin:6px auto}.kz{display:flex;justify-content:space-between;font-size:12px;margin-top:6px}.kol .bar{margin-top:3px}.kol .mut{margin-top:8px;font-size:11.5px;text-align:center}
.pos{color:var(--ok)}.neg{color:var(--bad)}
.js .per{display:none}.js .per.on{display:block}
.cat{display:flex;flex-wrap:wrap;gap:6px 14px;align-items:baseline;margin:22px 0 6px}.cat h3{font-size:16px;margin:0}
.chip{font-size:12px;padding:2px 10px;border-radius:999px;border:1px solid var(--line);background:var(--card);color:var(--mut)}.chip b{color:var(--txt)}
.v{display:inline-block;padding:3px 10px;border-radius:999px;font-weight:700;font-size:12.5px;white-space:nowrap}
.vw{background:#12301f;color:var(--ok);border:1px solid #1f5a36}.vl{background:#341616;color:var(--bad);border:1px solid #5e2626}.vv{background:#2a2a2a;color:var(--mut);border:1px solid #444}.vp{background:#14233a;color:var(--acc);border:1px solid #28466f}
td .m{color:var(--acc);font-weight:600}td .sp{color:var(--mut);font-size:12px}
tr.skryty,tr.skryty+tr.roz{display:none!important}
.filtr{margin:8px 0;display:flex;flex-wrap:wrap;gap:8px;align-items:center;font-size:13px}.filtr .chip{all:unset;cursor:pointer;padding:5px 14px;border-radius:999px;border:1px solid #2a3441;color:var(--mut)}.filtr .chip.on{background:var(--acc);color:#06121f;font-weight:700;border-color:var(--acc)}.filtr input{background:#10161d;color:inherit;border:1px solid #2a3441;border-radius:6px;padding:3px 6px}
.pyr{display:flex;gap:6px;flex-wrap:wrap;margin:10px 0}.pyr div{min-width:44px;text-align:center;padding:8px 6px;border-radius:8px;border:1px solid #2a3441;color:var(--mut);font-weight:700}
.pyr .ok{background:#16351f;border-color:#34c76b;color:#34c76b}.pyr .cur{background:var(--acc);color:#06121f;border-color:var(--acc)}.pyr small{display:block;font-weight:400;font-size:10px}
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
(function(){var f=document.getElementById('f130');if(!f)return;var rows=document.querySelectorAll('#t130 tr[data-s]'),od=document.getElementById('f130od'),do_=document.getElementById('f130do'),n=document.getElementById('f130n'),den='';
 function ap(){var v=0;rows.forEach(function(r){var d=r.dataset.s.slice(0,10),t=r.dataset.s.slice(11,16),ok=(!den||d===den)&&t>=(od.value||'00:00')&&t<=(do_.value||'23:59');r.classList.toggle('skryty',!ok);if(ok)v++});n.textContent='Zobrazeno '+v+' z '+rows.length;}
 f.querySelectorAll('.chip').forEach(function(b){b.onclick=function(){den=b.dataset.d;f.querySelectorAll('.chip').forEach(function(x){x.classList.toggle('on',x===b)});ap()}});
 od.oninput=ap;do_.oninput=ap;ap()})();
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


def _kol(m, nazev, aktualni):
    p = m["podil"]
    c = 2 * 3.14159265 * 40
    barva = "#34c76b" if p >= 1 else "#5aa9ff"
    svg = (f"<svg class='donut' viewBox='0 0 100 100'><circle cx='50' cy='50' r='40' fill='none' stroke='#2a3441' stroke-width='11'/>"
           f"<circle cx='50' cy='50' r='40' fill='none' stroke='{barva}' stroke-width='11' stroke-dasharray='{c * p:.1f} {c:.1f}' stroke-linecap='round' transform='rotate(-90 50 50)'/>"
           f"<text x='50' y='57' text-anchor='middle' class='dn'>{p * 100:.0f} %</text></svg>")
    pz, pd = min(1.0, m["stav"] / m["cil"]), min(1.0, m["dny"] / m["min_dny"])
    eta = "splněno" if p >= 1 else (m["eta"] or "bez dat")
    return (f"<div class='kol{' akt' if aktualni else ''}'><div class='kn'>{_e(nazev)}</div>{svg}"
            f"<div class='kz'>Zápasů <b>{tis(m['stav'])} / {tis(m['cil'])}</b></div><div class='bar'><i style='width:{pz * 100:.0f}%'></i></div>"
            f"<div class='kz'>Dnů dat <b>{m['dny']} / {m['min_dny']}</b></div><div class='bar'><i style='width:{pd * 100:.0f}%'></i></div>"
            f"<div class='kz'>Odhad: <b>{_e(eta)}</b></div><div class='mut'>{_e(m['co'])}</div></div>")


NAZVY_META = ["Meta 1 · ověření", "Meta 2 · první kalibrace", "Meta 3 · úprava modelu", "Meta 4 · ladění prahů"]


def _kolace(mety, dalsi):
    h = "".join(_kol(m, NAZVY_META[i] if i < len(NAZVY_META) else f"Meta {i + 1}", m["cil"] == dalsi["cil"] and dalsi["podil"] < 1) for i, m in enumerate(mety))
    return f"<div class='card'><h4>Postup k další úpravě modelu</h4><div class='kolace'>{h}</div></div>"


def _panel(k, o, aktivni):
    s, sp = o["stat"], o["sporty"]
    on = " on" if aktivni else ""
    if not s.get("n"):
        return f"<div class='per{on}' data-k='{k}'><div class='card'><h4>Úspěšnost na celé nabídce · {NAZVY[k].lower()}</h4><p class='mut'>V tomto období zatím nic vyhodnoceno.</p></div></div>"
    rozdil = (s["uspesnost"] - s["cekano"]) * 100
    bars = ""
    for nazev, v in sorted(sp.items(), key=lambda x: -x[1]["n"]):
        bars += (f"<div class='sr'><div class='sn'>{_e(nazev.capitalize())} <span class='mut'>· {tis(v['n'])} sázek</span></div>"
                 f"<div class='bar2'><i style='width:{v['uspesnost'] * 100:.0f}%'></i><b style='left:{v['cekano'] * 100:.0f}%'></b></div>"
                 f"<div class='sv'><b>{_pct(v['uspesnost'])}</b> čekáno {_pct(v['cekano'])} <span class='{_tr(v['uspesnost'] - v['cekano'])}'>{(v['uspesnost'] - v['cekano']) * 100:+.1f} b.</span> "
                 f"ROI <span class='{_tr(v['roi'])}'>{_sg(v['roi'])}</span></div></div>")
    return (f"<div class='per{on}' data-k='{k}'><div class='card'><h4>Úspěšnost na celé nabídce · {NAZVY[k].lower()}</h4>"
            f"<div class='big'>{_pct(s['uspesnost'], 1)} <small>čekáno {_pct(s['cekano'], 1)} · rozdíl {rozdil:+.1f} b.</small></div>"
            f"<div class='kp'><div><span>Vyšlo</span><b>{tis(s['vyslo'])} z {tis(s['n'])}</b></div><div><span>ROI (flat)</span><b class='{_tr(s['roi'])}'>{_sg(s['roi'])}</b></div><div><span>Sportů</span><b>{len(sp)}</b></div></div>"
            f"<h4>Rozpad podle sportů</h4><div class='mut' style='margin:-4px 0 6px'>Modrá = skutečná úspěšnost, žlutá čárka = čekaná z trhu</div>{bars}</div></div>")


def horni(u):
    if not u:
        return ""
    ob = u["obdobi"]
    cel = ob["vse"]["stat"]
    roi = "".join(f"<div data-k='{k}' style='opacity:{1 if k == '7' else .55}'><span class='s'>{NAZVY[k].lower() if k != 'vse' else 'celkem'}</span>"
                  f"<b class='{_tr(ob[k]['stat']['roi']) if ob[k]['stat'].get('n') else ''}'>{_sg(ob[k]['stat']['roi']) if ob[k]['stat'].get('n') else '–'}</b></div>" for k in ("vcera", "7", "30", "vse"))
    m = u["dalsi_meta"]
    meta = f"{tis(m['cil'])} zápasů a {m['min_dny']} dní"
    strip = (f"<div class='strip'><div><span class='s'>Zapsáno</span><b>{tis(u['zapsano'])}</b></div><div><span class='s'>Vyhodnoceno</span><b>{tis(u['vyhodnoceno'])}</b></div><div><span class='s'>Pyramida</span><b>{('kolo ' + str(u['pyramida']['aktualni']['kolo']) + ' z 10') if u.get('pyramida') and u['pyramida'].get('dnu') else '–'}</b></div>"
             f"<div><span class='s'>Úspěšnost (celkem)</span><b>{_pct(cel['uspesnost'], 1) if cel.get('n') else '–'}</b></div><div class='sep'></div>"
             f"<div><span class='s'>ROI podle období</span><div class='roi'>{roi}</div></div><div class='sep'></div><div><span class='s'>Další meta</span><b>{_e(meta)}</b></div></div>")
    tabs = "<div class='tabs'>" + "".join(f"<button data-k='{k}'{' class=on' if k == '7' else ''}>{NAZVY[k]}</button>" for k in ("vcera", "7", "30", "vse")) + "</div>"
    panely = "".join(_panel(k, ob[k], k == "7") for k in ("vcera", "7", "30", "vse"))
    return (f"{strip}{_kolace(u['mety'], m)}{tabs}<div>{panely}</div>")


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
        return f"<span class='chip'>zatím <b>nevyhodnoceno</b> ({tis(s['celkem'])})</span>"
    return (f"<span class='chip'><b>{tis(s['vyslo'])}</b> z <b>{tis(s['n'])}</b> vyšlo</span><span class='chip'>úspěšnost <b>{_pct(s['uspesnost'])}</b></span>"
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


def pyramida_postup(u):
    """Postup bota v Pyramidě (pravidla Tipsportu): 10 kol, aktivní Pyramidy, historie her, úspěšnost po kolech."""
    p = (u or {}).get("pyramida")
    if not p or not p.get("dnu"):
        return "<p class='mut'>Zatím nejsou žádná data o tiketech Pyramidy.</p>"
    bloky = []
    for n, a in enumerate(p["aktivni"], start=1):
        kolo = a["kolo"]
        boxy = "".join(f"<div class='{'ok' if k < kolo else 'cur' if k == kolo else ''}'>{k}<small>{'✔' if k < kolo else 'teď' if k == kolo else ''}</small></div>" for k in range(1, 11))
        info = ""
        if a.get("uvizl"):
            info = f" ⚠ Tiket kola {kolo} z {_datum_cz(a['ceka_od'])} se nepodařilo vyhodnotit (některý zápas bez výsledku), hra proto stojí."
        elif a.get("ceka"):
            info = " Tiket aktuálního kola ještě není vyhodnocený."
        zivot = "život ještě je" if a["zivot"] else "život už spotřebován (zrušená noha)"
        zb = f", do konce limitu zbývá {a['zbyva_dni']} z 42 dní" if a.get("zbyva_dni") is not None else ""
        od = f" od {_datum_cz(a['od'])}" if a.get("od") else " (ještě nezačala)"
        bloky.append(f"<div class='pyr'>{boxy}</div><p><b>Pyramida {n}:</b> kolo <b>{kolo} z 10</b>{od}, série {a['serie']} výher, {zivot}{zb}.{info}</p>")
    head = f"<p>Nejdál bot došel do <b>{p['nejlepsi']}. kola</b>, vyhraných Pyramid (10 kol): <b>{p['vyhrano']}</b>.</p>"
    behy = ""
    if p["behy"]:
        behy = ("<div class='w'><table><tr><th>Ukončená hra</th><th>Dosažené kolo</th><th>Konec</th></tr>" + "".join(
            f"<tr><td>{_datum_cz(b['od'])} až {_datum_cz(b['do'])}</td><td><b>{b['dosazeno']}</b> z 10</td><td>{'🏆 vyhráno' if b['stav'] == 'vyhráno' else b['stav'] + ' v ' + str(b['padl_na']) + '. kole'}</td></tr>" for b in p["behy"]) + "</table></div>")
    r = ["<div class='w'><table><tr><th>Kolo</th><th>Min. kurz</th><th>Cena za kolo</th><th>Vyhodnoceno</th><th>Vyšlo</th><th>Úspěšnost</th><th>Čekáno (model/trh)</th><th>Šance dojít až sem*</th></tr>"]
    for k, sa in zip(p["kola"], p["sance"]):
        us = _pct(k["uspesnost"]) if k["uspesnost"] is not None else "–"
        ce = _pct(k["cekano"]) if k["cekano"] is not None else "–"
        r.append(f"<tr><td><b>{k['kolo']}</b></td><td>{(format(k['prah'], '.2f') if k['prah'] else '–')}</td><td>{_e(k.get('cena') or '–')}</td><td>{tis(k['n'])}</td><td>{tis(k['vyhry'])}</td><td>{us}</td><td>{ce}</td><td>{_pct(sa, 1)}</td></tr>")
    r.append("</table></div>")
    return (f"<div class='card'><h4>Postup bota v Pyramidě</h4>{''.join(bloky)}{head}{behy}</div>"
            "<details open><summary><b>Úspěšnost po kolech</b></summary>" + "".join(r) + "</details>"
            "<p class='mut'>* Součin čekaných pravděpodobností kol 1 až N podle modelu a trhu (ne zaručená šance). "
            "Pravidla Tipsportu: 10 kol s min. kurzem 1,1 až 10, prohra Pyramidu ukončí (jeden život jen při zrušené příležitosti), nejvýš jeden tiket denně (kola 1–3 lze za jeden den), na dokončení 42 dní, najednou až 5 Pyramid. "
            f"Simulace hraje {p['soubezne']} Pyramid{'u' if p['soubezne'] == 1 else 'y'} najednou (sporty.yaml: pyramida.soubezne) hlavními tikety kol. Zatím {p['dnu']} dní dat, takže čísla u vyšších kol vycházejí z pár tiketů.</p>")
