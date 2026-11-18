"""Postup bota v Pyramidě: do kterého kola by se dostal, kdyby každý den sázel tiket aktuálního kola.

Bot každý den poskládá tiket pro všech 10 kol (data/tikety_log.json, klíče pyr1 … pyr10). Výsledek tiketu se skládá z výsledků jeho nohou.
Pravidlo simulace (sporty.yaml -> pyramida.pri_prohre):
  konec        = výhra tiketu posune na další kolo, prohra hru ukončí a nová hra začíná další den od kola 1 (výchozí),
  o_kolo_zpet  = prohra vrací o jedno kolo zpět, hra pokračuje.
Hra, kterou bot dokončí desátým kolem, se počítá jako vyhraná Pyramida. Dny, kdy tiket aktuálního kola ještě není vyhodnocený, hru nechají čekat.
Počítá se jen hlavní tiket kola (alternativa je jen náhradní varianta).
"""
import datetime
import re

KOL = 10


def vysledek_tiketu(t, podle_id):
    """'1' výhra, '0' prohra, '' čeká / chybí nohy (stejné pravidlo jako u tiketů v reportu: bez zrušených nohou)."""
    noze = [podle_id.get(i) for i in t["noze"]]
    if any(n is None for n in noze):
        return ""
    vys = [n["vysledek"] for n in noze if n["vysledek"] != "V"]
    if "0" in vys:
        return "0"
    return "1" if vys and all(x == "1" for x in vys) else ""


def tikety_kol(tiklog, nohy):
    """-> {datum: {kolo: {"vysledek", "kurz", "p", "prah"}}} jen pro hlavní tikety Pyramidy."""
    podle_id = {r["id"]: r for r in nohy}
    out = {}
    for t in tiklog:
        m = re.fullmatch(r"pyr(\d+)", t.get("klic", ""))
        if m:
            out.setdefault(t["datum"], {})[int(m.group(1))] = {"vysledek": vysledek_tiketu(t, podle_id), "kurz": t.get("kurz"), "p": t.get("p"), "prah": t.get("prah")}
    return out


def postup(tiklog, nohy, cfg=None):
    """-> {aktualni, behy, nejlepsi, vyhrano, kola, sance, dnu}"""
    pravidlo = ((cfg or {}).get("pyramida") or {}).get("pri_prohre", "konec")
    dny = tikety_kol(tiklog, nohy)
    kolo, od, behy, cekani, ceka_od = 1, None, [], False, None
    vyhrano = 0
    for d in sorted(dny):
        t = dny[d].get(kolo)
        if not t:
            continue
        if od is None:
            od = d
        if t["vysledek"] == "":
            cekani, ceka_od = True, d
            break
        if t["vysledek"] == "1":
            kolo += 1
            if kolo > KOL:
                behy.append({"od": od, "do": d, "dosazeno": KOL, "stav": "vyhráno"})
                vyhrano += 1
                kolo, od = 1, None
        elif pravidlo == "o_kolo_zpet":
            kolo = max(1, kolo - 1)
        else:
            behy.append({"od": od, "do": d, "dosazeno": kolo - 1, "padl_na": kolo, "stav": "prohra"})
            kolo, od = 1, None
    kola = []
    for k in range(1, KOL + 1):
        rr = [dny[d][k] for d in dny if k in dny[d]]
        h = [x for x in rr if x["vysledek"] in ("0", "1")]
        n = len(h)
        pk = [float(x["p"]) for x in rr if x.get("p") is not None]
        kola.append({"kolo": k, "prah": next((x["prah"] for x in rr if x.get("prah")), None), "tiketu": len(rr), "n": n, "vyhry": sum(x["vysledek"] == "1" for x in h),
                     "uspesnost": (sum(x["vysledek"] == "1" for x in h) / n) if n else None, "cekano": (sum(pk) / len(pk)) if pk else None})
    sance, soucin = [], 1.0
    for k in kola:
        soucin *= k["cekano"] if k["cekano"] is not None else 0.0
        sance.append(soucin)
    posledni = max(dny) if dny else None
    uvizl = bool(cekani and posledni and ceka_od < (datetime.date.fromisoformat(posledni) - datetime.timedelta(days=1)).isoformat())
    aktualni = {"kolo": kolo, "od": od, "serie": kolo - 1, "ceka": cekani, "ceka_od": ceka_od, "uvizl": uvizl}
    nej = max([b["dosazeno"] for b in behy] + [kolo - 1 if od else 0] + [0])
    return {"aktualni": aktualni, "behy": behy, "nejlepsi": nej, "vyhrano": vyhrano, "kola": kola, "sance": sance, "dnu": len(dny), "pravidlo": pravidlo}
