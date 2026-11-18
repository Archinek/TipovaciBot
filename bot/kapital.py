"""Doporučené vklady podle kapitálu uživatele.

Sází se jen tam, kde segment (sport × druh trhu × pásmo kurzu) prošel ověřením na vlastních sázkách bota:
  ověřeno -> plný frakční Kelly, kandidát -> jen čtvrtina (zkouška), vše ostatní -> 0.
Pravděpodobnost se před výpočtem sníží o bezpečnostní odečet; kurz se odhaduje jako kurz Tipsportu (srážka proti Fortuně).
Stejný výpočet běží v reportu v JavaScriptu (políčko "Můj kapitál"), tady je jeho referenční verze pro testy.
"""
import html
import json

IMPL = {"srazka_tipsport": 0.12, "odecet_p": 0.02, "min_hrana": 0.02, "kelly_frakce": 0.25, "max_na_tip": 0.02, "max_denne": 0.08,
        "koef_kandidat": 0.25, "zaokrouhlit": 10, "min_vklad": 20}


def parametry(cfg=None):
    return {**IMPL, **((cfg or {}).get("kapital") or {})}


def kurz_tipsport(kurz, srazka):
    return 1 + (float(kurz) - 1) * (1 - srazka)


def kandidati(*seznamy):
    """Sloučí sekce reportu: jeden záznam na zápas (nejvyšší p), jen to, co má ověření."""
    nej = {}
    for s in seznamy:
        for x in s or []:
            kurz = x.get("kurz", x.get("kurz_fortuna"))
            if kurz is None or x.get("p") is None: continue
            k = x["zapas"]
            if k not in nej or x["p"] > nej[k]["p"]:
                nej[k] = {"zapas": x["zapas"], "start": x.get("start"), "sport": x.get("sport") or "", "trh": x.get("trh") or "", "vyber": x.get("vyber") or "",
                          "kurz": float(kurz), "p": float(x["p"]), "overeni": x.get("overeni") or "málo dat"}
    return sorted(nej.values(), key=lambda c: -c["p"])


def vklady(kapital, radky, cfg=None):
    """-> seznam {…radek, vklad, hrana, duvod}; součet vkladů ≤ max_denne × kapitál."""
    c = parametry(cfg)
    out = []
    for x in radky:
        koef = 1.0 if x["overeni"] == "ověřeno" else c["koef_kandidat"] if x["overeni"] == "kandidát" else 0.0
        kt = kurz_tipsport(x["kurz"], c["srazka_tipsport"])
        pe = x["p"] - c["odecet_p"]
        hrana = pe * kt - 1
        v, duvod = 0.0, ""
        if koef == 0: duvod = "segment není ověřen"
        elif kt <= 1 or hrana < c["min_hrana"]: duvod = "po odečtu a srážce bez hrany"
        else:
            f = c["kelly_frakce"] * hrana / (kt - 1) * koef
            v = kapital * min(f, c["max_na_tip"])
        out.append({**x, "kurz_ts": kt, "hrana": hrana, "vklad": v, "duvod": duvod})
    soucet, strop = sum(o["vklad"] for o in out), kapital * c["max_denne"]
    if soucet > strop > 0:
        for o in out: o["vklad"] *= strop / soucet
    for o in out:
        if o["vklad"]:
            o["vklad"] = round(o["vklad"] / c["zaokrouhlit"]) * c["zaokrouhlit"]
            if o["vklad"] < c["min_vklad"]: o["vklad"], o["duvod"] = 0.0, "vklad pod minimem"
    return out


