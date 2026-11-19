"""Postup bota v Pyramidě podle pravidel Tipsportu (Soutěže -> Pyramida -> Jak hrát).

Pravidla, která simulace dodržuje:
  - Pyramida má 10 kol s minimálním kurzem tiketu 1,1 / 2 / 3 / … / 10; kolo se prochází tiketem aspoň na tento kurz, kola jdou postupně.
  - Nevyjde-li tiket (nebo nedosáhne kurzu), Pyramida končí a lze začít novou. Výjimka: kurz nedosažen jen kvůli zrušené příležitosti -> jeden život na Pyramidu.
  - Každá Pyramida smí mít nejvýš jeden tiket denně, jen kola 1–3 lze projít během jednoho dne.
  - Na dokončení je 42 dní (počítají se od dne po prvním tiketu).
  - Najednou lze hrát až 5 Pyramid (sporty.yaml -> pyramida.soubezne, výchozí 1).
Bot každý den poskládá tiket pro všech 10 kol (data/tikety_log.json, klíče pyr1 … pyr10); výsledek tiketu se skládá z výsledků jeho nohou.
Simulace bere hlavní tiket kola; paralelní Pyramidy hrají stejné tikety (jsou tedy navzájem závislé).
"""
import datetime
import re

KOL = 10
LIMIT_DNU = 42
CENY = {4: "50 Netů", 5: "100 Netů", 6: "200 Netů", 7: "15 000 Netů", 8: "200 000 Netů", 9: "2 000 000 Kč", 10: "min. 15 000 000 Kč"}


def vysledek_tiketu(t, podle_id):
    """'1' výhra, '0' prohra, 'Z' kurz nedosažen jen kvůli zrušené nohě (život), '' čeká / chybí nohy."""
    noze = [podle_id.get(i) for i in t["noze"]]
    if any(n is None for n in noze):
        return ""
    vys = [n["vysledek"] for n in noze if n["vysledek"] != "V"]
    if "0" in vys:
        return "0"
    if not vys or not all(x == "1" for x in vys):
        return ""
    zrusene = [float(n["kurz"]) for n in noze if n["vysledek"] == "V"]
    if zrusene and t.get("kurz") and t.get("prah"):
        k = float(t["kurz"])
        for z in zrusene:
            k /= z
        if k < float(t["prah"]):
            return "Z"
    return "1"


def tikety_kol(tiklog, nohy):
    """-> {datum: {kolo: {"vysledek", "kurz", "p", "prah"}}} jen pro hlavní tikety Pyramidy."""
    podle_id = {r["id"]: r for r in nohy}
    out = {}
    for t in tiklog:
        m = re.fullmatch(r"pyr(\d+)", t.get("klic", ""))
        if m:
            out.setdefault(t["datum"], {})[int(m.group(1))] = {"vysledek": vysledek_tiketu(t, podle_id), "kurz": t.get("kurz"), "p": t.get("p"), "prah": t.get("prah")}
    return out


def _novy():
    return {"kolo": 1, "od": None, "zivot": True, "ceka_od": None}


def postup(tiklog, nohy, cfg=None):
    """-> {aktivni: [{kolo, od, zbyva_dni, zivot, ceka, ceka_od, uvizl}], aktualni (první aktivní), behy, nejlepsi, vyhrano, kola, sance, dnu, soubezne}"""
    soubezne = max(1, min(5, int(((cfg or {}).get("pyramida") or {}).get("soubezne", 1))))
    od_data = str(((cfg or {}).get("pyramida") or {}).get("od") or "")
    dny = {d: v for d, v in tikety_kol(tiklog, nohy).items() if d >= od_data}      # starší dny se do simulace nepočítají
    sloty, behy, vyhrano = [_novy() for _ in range(soubezne)], [], 0
    posledni = max(dny) if dny else None
    for d in sorted(dny):
        dd = datetime.date.fromisoformat(d)
        for i, s in enumerate(sloty):
            if s.get("blok"):
                continue
            if s["od"] and dd > datetime.date.fromisoformat(s["od"]) + datetime.timedelta(days=LIMIT_DNU):
                behy.append({"od": s["od"], "do": d, "dosazeno": s["kolo"] - 1, "padl_na": s["kolo"], "stav": "vypršelo 42 dní"})
                sloty[i] = s = _novy()
            while True:
                t = dny[d].get(s["kolo"])
                if not t:
                    break
                if s["od"] is None:
                    s["od"] = d
                v = t["vysledek"]
                if v == "":
                    s["blok"], s["ceka_od"] = True, d
                    break
                if v == "1":
                    s["kolo"] += 1
                    if s["kolo"] > KOL:
                        behy.append({"od": s["od"], "do": d, "dosazeno": KOL, "stav": "vyhráno"})
                        vyhrano += 1
                        sloty[i] = s = _novy()
                        break
                    if s["kolo"] <= 3:          # kola 1–3 lze projít za jeden den
                        continue
                    break
                if v == "Z" and s["zivot"]:
                    s["zivot"] = False
                    break                       # život: kolo se opakuje další den
                behy.append({"od": s["od"], "do": d, "dosazeno": s["kolo"] - 1, "padl_na": s["kolo"], "stav": "prohra" if v == "0" else "prohra (zrušená noha, život už spotřebován)"})
                sloty[i] = s = _novy()
                break
    aktivni = []
    for s in sloty:
        uvizl = bool(s.get("blok") and posledni and s["ceka_od"] < (datetime.date.fromisoformat(posledni) - datetime.timedelta(days=1)).isoformat())
        zbyva = None
        if s["od"] and posledni:
            zbyva = max(0, (datetime.date.fromisoformat(s["od"]) + datetime.timedelta(days=LIMIT_DNU) - datetime.date.fromisoformat(posledni)).days)
        aktivni.append({"kolo": s["kolo"], "od": s["od"], "serie": s["kolo"] - 1, "zivot": s["zivot"], "ceka": bool(s.get("blok")), "ceka_od": s["ceka_od"], "uvizl": uvizl, "zbyva_dni": zbyva})
    kola = []
    for k in range(1, KOL + 1):
        rr = [dny[d][k] for d in dny if k in dny[d]]
        h = [x for x in rr if x["vysledek"] in ("0", "1", "Z")]
        n = len(h)
        pk = [float(x["p"]) for x in rr if x.get("p") is not None]
        vyhry = sum(x["vysledek"] == "1" for x in h)
        kola.append({"kolo": k, "prah": next((x["prah"] for x in rr if x.get("prah")), None), "tiketu": len(rr), "n": n, "vyhry": vyhry,
                     "uspesnost": (vyhry / n) if n else None, "cekano": (sum(pk) / len(pk)) if pk else None, "cena": CENY.get(k)})
    sance, soucin = [], 1.0
    for k in kola:
        soucin *= k["cekano"] if k["cekano"] is not None else 0.0
        sance.append(soucin)
    nej = max([b["dosazeno"] for b in behy] + [a["kolo"] - 1 for a in aktivni if a["od"]] + [0])
    return {"aktivni": aktivni, "aktualni": aktivni[0], "behy": behy, "nejlepsi": nej, "vyhrano": vyhrano, "kola": kola, "sance": sance, "dnu": len(dny), "soubezne": soubezne}