JS = r"""
(function(){var D=JSON.parse(document.getElementById('kapDat').textContent),C=JSON.parse(document.getElementById('kapCfg').textContent);
var inp=document.getElementById('kapIn'),tb=document.getElementById('kapTb'),sum=document.getElementById('kapSum');
function kc(v){return v.toLocaleString('cs-CZ',{minimumFractionDigits:0,maximumFractionDigits:0})+' Kč'}
function kc2(v){return v.toLocaleString('cs-CZ',{minimumFractionDigits:2,maximumFractionDigits:2}).replace(/\u202f/g,'\u00a0')+'\u00a0Kč'}
function vypocti(K){var o=D.map(function(x){var koef=x.overeni==='ověřeno'?1:x.overeni==='kandidát'?C.koef_kandidat:0;
 var kt=1+(x.kurz-1)*(1-C.srazka_tipsport),pe=x.p-C.odecet_p,h=pe*kt-1,v=0,d='';
 if(koef===0)d='segment není ověřen';else if(kt<=1||h<C.min_hrana)d='po odečtu a srážce bez hrany';else{v=K*Math.min(C.kelly_frakce*h/(kt-1)*koef,C.max_na_tip)}
 return Object.assign({},x,{kt:kt,h:h,v:v,d:d})});
 var s=o.reduce(function(a,b){return a+b.v},0),st=K*C.max_denne;if(s>st&&st>0)o.forEach(function(b){b.v*=st/s});
 o.forEach(function(b){if(b.v){b.v=Math.round(b.v/C.zaokrouhlit)*C.zaokrouhlit;if(b.v<C.min_vklad){b.v=0;b.d='vklad pod minimem'}}});return o}
function kresli(){var K=parseFloat((inp.value||'').replace(/\s/g,'').replace(',','.'));
 if(!(K>0)){tb.innerHTML='';sum.textContent='Zadej kapitál, např. 6797,77.';return}
 
 try{localStorage.setItem('tb_kapital',inp.value)}catch(e){}
 var o=vypocti(K),s=o.reduce(function(a,b){return a+b.v},0),n=o.filter(function(b){return b.v>0}).length;
 var zk='<div class="kpi" style="margin:8px 0"><div><b>'+kc2(K)+'</b><span>moje základna</span></div><div><b>'+kc2(s)+'</b><span>dnes sázím ('+(s/K*100).toFixed(1).replace('.',',')+' %)</span></div><div><b>'+kc2(K-s)+'</b><span>zůstává mimo hru</span></div></div>';
 sum.innerHTML=zk+(n?('Doporučeno vsadit na '+n+' tip'+(n>4?'ů':n>1?'y':'')+'. Součet vkladů je <b>'+kc(s)+'</b>.'):'<b>Dnes nic nevsazovat.</b> Žádný tip nesplňuje podmínky (ověřený trh a hrana po srážce). Seznam níže ukazuje, proč.');
 tb.innerHTML=o.map(function(b){var t=new Date(b.start);var cas=isNaN(t)?'':t.toLocaleString('cs-CZ',{day:'numeric',month:'numeric',hour:'2-digit',minute:'2-digit'});
 return '<tr><td>'+cas+'</td><td>'+esc(b.zapas)+'<br><span class="mut">'+esc(b.trh)+(b.vyber?': <b>'+esc(b.vyber)+'</b>':'')+'</span></td><td>'+b.kurz.toFixed(2)+'<br><span class="mut">Tipsport ~'+b.kt.toFixed(2)+'</span></td><td>'+Math.round(b.p*100)+' %<br><span class="mut">'+esc(b.overeni)+'</span></td><td>'+(b.v>0?'<b>'+kc(b.v)+'</b>':'<span class="mut">– '+esc(b.d)+'</span>')+'</td></tr>'}).join('')}
function esc(s){return String(s).replace(/[&<>"]/g,function(c){return{'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]})}
try{var u=localStorage.getItem('tb_kapital');if(u)inp.value=u}catch(e){}
inp.addEventListener('input',kresli);inp.addEventListener('blur',function(){var K=parseFloat((inp.value||'').replace(/\s/g,'').replace(',','.'));if(K>0)inp.value=K.toLocaleString('cs-CZ',{minimumFractionDigits:2,maximumFractionDigits:2}).replace(/\u202f/g,'\u00a0')});kresli()})();
"""


def sekce(radky, cfg=None):
    """HTML sekce s políčkem kapitálu. radky = výstup kandidati()."""
    c = parametry(cfg)
    n_ov = sum(r["overeni"] == "ověřeno" for r in radky)
    n_kan = sum(r["overeni"] == "kandidát" for r in radky)
    uvod = ("<p class='mut'>Zadej svůj kapitál a report spočítá vklad u každého tipu. Vsazuje se <b>jen u ověřených trhů</b> (kandidáti jen čtvrtinou, na zkoušku). "
            f"Vklad = čtvrtinový Kelly z pravděpodobnosti sníž. o {c['odecet_p'] * 100:.0f} b. a z odhadu kurzu Tipsportu (srážka {c['srazka_tipsport'] * 100:.0f} %), "
            f"strop {c['max_na_tip'] * 100:.0f} % kapitálu na zápas a {c['max_denne'] * 100:.0f} % za den. Kapitál se ukládá jen v tvém prohlížeči. "
            f"Dnes: {n_ov} ověřených, {n_kan} kandidátů. Žádná sázka není jistá a model může být vedle.</p>")
    dat = json.dumps(radky, ensure_ascii=False).replace("</", "<\\/")
    cf = json.dumps(c, ensure_ascii=False)
    return (f"<h2 id='kap'>💰 Kapitál a vklady</h2>{uvod}"
            "<div class='box'><label><b>Můj kapitál (Kč):</b> <input id='kapIn' inputmode='decimal' placeholder='např. 6797,77' style='font-size:1.1em;padding:6px;width:11em'></label>"
            "<p id='kapSum' style='margin:.6em 0 0'></p></div>"
            "<div class='w'><table><tr><th>Kdy</th><th>Zápas a tip</th><th>Kurz</th><th>p / ověření</th><th>Vklad</th></tr><tbody id='kapTb'></tbody></table></div>"
            f"<script type='application/json' id='kapDat'>{dat}</script><script type='application/json' id='kapCfg'>{cf}</script><script>{JS}</script>")
